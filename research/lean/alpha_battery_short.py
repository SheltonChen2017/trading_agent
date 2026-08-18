"""LEAN short-horizon alpha battery (reversal family), 5-day holding.
Specifications frozen in
`docs/research/ALPHA_BATTERY_2026-08-16_QC_PREREGISTRATION.md`.

This algorithm REPORTS ALPHA STATISTICS, so every run is a counted
research look. It is not exempt.

Same design rules as the monthly battery, and one that matters more here:
the industry adjustment uses the real `MorningstarIndustryCode`, which the
field probe found present on 100% of rows. The local run had no industry
data and substituted size buckets, which both failed to adjust for
industry and leaked future capitalization (ABR-005). ALPHA 004 is
therefore tested here for the first time rather than approximated.

Output is packed one line per DATE with spec indices, because QuantConnect
truncates cloud logs by total volume: the first monthly run silently lost
three specifications of ten to that limit, and a per-(spec, date) layout
would lose far more here where the cadence is weekly.
"""
from AlgorithmImports import *  # noqa: F403

import base64
from collections import deque
import math
import struct


ACTIVE_UNIVERSE = "B_core"
START = (2012, 1, 1)
END = (2024, 12, 31)

UNIVERSES = {
    "A_large": {"min_price": 5.0, "min_cap": 10_000_000_000.0, "min_adv": 25_000_000.0},
    "B_core": {"min_price": 5.0, "min_cap": 500_000_000.0, "min_adv": 5_000_000.0},
    "C_broad": {"min_price": 3.0, "min_cap": 100_000_000.0, "min_adv": 1_000_000.0},
}

LOOKBACK = 90
HOLD_DAYS = 5
MIN_NAMES = 30
DECILE = 0.10
QUINTILE = 0.20
SPECIFICATIONS = (
    "ABNORMAL_VOLUME_REVERSAL", "INDUSTRY_ADJ_REVERSAL_5D", "MAX_20",
    "MAX_X_REVERSAL", "REVERSAL_5D",
)


def _aligned_observation_tail(values, value_sessions, market_sessions, count):
    """Return ``count`` observations only on consecutive market sessions."""
    if count <= 0 or count > len(values) or count > len(value_sessions):
        return None
    if count > len(market_sessions):
        return None
    sessions = list(value_sessions)[-count:]
    if sessions != list(market_sessions)[-count:]:
        return None
    return list(values)[-count:]


def _spearman(pairs):
    if len(pairs) < MIN_NAMES:
        return None
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = average
            i = j + 1
        return out
    xs = ranks([p[0] for p in pairs])
    ys = ranks([p[1] for p in pairs])
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    return None if dx <= 0 or dy <= 0 else num / (dx * dy)


def _drift_turnover(previous, target, outcomes):
    """Method V2 one-way turnover from drifted signed weights."""
    if not previous:
        return 0.5 * sum(abs(weight) for weight in target.values())
    if any(symbol not in outcomes for symbol in previous):
        return None
    portfolio_return = sum(
        weight * outcomes.get(symbol, 0.0)
        for symbol, weight in previous.items()
    )
    denominator = 1.0 + portfolio_return
    if denominator <= 0.0:
        return None
    drifted = {
        symbol: weight * (1.0 + outcomes.get(symbol, 0.0)) / denominator
        for symbol, weight in previous.items()
    }
    names = set(drifted) | set(target)
    return 0.5 * sum(
        abs(target.get(symbol, 0.0) - drifted.get(symbol, 0.0))
        for symbol in names
    )


def _round_trip_turnover(target, outcomes):
    """One-way entry plus exit turnover for one five-session holding."""
    entry_turnover = _drift_turnover({}, target, {})
    exit_turnover = _drift_turnover(target, {}, outcomes)
    if exit_turnover is None:
        return None
    return exit_turnover + entry_turnover


def _max_daily_return(values):
    """Return MAX(20) only from exactly 21 finite, positive closes."""
    if len(values) != 21:
        return None
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        return None
    return max(values[index + 1] / values[index] - 1.0
               for index in range(20))


