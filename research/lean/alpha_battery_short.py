"""LEAN short-horizon alpha battery (reversal family), 5-day holding.
Specifications frozen in
`docs/ALPHA_BATTERY_2026-08-16_QC_PREREGISTRATION.md`.

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


class AlphaBatteryShort(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(*START)
        self.SetEndDate(*END)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        # Raw coarse/fine fields drive the screens; adjusted bars drive all
        # return arithmetic so stock splits cannot become fictitious alpha.
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Adjusted
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.AddUniverse(self._coarse, self._fine)

        self.closes = {}
        self.volumes = {}
        self.industry = {}
        self.selected = []
        self.selection_month = None
        self.pending = None
        self.staged = None
        self.days_held = 0
        self.prior_outcomes = {}
        self.last_session = None
        self.in_universe = set()
        self.retained = set()
        self.terminal_prices = {}
        self.results = {}
        self.previous_weights = {}
        self.cap_rows = self.cap_fallback = self.cap_missing = 0

    def _coarse(self, coarse):
        if self.selection_month == (self.Time.year, self.Time.month):
            return Universe.Unchanged
        return [c.Symbol for c in coarse
                if c.HasFundamentalData
                and c.Price >= self.screen["min_price"]
                and c.DollarVolume >= self.screen["min_adv"]]

    def _fine(self, fine):
        if self.selection_month == (self.Time.year, self.Time.month):
            return Universe.Unchanged
        self.selection_month = (self.Time.year, self.Time.month)
        chosen = []
        for f in fine:
            self.cap_rows += 1
            cap = float(f.MarketCap or 0.0)
            if cap <= 0.0:
                try:
                    shares = float(f.CompanyProfile.SharesOutstanding or 0.0)
                except Exception:  # noqa: BLE001
                    shares = 0.0
                price = float(f.Price or 0.0)
                if shares > 0.0 and price > 0.0:
                    cap = shares * price
                    self.cap_fallback += 1
                else:
                    self.cap_missing += 1
                    continue
            if cap < self.screen["min_cap"]:
                continue
            self.industry[f.Symbol] = int(
                f.AssetClassification.MorningstarIndustryCode or 0)
            chosen.append(f.Symbol)
        current = set(chosen)
        needed = set()
        if self.pending is not None:
            needed.update(self.pending.get("entry", {}))
        if self.staged is not None:
            needed.update(self.staged.get("names", ()))
        for symbol in self.in_universe - current:
            if symbol in needed and symbol not in self.retained:
                self.AddSecurity(symbol, Resolution.Daily)
                self.retained.add(symbol)
        self.in_universe = current
        self.selected = chosen
        return chosen

    def OnData(self, data):
        for symbol, delisting in data.Delistings.items():
            if delisting.Type != DelistingType.Delisted:
                continue
            raw_price = getattr(delisting, "Price", None)
            if raw_price is None:
                raw_price = getattr(delisting, "Value", 0.0)
            try:
                self.terminal_prices[symbol] = max(0.0, float(raw_price))
            except (TypeError, ValueError):
                self.terminal_prices[symbol] = 0.0

        for symbol in list(data.Bars.Keys):
            bar = data.Bars[symbol]
            self.closes.setdefault(symbol, deque(maxlen=LOOKBACK)).append(float(bar.Close))
            self.volumes.setdefault(symbol, deque(maxlen=LOOKBACK)).append(float(bar.Volume))

        session = self.Time.date()
        if not data.Bars or session == self.last_session:
            return
        self.last_session = session

        entered_today = False
        if self.staged is not None and session > self.staged["score_session"]:
            entered_today = self._bind_staged_entry()

        if self.pending is not None and not entered_today:
            self.days_held += 1
            if self.days_held >= HOLD_DAYS:
                self.prior_outcomes = self._settle()
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
            keys = (
                (spec, "long_short"),
                (spec, "long_only_10"),
                (spec, "long_only_20"),
            )
            targets = (
                ls_weights,
                {symbol: 1.0 / len(longs) for symbol in longs},
                {symbol: 1.0 / len(long20) for symbol in long20},
            )
            turns = tuple(
                _drift_turnover(self.previous_weights.get(key) or {}, target,
                                self.prior_outcomes)
                for key, target in zip(keys, targets)
            )
            if any(value is None for value in turns):
                continue
            for key, target in zip(keys, targets):
                self.previous_weights[key] = target
            portfolios[spec] = {
                "longs": longs, "shorts": shorts, "long20": long20,
                "turnovers": turns,
            }
        if not portfolios:
            return False
        self.pending = {
            "scores": staged["scores"],
            "entry": entry,
            "date": staged["date"],
            "portfolios": portfolios,
        }
        self.prior_outcomes = {}
        self.days_held = 0
        return True

    def _price(self, symbol, ago):
        window = self.closes.get(symbol)
        if window is None or len(window) <= ago:
            return None
        return window[len(window) - 1 - ago]

    def _form_scores(self):
        names = [s for s in self.selected if len(self.closes.get(s, ())) >= 65]
        if len(names) < MIN_NAMES:
            return

        ret5 = {}
        for symbol in names:
            now, then = self._price(symbol, 0), self._price(symbol, 5)
            ret5[symbol] = None if not now or not then or then <= 0 else now / then - 1.0

        industry_peers = {}
        buckets = {}
        for symbol in names:
            if ret5.get(symbol) is not None:
                buckets.setdefault(self.industry.get(symbol), []).append(ret5[symbol])
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
            if window is None or len(window) < 60:
                continue
            recent = list(window)[-60:]
            mean = sum(recent) / len(recent)
            var = sum((v - mean) ** 2 for v in recent) / max(1, len(recent) - 1)
            sd = math.sqrt(var)
            if sd > 0:
                volume_z[symbol] = max(-3.0, min(3.0, (recent[-1] - mean) / sd))

        max20 = {}
        for symbol in names:
            window = self.closes.get(symbol)
            if window is None or len(window) < 21:
                continue
            values = list(window)[-21:]
            daily = [values[i + 1] / values[i] - 1.0
                     for i in range(len(values) - 1) if values[i] > 0]
            if daily:
                max20[symbol] = max(daily)

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
            "date": str(self.Time.date()),
            "score_session": self.Time.date(),
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
            long_ret = sum(outcomes[s] for s in longs) / len(longs)
            short_ret = sum(outcomes[s] for s in shorts) / len(shorts)
            long20_ret = sum(outcomes[s] for s in long20) / len(long20)
            self.results.setdefault(spec, []).append(
                (pending["date"], ic, long_ret, short_ret, long20_ret,
                 portfolio["turnovers"][0], portfolio["turnovers"][1],
                 portfolio["turnovers"][2], len(usable)))
        self._release_unused_retained()
        return outcomes

    def _release_unused_retained(self):
        needed = set(self.pending.get("entry", {})) if self.pending else set()
        for symbol in list(self.retained):
            if symbol not in needed and symbol not in self.in_universe:
                self.RemoveSecurity(symbol)
                self.retained.remove(symbol)

    def OnEndOfAlgorithm(self):
        self.Log(f"=== ALPHA BATTERY SHORT | universe={ACTIVE_UNIVERSE} ===")
        self.Log(f"cap_rows={self.cap_rows} cap_fallback={self.cap_fallback} "
                 f"cap_missing={self.cap_missing}")
        order = list(SPECIFICATIONS)
        missing = [spec for spec in order if spec not in self.results]
        if missing:
            self.Error(f"INCOMPLETE|missing_specs={'|'.join(missing)}")
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
        by_date = {}
        for spec, rows in self.results.items():
            for date, ic, lr, sr, l20, turn_ls, turn_l10, turn_l20, n in rows:
                turns = tuple(int(round(value * 10000))
                              for value in (turn_ls, turn_l10, turn_l20))
                if any(value < 0 or value > 65535 for value in turns):
                    self.Error(f"INCOMPLETE|turnover_out_of_range|{spec}|{date}")
                    return
                by_date.setdefault(date, {})[index_of[spec]] = (
                    -2147483648 if ic is None else int(round(ic * 100000)),
                    int(round(lr * 1000000)),
                    int(round(sr * 1000000)),
                    int(round(l20 * 1000000)),
                    turns[0], turns[1], turns[2],
                )
        self.Log(f"SPECS|{'|'.join(order)}")
        self.Log("SCALE|layout=b64block_date_u32_i32x4_u16x3|ic=1e-5|ret=1e-6|turnover=1e-4")
        self.Log(f"DATES|{len(by_date)}")
        for spec in order:
            rows = self.results[spec]
            names = sorted(r[8] for r in rows)
            self.Log(f"SPECMETA|{spec}|median_names={names[len(names)//2]}"
                     f"|periods={len(rows)}")
        records = []
        for date in sorted(by_date):
            cells = by_date[date]
            if set(cells) != set(range(len(order))):
                self.Error(f"INCOMPLETE|missing_date_specs|{date}")
                return
            payload = struct.pack(">I", int(date.replace('-', '')))
            payload += b"".join(struct.pack(">iiiiHHH", *cells[index])
                                for index in range(len(order)))
            records.append(payload)
        for start in range(0, len(records), 10):
            block = records[start:start + 10]
            encoded = base64.b64encode(b"".join(block)).decode("ascii")
            self.Log(f"B64BLOCK|{len(block)}|{encoded}")
        self.Log(f"orders placed: {self.Transactions.OrdersCount}")
