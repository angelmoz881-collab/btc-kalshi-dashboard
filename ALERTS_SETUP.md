# Optional BTC/Kalshi alerts

This adds **notifications only**. Existing charts, signals, learning, gold
analysis, positions, and trading safeguards are unchanged. **No trades are
placed.** Entry/reversal/pressure alerts are research warnings, not
reliable predictions of future market direction.

## What you'll hear about

- **Cash-out/position safety (highest priority):** TAKE PROFIT, PROTECT
  PROFIT, CASH OUT SOON, PREPARE TO CASH, STOP LOSS REVIEW, EXIT WINDOW
  CLOSING, TIME EXIT REVIEW, LIQUIDITY WARNING, and DATA STALE.
- **Entry watch:** WATCH YES or WATCH NO only after the existing scalp engine
  gives a legitimate watch (never from a WAIT).
- **Early market warnings:** strong BTC buying/selling pressure, execution
  price/flow divergence, conflicting candle/flow signals, and significant
  possible reversal warnings.

To avoid spam, an active alert is sent once per continuous episode. Once it
clears, the same alert can be sent again after a cooldown (45 seconds for
position alerts, 150 seconds for entries, 180 seconds for market signals).
Different status changes can trigger separate warnings; high-priority position
warnings may bypass the normal 12-second global notification gap.

## Built-in popups

On the BTC dashboard, open **Settings → 🔔 Alerts · phone and in-app**.
The **In-app popup alerts** setting is on by default; use **Test popup alert**
to check it. You can toggle which types to receive.

Popups are visible in the Streamlit app only; they are **not Android system
push notifications** and may disappear when the app isn't foregrounded.

## Optional Android/iPhone notifications via Telegram

1. In Telegram, open the verified **@BotFather** account, use `/newbot`,
   and copy your private bot token.
2. Open the new bot in Telegram and send `/start` to it.
3. Get the chat ID for your own conversation with the bot. One way is to open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` privately after
   sending `/start`, then find `message.chat.id`.
   Never share that URL or token with anyone.
4. In your deployed Streamlit app's **Secrets** settings (not GitHub files or
   code), add:

   ```toml
   TELEGRAM_BOT_TOKEN = "YOUR_PRIVATE_BOT_TOKEN"
   TELEGRAM_CHAT_ID = "YOUR_NUMERIC_CHAT_ID"
   ALERTS_PASSWORD = "a-unique-long-password"
   ```

5. Restart/redeploy Streamlit as needed, open **Settings → 🔔 Alerts**, enter
   `ALERTS_PASSWORD`, enable **Send phone alerts through Telegram**, and
   select **Send test Telegram alert**. Enable Telegram notifications on
   your phone.

The password is mandatory for phone delivery, since a publicly viewable
Streamlit app must not let visitors spam your Telegram chat. Keep secrets
private and never commit your real token, chat ID, or password to GitHub.

**Operational limit:** Alerts are checked only when the BTC Streamlit dashboard
is actively running and refreshing. They are **not 24/7 background monitoring**.
If the browser app is closed, paused, disconnected, or the Streamlit server is
asleep, you may not get alerts. Running a dedicated background service would
be a separate future project. Delivery is best effort, and phone/network
notifications may be delayed or lost. Always verify your actual Kalshi quotes
and positions before acting.
