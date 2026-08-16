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

from collections import deque
import math


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


class AlphaBatteryShort(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(*START)
        self.SetEndDate(*END)
        self.SetCash(100_000)
        self.UniverseSettings.Resolution = Resolution.Daily
        self.UniverseSettings.DataNormalizationMode = DataNormalizationMode.Raw
        self.screen = UNIVERSES[ACTIVE_UNIVERSE]
        self.AddUniverse(self._coarse, self._fine)

        self.closes = {}
        self.volumes = {}
        self.industry = {}
        self.selected = []
        self.selection_month = None
        self.pending = None
        self.days_held = 0
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
        self.selected = chosen
        return chosen

    def OnData(self, data):
        for symbol in list(data.Bars.Keys):
            bar = data.Bars[symbol]
            self.closes.setdefault(symbol, deque(maxlen=LOOKBACK)).append(float(bar.Close))
            self.volumes.setdefault(symbol, deque(maxlen=LOOKBACK)).append(float(bar.Volume))

        if self.pending is not None:
            self.days_held += 1
            if self.days_held >= HOLD_DAYS:
                self._settle()
        if self.pending is None and self.selected:
            self._form_scores()

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

        industry_mean = {}
        buckets = {}
        for symbol in names:
            if ret5.get(symbol) is not None:
                buckets.setdefault(self.industry.get(symbol), []).append(ret5[symbol])
        for code, values in buckets.items():
            if len(values) >= 3:
                industry_mean[code] = sum(values) / len(values)

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
        max_rank = {s: (i + 1) / len(ranked_max) for i, s in enumerate(ranked_max)}

        scores = {
            "REVERSAL_5D": {s: None if ret5.get(s) is None else -ret5[s] for s in names},
            "INDUSTRY_ADJ_REVERSAL_5D": {
                s: None if ret5.get(s) is None
                or self.industry.get(s) not in industry_mean
                else -(ret5[s] - industry_mean[self.industry[s]])
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
        entry = {s: self._price(s, 0) for s in names}
        self.pending = {"scores": scores, "entry": entry,
                        "date": str(self.Time.date())}
        self.days_held = 0

    def _settle(self):
        pending = self.pending
        self.pending = None
        outcomes = {}
        for symbol, entry_price in pending["entry"].items():
            now = self._price(symbol, 0)
            if entry_price and now and entry_price > 0:
                outcomes[symbol] = now / entry_price - 1.0
        if len(outcomes) < MIN_NAMES:
            return
        for spec, scores in pending["scores"].items():
            usable = [(v, s) for s, v in scores.items()
                      if v is not None and math.isfinite(v) and s in outcomes]
            if len(usable) < MIN_NAMES:
                continue
            ic = _spearman([(v, outcomes[s]) for v, s in usable])
            ranked = sorted(usable, key=lambda p: p[0], reverse=True)
            cut = max(1, int(round(len(ranked) * DECILE)))
            quint = max(1, int(round(len(ranked) * QUINTILE)))
            longs = [s for _, s in ranked[:cut]]
            shorts = [s for _, s in ranked[-cut:]]
            long20 = [s for _, s in ranked[:quint]]
            long_ret = sum(outcomes[s] for s in longs) / len(longs)
            short_ret = sum(outcomes[s] for s in shorts) / len(shorts)
            long20_ret = sum(outcomes[s] for s in long20) / len(long20)
            weights = {s: 0.5 / len(longs) for s in longs}
            for s in shorts:
                weights[s] = weights.get(s, 0.0) - 0.5 / len(shorts)
            turnover = self._turnover(spec, weights, outcomes)
            self.results.setdefault(spec, []).append(
                (pending["date"], ic, long_ret, short_ret, long20_ret,
                 turnover, len(usable)))

    def _turnover(self, spec, weights, outcomes):
        previous = self.previous_weights.get(spec) or {}
        self.previous_weights[spec] = weights
        if not previous:
            return 1.0
        grown = {s: w * (1.0 + outcomes.get(s, 0.0)) for s, w in previous.items()}
        gross = sum(abs(v) for v in grown.values())
        target = sum(abs(v) for v in previous.values()) or 1.0
        if gross > 0:
            grown = {s: v / gross * target for s, v in grown.items()}
        names = set(grown) | set(weights)
        return 0.5 * sum(abs(weights.get(n, 0.0) - grown.get(n, 0.0)) for n in names)

    def OnEndOfAlgorithm(self):
        self.Log(f"=== ALPHA BATTERY SHORT | universe={ACTIVE_UNIVERSE} ===")
        self.Log(f"cap_rows={self.cap_rows} cap_fallback={self.cap_fallback} "
                 f"cap_missing={self.cap_missing}")
        order = sorted(self.results)
        index_of = {spec: i for i, spec in enumerate(order)}
        # SCALED INTEGERS. QuantConnect's log cap is about 100KB, measured:
        # a 283-char-per-row layout truncated at 359 of 1,311 dates, while
        # the monthly battery's 76KB survived intact. Decimal text is the
        # expensive part, so IC is emitted in units of 1e-4 and returns in
        # 1e-5 -- both far finer than the quantities they carry. Turnover
        # moves to a per-spec average because it is applied as a mean in
        # the cost model anyway.
        by_date = {}
        for spec, rows in self.results.items():
            for date, ic, lr, sr, l20, turn, n in rows:
                by_date.setdefault(date, {})[index_of[spec]] = (
                    f"{'' if ic is None else int(round(ic * 10000))},"
                    f"{int(round(lr * 100000))},{int(round(sr * 100000))}"
                )
        self.Log(f"SPECS|{'|'.join(order)}")
        self.Log("SCALE|ic=1e-4|ret=1e-5")
        self.Log(f"DATES|{len(by_date)}")
        for spec in order:
            rows = self.results[spec]
            turns = [r[5] for r in rows]
            names = sorted(r[6] for r in rows)
            self.Log(f"SPECMETA|{spec}|turnover={round(sum(turns)/len(turns), 4)}"
                     f"|median_names={names[len(names)//2]}|periods={len(rows)}")
        for date in sorted(by_date):
            cells = by_date[date]
            packed = "|".join(f"{i}~{cells[i]}" for i in sorted(cells))
            self.Log(f"ROW|{date.replace('-', '')}|{packed}")
        self.Log(f"orders placed: {self.Transactions.OrdersCount}")
