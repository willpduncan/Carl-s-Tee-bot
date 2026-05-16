# TeeBot Emergency Runbook

## Kill switch — disable the bot immediately

```bash
ssh root@<VPS-IP>
sqlite3 /var/lib/teebot/teebot.db "UPDATE config SET bot_enabled=0"
```

This stops all future booking attempts. The poller still runs (so Carl's emails are still acknowledged), but the booker exits immediately on its next 8 AM fire.

## Common scenarios

### "Carl just got a booking he didn't want"

He cancels manually in ForeTees:
1. pfcc.clubhouseonline-e3.com → log in → ForeTees → his name → "Tee Times" → "Make Change or View Tee Times"
2. Find the reservation → "Cancel" → confirm

### "I got a POSSIBLE DETECTION email"

1. Bot has already self-disabled (`bot_enabled=0`)
2. SSH to VPS, check the audit_log:
   ```bash
   sqlite3 /var/lib/teebot/teebot.db "SELECT timestamp, event_type, details FROM audit_log ORDER BY id DESC LIMIT 50"
   ```
3. Look for the trigger (datadome cookie, 403/429, captcha keyword)
4. Decide: pause for a week and see if DataDome stays active, or move to browser automation fallback

### "Booker missed the 8 AM run"

```bash
journalctl -u teebot-booker.service -n 200
systemctl list-timers | grep teebot
```

Possibilities: VPS was down, network was out, login failed (bad password). Manually rerun:
```bash
sudo -u teebot bash -c "set -a; source /etc/teebot/secrets.env; set +a; cd /opt/teebot && .venv/bin/python scripts/run_booker.py"
```

### "Carl's password changed"

Update `/etc/teebot/secrets.env`, then restart the timer:
```bash
systemctl restart teebot-booker.timer teebot-poller.timer
```

### "Bot keeps booking the wrong slot"

Most likely: the parser is misreading Carl's email. Check the latest request:
```bash
sqlite3 /var/lib/teebot/teebot.db "SELECT * FROM requests ORDER BY id DESC LIMIT 1"
```

If `course`, `window_start`, `window_end`, or `preferred_time` don't match what Carl typed, look at his email body and tighten the parser's regex.

## Re-enabling after a kill switch

Once you've investigated:
```bash
sqlite3 /var/lib/teebot/teebot.db "UPDATE config SET bot_enabled=1"
```

Then send a test request to verify everything still works.
