# Alpha explanations

Status: plain-language research glossary. Nothing in this file is a promise of profit, a trading recommendation, or evidence that an alpha works. As of 2026-08-17, every result from the affected local and QuantConnect rounds is invalid or pending a clean reviewed rerun.

An **alpha** is simply a rule that tries to rank investments. A high score means “this rule prefers this stock.” It does not mean the stock will rise.

## Momentum over 3, 6, 9, or 12 months, skipping the latest month

- **What it asks:** Has this stock risen more than other stocks over the chosen past period, while ignoring the most recent month?
- **What a high score means:** The stock has been a stronger recent winner.
- **Main trap:** A winner can reverse suddenly. The answer also changes if old prices, delisted stocks, or trading costs are handled incorrectly.

## Residual momentum

- **What it asks:** After removing the part of a stock's movement that can be explained by the overall market and its industry, has the leftover movement been strong and steady?
- **What a high score means:** The stock appears to have its own upward trend rather than merely riding a broad market or industry rise.
- **Main trap:** This is easy to calculate incorrectly. Market and industry groups must be known at the time, dates must line up exactly, and the stock must not be included in its own peer average.

## Gross profitability

- **What it asks:** How much gross profit does the company produce compared with the assets it uses?
- **What a high score means:** The company produces more gross profit from each dollar of assets.
- **Main trap:** Accounting data can arrive late or be revised. Using today's data for an old date creates a fake advantage.

## Quality composite

- **What it asks:** Does the company look financially healthy across several measures, such as profitability, cash generation, and balance-sheet strength?
- **What a high score means:** Several quality checks agree that the business looks stronger than its peers.
- **Main trap:** Combining many weak measures can create a score that sounds precise but is not. Every input must have an exact time-available rule.

## Quality momentum

- **What it asks:** Is the company's financial quality improving, not merely high?
- **What a high score means:** Measures such as profitability or cash flow are getting better compared with their earlier values.
- **Main trap:** Financial statements are infrequent and revised. Comparing the wrong publication dates leaks future information.

## Multi-alpha composite

- **What it asks:** Do several different alpha rules agree on the same stock?
- **What a high score means:** The stock ranks well after several standardized scores are combined.
- **Main trap:** Similar rules may repeat the same idea and make agreement look stronger than it is. Missing inputs and score scaling must be frozen before testing.

## Five-day reversal

- **What it asks:** Did a stock fall more than its peers over the last five trading days, making a short bounce possible?
- **What a high score means:** The stock was a recent loser and the rule expects some rebound.
- **Main trap:** Some losers keep falling. Frequent trading can make costs larger than the small expected bounce.

## Industry-adjusted reversal

- **What it asks:** Did a stock fall over five days even after removing the movement of other stocks in its industry?
- **What a high score means:** The stock underperformed its peers, not just a falling industry.
- **Main trap:** Industry membership must be known at the time, the stock must be left out of its own peer average, and small peer groups can be unreliable.

## Abnormal-volume reversal

- **What it asks:** Did a stock fall while trading much more heavily than usual, suggesting a short-lived wave of selling?
- **What a high score means:** The rule sees an unusually busy selloff that might bounce.
- **Main trap:** Heavy volume can signal genuinely bad news rather than panic. Volume history and corporate actions must be aligned correctly.

## MAX-20 and MAX-times-reversal

- **What it asks:** Has the stock had an unusually large one-day gain during the last 20 trading days? The combined version also considers a recent decline.
- **What a high score means:** Depending on the frozen formula, the rule is identifying lottery-like recent behavior or a possible reversal after it.
- **Main trap:** The sign is easy to misunderstand, and the measure can favor very volatile, hard-to-trade stocks.

## REP-H52

- **What it asks:** Is the current price close to the highest price seen over roughly the last year?
- **What a high score means:** The stock is near its 52-week high, which is another way to describe strength.
- **Main trap:** The exact price, adjustment method, scoring date, and next-day entry must be fixed. Otherwise the test can accidentally use information unavailable at the decision time.

## REP-IDV

- **What it asks:** How much of the stock's recent movement remains after removing broad market movement, and how jumpy is that leftover movement?
- **What a high score means:** The frozen hypothesis ranks stocks by this stock-specific volatility measure; the direction of preference must be stated before testing.
- **Main trap:** A sequential or misaligned regression answers a different question. It must use the frozen joint model, exact sessions, and point-in-time market membership.

## Point-in-time post-earnings announcement drift (PEAD), planned

- **What it asks:** After a company reports a genuine earnings surprise, does its price keep moving in the surprise's direction?
- **What a high score means:** The reported surprise was stronger and the rule expects a continued reaction.
- **Main trap:** The announcement timestamp and the version of estimates available before the announcement are essential. Without them, the test can see the future.

## Hierarchical sector-relative momentum, planned

- **What it asks:** Is the stock strong compared with its industry, is the industry strong compared with its sector, and is the sector strong compared with the market?
- **What a high score means:** Strength appears at several levels rather than at only one level.
- **Main trap:** This is several related tests combined together. Historical classifications, level weights, and rebalancing rules must be fixed in advance.

## Cross-sectional overnight persistence, optional

- **What it asks:** Do stocks that repeatedly move in one direction between yesterday's close and today's open continue to show that pattern relative to other stocks?
- **What a high score means:** The stock has had stronger repeated overnight movement.
- **Main trap:** Open prices, time zones, overnight corporate news, spreads, and trading costs matter greatly. It needs a separate daily or intraday test rather than being mixed into a monthly algorithm.

## How to read future results

A result becomes useful only after the formula, dates, universe, costs, comparison benchmark, and number of research attempts were frozen before the run. The code must then be independently reviewed, the exact reviewed source must be run, and the run IDs and file hashes must be saved. Alpaca Paper comes later to test real order behavior; it does not repair a weak historical result.
