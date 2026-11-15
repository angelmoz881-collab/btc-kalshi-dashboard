# AI Trading Desk setup

The AI Trading Desk is an optional, read-only analyst panel. It does not place, edit, or close trades.

## Configure the API key

In the Streamlit app deployment, open **App settings → Secrets** and add:

```toml
OPENAI_API_KEY = "your-private-OpenAI-API-key"
OPENAI_MODEL = "gpt-6"
```

Keep the key in Streamlit Secrets or a server-side environment variable. Do not commit it to this repository or paste it into chat.

If your account does not have access to the default model, set `OPENAI_MODEL` to a model available to your API project.

## Forecast design

- Input: the bot's native 15-minute BTC OHLCV candles (up to the latest 36 bars).
- Horizon: exactly 60 minutes from the time the AI request is made.
- Output: UP / DOWN / UNCERTAIN, confidence, UP probability, expected price, likely range, entry zone, risk references, reasons and risks.
- Refresh: at most once per minute automatically, with a manual refresh button.
- Safety: the AI integration is analysis-only; existing bot signals and trade controls remain separate.

## Forecast journal

Successful calls are appended to `data/ai_forecasts.jsonl`. Each record stores the creation time, target time, input timeframe, horizon, starting price, direction, probability, expected price and range. Actual outcome fields are initially blank and must be matched with later BTC price data before performance statistics can be calculated.

The default local file may not survive an ephemeral hosting restart or redeploy. For durable evaluation, mount persistent storage or set `AI_FORECAST_LOG` to a persistent writable path. OpenAI API usage may incur charges under your API account.
