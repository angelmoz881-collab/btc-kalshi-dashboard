# BTC External Bot Agreement Mode

The live BTC outcome now requires **two different external signal providers** saying the SAME direction on the SAME exact `KXBTC15M` ticker with timestamps no older than 90 seconds. Local predictions are visible as research context but **do not count as external bots**. Missing data, different tickers, a reversal in bot votes, an expired vote, a duplicate feed, or strong contradictory local model risk yields **WAIT**.

The original statistical, historical, and adaptive model estimates remain available for diagnostics and chronological settlement-score research. They cannot manufacture an outside-bot vote.

## Supported sources

### 1. SpectralEdge / Cotes AI

This is a documented third-party provider of real-time BTC 15-minute signals, not code copied from a GitHub repo.

- Official documentation: https://spectralbot.cotes.ai/docs/
- Active feed: `GET https://api.cotes.ai/v1/contests/active?series=KXBTC15M`
- Requires an account, an API key, and an active trial or subscription.
- Create the Cotes key through your **Cotes account**, not through Kalshi's API keys. This is a separate provider.
- In Streamlit Cloud **Manage app > Settings > Secrets**:

```toml
COTES_API_KEY = "YOUR_COTES_API_KEY"
```

The feed's own JSON `ticker` must match the active Kalshi ticker, `state` must be `live`, and its most recent pending signal must be less than 90 seconds old. Multiple emissions or model versions **from Cotes** count as one Cotes vote.

### 2. Another independent signal service

If you run/subscribe to a different BTC signal bot with a real hosted HTTPS JSON endpoint, configure:

```toml
BOT_SIGNAL_URL_2 = "https://your-second-bot.example/api/btc/signal"
BOT_SIGNAL_TOKEN_2 = "OPTIONAL_BEARER_TOKEN"
```

The endpoint receives a `GET` query param `ticker=<exact KXBTC15M ticker>` and must reply:

```json
{
  "ticker": "KXBTC15M-EXACT-TICKER",
  "side": "YES",
  "confidence": 0.78,
  "timestamp": "2026-10-18T21:00:00Z",
  "status": "live"
}
```

The JSON above is an *example*, not live data. `side` can be `YES`, `NO`, `UP`, or `DOWN`. Confidence can be 0.78 or 78. Require a timezone-bearing timestamp. Only fresh, high-enough-confidence signals count. Optional 3rd provider uses `BOT_SIGNAL_URL_3` and `BOT_SIGNAL_TOKEN_3`.

**Never count a Kalshi market price or a renamed copy of Cotes' output as an independent outside bot.** Hosts are deduplicated, but it remains the operator's responsibility to confirm providers are genuinely independent. GitHub source repositories do not automatically provide hosted real-time predictions.

## How to use

1. Open the upgraded Streamlit BTC app after merge.
2. In the sidebar, open **🤝 External bot signal feeds** for setup notes.
3. Open the **🤝 BOTS** tab to inspect the actual outside votes, their ages, and provider connection health.
4. A YES/NO directional call appears only after two independent providers agree. If there is only one connected feed, the displayed outcome is **WAIT** — by design.
5. The old bot models are still visible for research, but they are not counted in this quorum.

## Important risk limitations

- Agreement is **not** proof of accuracy, nor does it prove that a profitable 30–45-second scalp exit can be filled.
- Signals are **settlement-direction forecasts** and may not predict profitable early-exit prices.
- This implementation **never sends a live order**. The existing BTC scalp value remains **WAIT**, and Kalshi account connection is read-only. A trading implementation would need a persistent execution worker, actual fill reconciliation, authenticated cancel/reduce-only exit handling, kill switches, position caps and live deployment tests.
- Do not commit any private feed token or Kalshi private key to GitHub. Store credentials in Streamlit Secrets.
- If a service goes down, the app refuses to invent a consensus. Historical code from open-source bots is useful to study, but their code does not constitute a live vote.
