# First-Run Validation Protocol

Before relying on TeeBot for a competitive Monday booking, you MUST complete this controlled live test once. This validates the success-response shape and trains Carl on the manual-cancel path.

## Step 1: Pick a low-stakes target

Choose a **Tuesday afternoon ~5-6 days out** where Pine Forest has wide availability and zero demand pressure. Example: Tuesday at 3:00 PM on the Green course.

## Step 2: Carl sends the request

From `cpfiffner62@gmail.com`, email `teebotcarl@gmail.com`:

```
Subject: tee time

Day: Tuesday <date>
Course: Green
Window: 2:30 PM to 4:00 PM
Preferred: 3:00 PM
```

Wait for the confirmation reply (within ~60s). Verify it matches what was sent.

## Step 3: Wait for the booker fire

On the **morning 5 days before the target day**, the booker fires at 7:58 AM Central. Watch via SSH:

```bash
ssh root@<VPS-IP>
journalctl -u teebot-booker.service -f
```

You should see auth, warm hold, race, slot attempts. The whole sequence takes ~30-60 seconds.

## Step 4: Verify the booking exists

After the booker emails Carl success:

1. Carl logs into ForeTees and confirms the reservation is visible under his name at the booked time/course.
2. Will (operator) inspects the audit log:
   ```bash
   sqlite3 /var/lib/teebot/teebot.db "SELECT timestamp, event_type, details FROM audit_log WHERE timestamp >= datetime('now', '-1 hour') ORDER BY id"
   ```
3. Note the `booking_attempted` row and the success-response body in `details`. This is the canonical success format we'll trust going forward.

## Step 5: Carl cancels the test reservation immediately

Within 10 minutes:
1. pfcc.clubhouseonline-e3.com → ForeTees → his name → "Tee Times" → "Make Change or View Tee Times"
2. Find the test reservation → click Cancel → confirm
3. Verify the slot is released

## Step 6: Sign off

In this file (`docs/first_run.md`), add a line below recording the test outcome:

```
- Test booking 2026-MM-DD: <success/failure>. Booking latency XXXms. Success-response confirmed at audit_log.id=NNNN.
```

The bot is then cleared for competitive Monday use.

## If the test fails

- Booker errored out → check journalctl, fix the issue, repeat the test.
- Booking succeeded but no email arrived → SMTP issue, check `mailer.py` / app password.
- Booking succeeded but DB shows `failure` → response-shape mismatch in `submit_booking`, update the success heuristic in `src/teebot/foretees/booker.py`.
- Slot wasn't actually reserved in ForeTees → false-positive success classifier, same fix.
- **Most likely failure mode:** the tee-sheet parser doesn't find any slots in the real ForeTees response (the test fixture was synthesized from incomplete HAR data — see Task 10 note). To fix: SSH to VPS, run `.venv/bin/python -c "from teebot.foretees.session import ForeTeesSession; from teebot.foretees.auth import login; from teebot.foretees.tee_sheet import fetch_tee_sheet_html; import os; from datetime import date, timedelta; s = ForeTeesSession(); login(s, username=os.environ['FORETEES_USERNAME'], password=os.environ['FORETEES_PASSWORD']); html = fetch_tee_sheet_html(s, date.today() + timedelta(days=5)); open('/tmp/live_tee_sheet.html','w').write(html); print(len(html))"`. Then inspect `/tmp/live_tee_sheet.html` to see how slots are actually encoded, and update `parse_tee_sheet()` accordingly.

## Sign-off log

(append test results here as they happen)
