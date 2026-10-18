# Bot Arena: BTC/Kalshi research upgrade

This branch preserves the BTC chart, independent expiry countdown, hourly forecasts, FLOW tab, learning archive, mobile layout and separate Gold page. It adds a new **🏆 ARENA** section and never creates real-money orders.

## Improvements

- Six competing observed forecast signals: volatility/strike, historical analogs, flow/candles, Kalshi market consensus, existing base fusion, and adaptive learner.
- Fixed checkpoint scoring: select the original pre-settlement snapshot nearest five minutes remaining, at most one per unique settled contract. This prevents multiple snapshots of one market from falsely inflating hit rates.
- Brier scores (lower is better), directional accuracy, and 95% Wilson intervals, with small sample sizes flagged.
- Quote-independent value: 65% volatility/strike, 25% analogs, 10% flow/candles. Kalshi's quoted price is **not** reused inside the supposedly independent fair-value estimate.
- A fixed alternate blend (70% original prediction + 30% independent) is unlocked only after 120 distinct settled markets, with improvement over the existing bot's Brier score in both chronological 60-market evaluation halves. Until then, the original core outcome predictor is untouched.
- Conservative one-contract paper filters for venue disagreement, stale feeds, high volatility, Kalshi trading status, too little time, orderbook depth, spreads and execution cost.
- No new required dependencies for the Streamlit app.

## Install

1. Review and merge the feature/bot-arena-v5 pull request.
2. Restart the same Streamlit deployment that runs dashboard.py.
3. Open the new 🏆 ARENA tab. Existing CHART remains the default.
4. Ensure the existing learning-data persistence is configured and official Kalshi settlements are being attached. This branch does not change or request your secrets.
5. Optionally export the settled learning CSV and run the standalone offline comparison:

    python arena_report.py --history data/btc_kalshi_learning.csv

6. For local tests:

    pip install pytest
    python -m pytest -q tests/test_arena_core.py

The GitHub Actions workflow bot-arena-tests.yml compiles Python sources and runs regression tests when changes are pushed.

## Ideas compared from public open-source systems

- SiddhaBasu/kalshi-bot: chronological validation, calibration and order-book execution.
- oribarlevco-cell/kalshi-btc-15m-bot: settlement journals and multi-strategy paper comparisons.
- TylerShep/quant-kbtc: order-book imbalance and volatility-regime restrictions.
- Freqtrade/FreqAI: lookahead-bias protection and retraining validation.
- Kalshi official documentation: bid-only orderbook semantics; NO bids imply YES asks.

This is original implementation informed by those patterns, not a wholesale import of unverified bots.

## Risk and reliability

- **No demonstration of superior profitability yet.** Unit tests use synthetic data; they are not historical P&L results.
- Official Kalshi settlement on the BTC 15-minute series references CF Benchmarks BRTI averaging, which public Coinbase and multi-exchange proxy data may not match precisely.
- Paper EV uses a **3 cent assumed fee allowance and 2 cent slippage buffer**. Those assumptions are NOT a verified market fee schedule or a promise of executable pricing.
- A low Brier score is a good probability forecast but NOT proof of profitable trading after spreads, fees, and fills.
- The original short-term scalp feature remains WAIT because predicting settlement is not the same as predicting profitable early contract exits.
- The Streamlit session does not magically keep collecting and learning after it has stopped. Persistent unattended capture would require a separately configured backend and authenticated storage, neither of which is installed by this branch.
- If the alternate model does not meet verification gates, it is intentionally not promoted. The safe decision can still be NO TRADE.
