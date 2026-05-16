# TeeBot Emergency Runbook (Railway deployment)

## Kill switch — disable the bot immediately

Using the Railway CLI (install once: `npm install -g @railway/cli`, then `railway login && railway link`):

```bash
railway run sqlite3 /data/teebot.db "UPDATE config SET bot_enabled=0"
```

This stops all future booking attempts. The poller still runs (so Carl's emails are still acknowledged), but the booker exits immediately on its next 8 AM fire.

**Alternative — pause the whole service** from the Railway dashboard:
- Project → Service → **Settings** → **Pause Service**

This stops everything (poller too). Use this if you suspect the bot is doing something actively harmful.

---

## Common scenarios

### "Carl just got a booking he didn't want"

He cancels manually in ForeTees:
1. https://pfcc.clubhouseonline-e3.com → log in → ForeTees → his name → "Tee Times" → "Make Change or View Tee Times"
2. Find the reservation → click **Cancel** → confirm

### "I got a POSSIBLE DETECTION email"

1. The bot has already self-disabled (`bot_enabled=0`)
2. Check the audit log via Railway CLI:
   ```bash
   railway run sqlite3 /data/teebot.db \
     "SELECT timestamp, event_type, details FROM audit_log ORDER BY id DESC LIMIT 50"
   ```
3. Look for the trigger (datadome cookie, 403/429, captcha keyword)
4. Decide: pause for a week and see if DataDome stays active, or move to a browser-automation fallback (v2 work).

### "Booker missed the 8 AM run"

Check Railway logs from the dashboard, or:
```bash
railway logs
```

Possibilities: container was restarting, network was out, login failed (bad password). Manually rerun:
```bash
railway run python scripts/run_booker.py
```

### "Carl's password changed"

Update the env var in Railway:
1. Dashboard → Service → **Variables** tab
2. Edit `FORETEES_PASSWORD`
3. Railway auto-redeploys

### "Bot keeps booking the wrong slot"

Most likely: the parser misread Carl's email. Check the latest request:
```bash
railway run sqlite3 /data/teebot.db \
  "SELECT * FROM requests ORDER BY id DESC LIMIT 1"
```

If `course`, `window_start`, `window_end`, or `preferred_time` don't match what Carl typed, look at his email body and tighten the parser's regex (`src/teebot/parser.py`), then `git push` to redeploy.

### "Tee-sheet parsing returns 0 slots"

This is the most likely first-run failure (see [first_run.md](first_run.md) — the fixture was synthetic). Diagnostic:

```bash
railway run python -c "
from teebot.config import Config
from teebot.foretees.session import ForeTeesSession
from teebot.foretees.auth import login
from teebot.foretees.tee_sheet import fetch_tee_sheet_html
from datetime import date, timedelta
cfg = Config.from_env()
s = ForeTeesSession()
login(s, username=cfg.foretees_username, password=cfg.foretees_password)
html = fetch_tee_sheet_html(s, date.today() + timedelta(days=5))
print(html[:2000])
print('---')
print(f'Total length: {len(html)}')
"
```

Inspect the real HTML structure and update `parse_tee_sheet()` in `src/teebot/foretees/tee_sheet.py`, then `git push` to redeploy.

---

## Re-enabling after a kill switch

Once you've investigated:
```bash
railway run sqlite3 /data/teebot.db "UPDATE config SET bot_enabled=1"
```

Then send a test request from Carl's account to verify everything still works.
