# NIFTY IV Calendar Spread Monitor

## Purpose
Monitors Implied Volatility (PE IV) of ATM Nifty options across 5 weekly expiries (W1–W5).
Computes IV spreads for 10 defined pairs and fires Telegram alerts when spread crosses ±20%.
Runs Mon–Fri at 4 fixed IST time slots: 09:30, 10:00, 10:30, 11:00.

## Files
- `nifty_iv_monitor.py` — main script (~350 lines)
- `.github/workflows/iv-monitor.yml` — GitHub Actions workflow
- `requirements.txt` — `requests` only

## Environment Variables (GitHub Secrets)
- `TELEGRAM_TOKEN` — Telegram bot token
- `TELEGRAM_CHAT_ID` — Telegram chat/channel ID

## W-Cycle Logic
Reference Tuesday is computed from today's weekday:
- Mon → ref = today + 1
- Tue → ref = today
- Wed → ref = today + 6 (next Tuesday after expiry week shift)
- Thu → ref = today + 5
- Fri → ref = today + 4

W1 = first NSE expiry >= ref_tuesday + 7
W2–W5 = next 4 consecutive NSE expiries

## Pair Order (all 10)
W2/W1, W3/W1, W3/W2, W4/W2, W4/W3, W4/W1, W5/W1, W5/W2, W5/W3, W5/W4

## Spread Formula
`spread = (left_iv - right_iv) / right_iv * 100`
- left = far expiry, right = near expiry
- Alert threshold: ±20%
- spread > +20% → Long Calendar (Long far, Short near)
- spread < -20% → Short Calendar (Short far, Long near)

## IV Source
PE IV (`PE.impliedVolatility`) from NSE option chain API at ATM strike.
Fallback: try ATM±50, ATM±100, then CE IV if PE IV is zero/missing.

## Alert Behaviour
- Each slot is independent (no deduplication across slots)
- All 10 pairs are always checked (no stop-at-first-match)
- Message sent only if at least one pair qualifies
- Startup ping and session-complete always sent (health check)

## Deployment
1. Push to GitHub
2. Add `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` in repo Settings → Secrets
3. Workflow auto-triggers Mon–Fri at 9:25 AM IST via cron `55 3 * * 1-5`
4. Manual trigger via `workflow_dispatch`

## Verification
1. Run `python nifty_iv_monitor.py` at ~9:20 AM IST on a trading day
2. Check console for correct W1–W5 dates
3. Verify PE IV values are in ~8–30% range
4. Manually verify one spread: `(left_iv - right_iv) / right_iv * 100`
5. Telegram messages should arrive at each slot (±30s)
6. Simulate holiday: add today's date to `MARKET_HOLIDAYS` dict in the script
