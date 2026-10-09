# Dataset schemas

All timestamps should be ISO-8601 UTC. Each row must reflect only information available at its `timestamp` / `snapshot_time`.

## `data/contract_outcomes.csv` — model training

Required columns:

- `timestamp`: decision time, used for chronological split.
- `label_yes`: 1 if the contract ultimately settled YES, otherwise 0.
- `distance_pct`: signed percentage distance of current BTC spot from the contract's relevant target. Document one consistent sign convention and keep it identical in training and inference.
- `minutes_remaining`: minutes until the relevant settlement/cutoff.
- `ret_1m_pct`, `ret_5m_pct`, `ret_15m_pct`: BTC returns over those trailing windows.
- `realized_vol_15m_pct`: trailing realized volatility feature.
- `ema_gap_pct`: percentage difference between short and longer EMA.
- `volume_ratio_15m`: latest volume divided by a trailing average.
- `orderbook_imbalance_pct`: imbalance calculated from a point-in-time Kalshi book snapshot, with one documented sign convention.
- `yes_price_cents`: YES price at the prediction timestamp, in cents.

The training script rejects datasets with fewer than 100 valid rows; 300+ is a better starting point but may still be insufficient. Collect diverse market conditions and ensure rows are not duplicated across overlapping contracts in a way that leaks future information.

## `data/market_candidates.csv` — paper candidate scoring

Required columns:

- `ticker`
- `snapshot_time`
- `minutes_remaining`
- `distance_pct`
- `ret_1m_pct`
- `ret_5m_pct`
- `ret_15m_pct`
- `realized_vol_15m_pct`
- `ema_gap_pct`
- `volume_ratio_15m`
- `orderbook_imbalance_pct`
- `yes_price_cents`
- `yes_ask_cents`
- `no_ask_cents`
- `spread_cents`

Prices must be executable ask estimates, not last-traded prices or best bids. If you cannot verify the ask from the live order book, do not create a candidate row. `spread_cents` should represent the actual spread for the intended side using current market mechanics.

## Critical data hygiene

- Never use future candles, final settlement price, later market quotes, or outcomes in the feature columns.
- Build labels only after contracts settle, using verified settlement results and exact rules.
- Separate training and test periods chronologically; consider purging overlapping settlement windows between splits.
- Include estimated fees and conservative slippage when deciding whether an edge is sufficient.