def _valid_industry_code(value):
    """Return a real Morningstar industry code; missing/invalid stays missing."""
    try:
        code = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return None
    return code if code > 0 else None


class AlphaBatteryShort(QCAlgorithm):

    def initialize(self):
        self.set_start_date(*START)
        self.set_end_date(*END)
        self.set_cash(100_000)
        self.universe_settings.resolution = Resolution.DAILY
        # Raw coarse/fine fields drive the screens; adjusted bars drive all
        # return arithmetic so stock splits cannot become fictitious alpha.
        self.universe_settings.data_normalization_mode = DataNormalizationMode.ADJUSTED
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.add_universe(self._coarse, self._fine)

        self.closes = {}
        self.close_sessions = {}
        self.volumes = {}
        self.volume_sessions = {}
        self.sessions = deque(maxlen=LOOKBACK)
        self.industry = {}
        self.selected = []
        self.selection_month = None
        self.pending = None
        self.staged = None
        self.days_held = 0
        self.last_session = None
        self.in_universe = set()
        self.retained = set()
        self.terminal_prices = {}
        self.results = {}
        self.cap_rows = self.cap_fallback = self.cap_missing = 0

    def _coarse(self, coarse):
        if self.selection_month == (self.time.year, self.time.month):
            return Universe.UNCHANGED
        return [c.symbol for c in coarse
                if c.has_fundamental_data
                and c.price >= self.screen["min_price"]
                and c.dollar_volume >= self.screen["min_adv"]]

    def _fine(self, fine):
        if self.selection_month == (self.time.year, self.time.month):
            return Universe.UNCHANGED
        self.selection_month = (self.time.year, self.time.month)
        chosen = []
        for f in fine:
            self.cap_rows += 1
            cap = float(f.market_cap or 0.0)
            if cap <= 0.0:
                try:
                    shares = float(f.company_profile.shares_outstanding or 0.0)
                except Exception:  # noqa: BLE001
                    shares = 0.0
                price = float(f.price or 0.0)
                if shares > 0.0 and price > 0.0:
                    cap = shares * price
                    self.cap_fallback += 1
                else:
                    self.cap_missing += 1
                    continue
            if cap < self.screen["min_cap"]:
                continue
            code = _valid_industry_code(
                f.asset_classification.morningstar_industry_code)
            if code is None:
                self.industry.pop(f.symbol, None)
            else:
                self.industry[f.symbol] = code
            chosen.append(f.symbol)
        current = set(chosen)
        needed = set()
        if self.pending is not None:
            needed.update(self.pending.get("entry", {}))
        if self.staged is not None:
            needed.update(self.staged.get("names", ()))
        for symbol in self.in_universe - current:
            if symbol in needed and symbol not in self.retained:
                self.add_security(symbol, Resolution.DAILY)
                self.retained.add(symbol)
        self.in_universe = current
        self.selected = chosen
        return chosen

    def on_data(self, data):
        for symbol, delisting in data.delistings.items():
            if delisting.type != DelistingType.DELISTED:
                continue
            raw_price = getattr(delisting, "price", None)
            if raw_price is None:
                raw_price = getattr(delisting, "value", 0.0)
            try:
                self.terminal_prices[symbol] = max(0.0, float(raw_price))
            except (TypeError, ValueError):
                self.terminal_prices[symbol] = 0.0

        session = self.time.date()
        if not data.bars or session == self.last_session:
            return
        self.last_session = session
        self.sessions.append(session)

        for symbol in list(data.bars.keys()):
            bar = data.bars[symbol]
            if symbol not in self.closes:
                self.closes[symbol] = deque(maxlen=LOOKBACK)
                self.close_sessions[symbol] = deque(maxlen=LOOKBACK)
                self.volumes[symbol] = deque(maxlen=LOOKBACK)
                self.volume_sessions[symbol] = deque(maxlen=LOOKBACK)
            self.closes[symbol].append(float(bar.close))
            self.close_sessions[symbol].append(session)
            self.volumes[symbol].append(float(bar.volume))
            self.volume_sessions[symbol].append(session)

        entered_today = False
        if self.staged is not None and session > self.staged["score_session"]:
            entered_today = self._bind_staged_entry()

        if self.pending is not None and not entered_today:
            self.days_held += 1
            if self.days_held >= HOLD_DAYS:
                self._settle()
        if self.pending is None and self.staged is None and self.selected:
            self._form_scores()

    def _bind_staged_entry(self):
        staged = self.staged
        self.staged = None
        entry = {
            symbol: self._price(symbol, 0)
            for symbol in staged["names"]
            if symbol not in self.terminal_prices and self._price(symbol, 0) is not None
        }
        if len(entry) < MIN_NAMES:
            return False
        portfolios = {}
        for spec, scores in staged["scores"].items():
            usable = [(value, symbol) for symbol, value in scores.items()
                      if value is not None and math.isfinite(value) and symbol in entry]
            if len(usable) < MIN_NAMES:
                continue
            ranked = sorted(usable, key=lambda pair: pair[0], reverse=True)
            cut = max(1, int(round(len(ranked) * DECILE)))
            quint = max(1, int(round(len(ranked) * QUINTILE)))
            longs = [symbol for _, symbol in ranked[:cut]]
            shorts = [symbol for _, symbol in ranked[-cut:]]
            long20 = [symbol for _, symbol in ranked[:quint]]
            ls_weights = {symbol: 0.5 / len(longs) for symbol in longs}
            for symbol in shorts:
                ls_weights[symbol] = ls_weights.get(symbol, 0.0) - 0.5 / len(shorts)
            targets = (
                ls_weights,
                {symbol: 1.0 / len(longs) for symbol in longs},
                {symbol: 1.0 / len(long20) for symbol in long20},
            )
            portfolios[spec] = {
                "longs": longs, "shorts": shorts, "long20": long20,
                "weights": targets,
            }
        if not portfolios:
            return False
        self.pending = {
            "scores": staged["scores"],
            "entry": entry,
            "date": staged["date"],
            "portfolios": portfolios,
        }
        self.days_held = 0
        return True

    def _price(self, symbol, ago):
        window = self.closes.get(symbol)
        sessions = self.close_sessions.get(symbol)
        if window is None or sessions is None:
            return None
        values = _aligned_observation_tail(
            window, sessions, self.sessions, ago + 1
        )
        return None if values is None else values[0]

    def _form_scores(self):
        names = [
            symbol for symbol in self.selected
            if _aligned_observation_tail(
                self.closes.get(symbol, ()),
                self.close_sessions.get(symbol, ()),
                self.sessions,
                65,
            ) is not None
        ]
        if len(names) < MIN_NAMES:
            return

        ret5 = {}
        for symbol in names:
            now, then = self._price(symbol, 0), self._price(symbol, 5)
            ret5[symbol] = None if not now or not then or then <= 0 else now / then - 1.0

        industry_peers = {}
        buckets = {}
        for symbol in names:
            code = self.industry.get(symbol)
            if code is not None and ret5.get(symbol) is not None:
                buckets.setdefault(code, []).append(ret5[symbol])
        for code, values in buckets.items():
            if len(values) >= 3:
                total = sum(values)
                members = [s for s in names
                           if self.industry.get(s) == code and ret5.get(s) is not None]
                for symbol in members:
                    industry_peers[symbol] = (total - ret5[symbol]) / (len(values) - 1)

        volume_z = {}
        for symbol in names:
            window = self.volumes.get(symbol)
            sessions = self.volume_sessions.get(symbol)
            if window is None or sessions is None:
                continue
            recent = _aligned_observation_tail(
                window, sessions, self.sessions, 60
            )
            if recent is None:
                continue
            mean = sum(recent) / len(recent)
            var = sum((v - mean) ** 2 for v in recent) / max(1, len(recent) - 1)
            sd = math.sqrt(var)
            if sd > 0:
                volume_z[symbol] = max(-3.0, min(3.0, (recent[-1] - mean) / sd))

        max20 = {}
        for symbol in names:
            window = self.closes.get(symbol)
            sessions = self.close_sessions.get(symbol)
            if window is None or sessions is None:
                continue
            values = _aligned_observation_tail(
                window, sessions, self.sessions, 21
            )
            if values is None:
                continue
            maximum = _max_daily_return(values)
            if maximum is not None:
                max20[symbol] = maximum

        ranked_max = sorted([s for s in max20], key=lambda s: max20[s])
        max_rank = {}
        rank_index = 0
        while rank_index < len(ranked_max):
            tie_end = rank_index
            while (tie_end + 1 < len(ranked_max)
                   and max20[ranked_max[tie_end + 1]] == max20[ranked_max[rank_index]]):
                tie_end += 1
            percentile = ((rank_index + tie_end) / 2.0 + 1.0) / len(ranked_max)
            for tied in ranked_max[rank_index:tie_end + 1]:
                max_rank[tied] = percentile
            rank_index = tie_end + 1

        scores = {
            "REVERSAL_5D": {s: None if ret5.get(s) is None else -ret5[s] for s in names},
            "INDUSTRY_ADJ_REVERSAL_5D": {
                s: None if ret5.get(s) is None
                or s not in industry_peers
                else -(ret5[s] - industry_peers[s])
                for s in names
            },
            "ABNORMAL_VOLUME_REVERSAL": {
                s: None if ret5.get(s) is None or s not in volume_z
                else -ret5[s] * volume_z[s]
                for s in names
            },
            "MAX_20": {s: None if s not in max20 else -max20[s] for s in names},
            "MAX_X_REVERSAL": {
                s: None if ret5.get(s) is None or s not in max_rank
                else -ret5[s] * max_rank[s]
                for s in names
            },
        }
        self.staged = {
            "scores": scores,
            "names": names,
            "date": str(self.time.date()),
            "score_session": self.time.date(),
        }

    def _settle(self):
        pending = self.pending
        self.pending = None
        outcomes = {}
        for symbol, entry_price in pending["entry"].items():
            now = self.terminal_prices.get(symbol, self._price(symbol, 0))
            if entry_price and now is not None and entry_price > 0:
                outcomes[symbol] = now / entry_price - 1.0
        if len(outcomes) < MIN_NAMES:
            self._release_unused_retained()
            return outcomes
        for spec, portfolio in pending["portfolios"].items():
            scores = pending["scores"][spec]
            usable = [(v, s) for s, v in scores.items()
                      if v is not None and math.isfinite(v) and s in outcomes]
            if len(usable) < MIN_NAMES:
                continue
            ic = _spearman([(v, outcomes[s]) for v, s in usable])
            longs = portfolio["longs"]
            shorts = portfolio["shorts"]
            long20 = portfolio["long20"]
            if any(symbol not in outcomes for symbol in longs + shorts + long20):
                continue
            # Turnover is a COST input, never a gate on the alpha result
            # (R-010/R-013). An unpriceable exit book emits None, which the
            # packed layout carries as a declared-unavailability sentinel and
            # the analyser charges at the conservative full 1.0 one-way.
            turnovers = tuple(
                _round_trip_turnover(target, outcomes)
                for target in portfolio["weights"]
            )
            long_ret = sum(outcomes[s] for s in longs) / len(longs)
            short_ret = sum(outcomes[s] for s in shorts) / len(shorts)
            long20_ret = sum(outcomes[s] for s in long20) / len(long20)
            self.results.setdefault(spec, []).append(
                (pending["date"], ic, long_ret, short_ret, long20_ret,
                 turnovers[0], turnovers[1], turnovers[2], len(usable)))
        self._release_unused_retained()
        return outcomes

    def _release_unused_retained(self):
        needed = set(self.pending.get("entry", {})) if self.pending else set()
        for symbol in list(self.retained):
            if symbol not in needed and symbol not in self.in_universe:
                self.remove_security(symbol)
                self.retained.remove(symbol)

    def on_end_of_algorithm(self):
        self.log(f"=== ALPHA BATTERY SHORT | universe={ACTIVE_UNIVERSE} ===")
        self.log(f"cap_rows={self.cap_rows} cap_fallback={self.cap_fallback} "
                 f"cap_missing={self.cap_missing}")
        order = list(SPECIFICATIONS)
        missing = [spec for spec in order if spec not in self.results]
        if missing:
            self.error(f"INCOMPLETE|missing_specs={'|'.join(missing)}")
            return
        index_of = {spec: i for i, spec in enumerate(order)}
        # PACKED SCALED INTEGERS. QuantConnect's log cap is about 100KB,
        # measured:
        # a 283-char-per-row layout truncated at 359 of 1,311 dates, while
        # the monthly battery's 76KB survived intact. Decimal text is the
        # expensive part. Each spec/date uses four signed int32 values (IC
        # at 1e-5 and three returns at 1e-6) plus three uint16 turnovers at
        # 1e-4. Ten dated rows are base64 encoded per log message so the
        # platform's own timestamp prefix does not push the run back over
        # the cap. This preserves full-period
        # state in one run; splitting the calendar would reset warm-up,
        # holding cadence, and drift-aware turnover at the boundary.
        if len(order) > 8:
            # The u8 presence mask below carries at most eight specs.
            self.error(f"INCOMPLETE|too_many_specs_for_mask|{len(order)}")
            return
        by_date = {}
        for spec, rows in self.results.items():
            for date, ic, lr, sr, l20, turn_ls, turn_l10, turn_l20, n in rows:
                turns = []
                for value in (turn_ls, turn_l10, turn_l20):
                    if value is None:
                        # 65535 is reserved as the declared-unavailability
                        # sentinel (unpriceable exit book, R-013); a real
                        # turnover too large to represent is refused below.
                        turns.append(65535)
                        continue
                    scaled = int(round(value * 10000))
                    if scaled < 0 or scaled > 65534:
                        self.error(
                            f"INCOMPLETE|turnover_out_of_range|{spec}|{date}")
                        return
                    turns.append(scaled)
                by_date.setdefault(date, {})[index_of[spec]] = (
                    -2147483648 if ic is None else int(round(ic * 100000)),
                    int(round(lr * 1000000)),
                    int(round(sr * 1000000)),
                    int(round(l20 * 1000000)),
                    turns[0], turns[1], turns[2],
                )
        self.log(f"SPECS|{'|'.join(order)}")
        self.log("SCALE|layout=b64block_date_u32_mask_u8_i32x4_u16x3"
                 "|ic=1e-5|ret=1e-6|turnover=1e-4")
        self.log(f"DATES|{len(by_date)}")
        for spec in order:
            rows = self.results[spec]
            names = sorted(r[8] for r in rows)
            self.log(f"SPECMETA|{spec}|median_names={names[len(names)//2]}"
                     f"|periods={len(rows)}")
        records = []
        for date in sorted(by_date):
            cells = by_date[date]
            # A date may honestly lack some specs (below MIN_NAMES usable
            # names, a held name with no outcome). The presence mask declares
            # exactly which specs emitted, so ordinary per-spec raggedness —
            # already the norm in the monthly battery — never forces refusing
            # the entire run (R-013: one absent MAX_20 date withheld 2,664
            # honest spec-date cells).
            mask = 0
            for index in cells:
                mask |= 1 << index
            payload = struct.pack(">IB", int(date.replace('-', '')), mask)
            payload += b"".join(struct.pack(">iiiiHHH", *cells[index])
                                for index in sorted(cells))
            records.append(payload)
        for start in range(0, len(records), 10):
            block = records[start:start + 10]
            encoded = base64.b64encode(b"".join(block)).decode("ascii")
            self.log(f"B64BLOCK|{len(block)}|{encoded}")
        self.log(f"orders placed: {self.transactions.orders_count}")
