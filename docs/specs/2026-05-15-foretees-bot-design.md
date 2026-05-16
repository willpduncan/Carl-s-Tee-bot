# TeeBot Design Spec — Pine Forest Country Club ForeTees Automation

**Date:** 2026-05-15
**Status:** Draft, pending user approval
**Owner:** Will Duncan (operator), Carl Pfiffner (end user / beneficiary)

---

## 1. Summary

TeeBot is a cloud-hosted automated booking bot for Pine Forest Country Club's ForeTees tee-time system. Carl Pfiffner submits his weekly preferences via email. Every morning at 7:58 AM Central, the bot wakes up, checks whether a request exists for the day-opening window (today + 5 days), and at 8:00:00.000 fires a raw HTTP request sequence to grab the best available slot within Carl's preferences. The bot then emails Carl the result and asks how he wants to handle the other 3 spots in his group.

This is a single-user, single-club system. There is no multi-tenancy.

---

## 2. Problem & User

**The problem:** Pine Forest releases tee times on a rolling 5-day window, with each day's slots opening at 8:00 AM Central. Prime times go in seconds. Carl is 80+, refreshes manually, and consistently loses out to faster members (who appear to use bots themselves).

**The user:** Carl Pfiffner, Pine Forest member. Older, uses email comfortably, prefers minimal technology friction. His grandson (Will) is the operator who maintains the bot.

**Day mapping (verified with Carl):**
- Mon 8 AM → Sat opens for booking
- Tue 8 AM → Sun opens
- Wed 8 AM → Mon opens
- Thu 8 AM → Tue opens
- Fri 8 AM → Wed opens
- Sat 8 AM → Thu opens
- Sun 8 AM → Fri opens

(Offset is +5 days; verify against live site during implementation.)

---

## 3. Goals & Non-Goals

**Goals:**
- Submit ForeTees booking POST within ~200ms of 8:00:00.000 Central, daily
- Allow Carl to specify per-day preferences via email
- Fall back gracefully when preferred slot is unavailable (walk outward within his window)
- Detect bot-defense activation early (DataDome challenge, 403/429) and self-disable to protect Carl's club standing
- Email Carl the result and let him decide partner handling with one click

**Non-goals:**
- Multi-user support
- Multi-club support
- Web UI (replaced by email-in for simplicity)
- Beating sub-50ms bots (a stretch we'll accept)
- Permanent evasion of every bot-detection upgrade ForeTees might deploy

---

## 4. Risks & Constraints

**ToS / club standing risk (PRIMARY):**
- ForeTees almost certainly prohibits automated booking in its ToS
- Pine Forest member rules may also prohibit it
- Detection consequences: ForeTees account flag → account suspension → club discipline against Carl
- **Mitigation:** Defensive instrumentation; immediate self-disable on any detection signal; conservative request shaping; no aggressive retries.

**Bot-detection technical landscape (verified via HAR analysis):**
- `www1.foretees.com` loads DataDome (`api-js.datadome.co`) — currently in passive mode (no `datadome` cookie set, no blocking responses observed)
- Clubhouse Online side has Cloudflare Bot Management — also passive
- DataDome could flip to active mode at any time, especially during peak 8 AM windows
- **Mitigation:** monitor for `datadome` cookie issuance, `403`, `429`, or response-shape changes. Hard-stop on any of these.

**Credential handling:**
- ForeTees credentials (`Pfifftex` / current password) live in `/etc/teebot/secrets.env` with `chmod 600`
- Rotate password once after deployment (the version shared during design is now considered "transmitted")
- Never logged, never committed to git
- `.gitignore` excludes secrets, DB, HAR captures

**Single point of failure:**
- One VPS, one Gmail relay. If either is down at 8 AM, the bot misses that day's window.
- **Mitigation:** uptime monitor (UptimeRobot free tier) pings the VPS every 5 min and alerts on outage.

---

## 5. Architecture Overview

Three independent processes on one $5/mo VPS (DigitalOcean droplet, Ubuntu 24.04):

```
┌─────────────────────┐
│ Carl's Gmail        │
│ cpfiffner62@gmail   │
└────┬────────────▲───┘
     │ sends      │ receives
     │ request    │ booking result + partner Q
     │ email      │
     ▼            │
┌─────────────────┴───┐         ┌──────────────────────┐
│ TeeBot Gmail        │ ◄───────│  email-poller        │
│ teebotcarl@gmail    │  IMAP   │  (systemd timer,     │
└────┬────────────────┘         │   every 30s)         │
     │                          │  - parse request     │
     │ SMTP                     │  - write to DB       │
     │ outbound                 │  - parse partner     │
     ▼                          │    follow-up replies │
┌─────────────────────┐         └──────────┬───────────┘
│ Carl's Gmail        │                    │
└─────────────────────┘                    │
                                           ▼
                                ┌──────────────────────┐
                                │  SQLite DB           │
                                │  /var/lib/teebot/    │
                                │     teebot.db        │
                                └──────────┬───────────┘
                                           │
                                           ▼
                                ┌──────────────────────┐
                                │  booker              │
                                │  (systemd timer,     │
                                │   daily 7:58 AM CT)  │
                                └──────────┬───────────┘
                                           │ HTTPS
                                           ▼
                                ┌──────────────────────┐
                                │  pfcc.clubhouseonline│
                                │  www1.foretees.com   │
                                └──────────────────────┘
```

**Process boundaries:**
- `email-poller.py` — IMAP poll every 30s, parse incoming emails, write DB rows, send confirmation/acknowledgement replies
- `booker.py` — fires daily at 7:58 AM Central (`systemd` timer with `OnCalendar=*-*-* 07:58:00 America/Chicago`), runs the full 5-phase booking sequence
- `partner-handler.py` — folded into `email-poller.py` (since it's also reading the same inbox)

No web server, no FastAPI, no HTTPS termination, no domain. Just three Python scripts, SQLite, and Gmail.

---

## 6. Components

### 6.1 Bot Gmail account
- Create a new free Gmail: `teebotcarl@gmail.com` (or similar, pending availability)
- Generate a Gmail **app password** for IMAP + SMTP access (regular password won't work)
- Stores nothing sensitive — only request emails and outbound copies

### 6.2 email-poller.py
- Connects via IMAP to bot Gmail every 30s
- Lists INBOX, fetches new messages since last poll
- **Sender filter:** only processes messages where `From: cpfiffner62@gmail.com`. Other senders are marked-read and ignored.
- Each new message is classified:
  - **Request email** (subject contains "tee time" or "request" or body matches request grammar)
  - **Partner follow-up reply** (in-reply-to a confirmation message-id we previously sent — tracked via DB)
- Parsed via lenient regex (see §8 for grammar)
- Writes parsed result to DB
- Replies to sender with acknowledgement or "I couldn't parse this, here's the format"
- Marks message as read

### 6.3 booker.py
- Triggered by `systemd` timer at 07:58:00 Central daily
- Checks DB: `SELECT * FROM requests WHERE target_date = today + 5 days AND status = 'pending'`
- If none → log "no request, exiting" and quit
- If found → run the 5-phase sequence (§7)
- All HTTP via `httpx` with realistic User-Agent and connection reuse
- After booking attempt, writes a `bookings` row and sends the result email

### 6.4 SQLite database

Located at `/var/lib/teebot/teebot.db`. Four tables.

**`requests`** — Carl's pending and historical booking requests

```sql
CREATE TABLE requests (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  target_date     TEXT NOT NULL,   -- ISO 'YYYY-MM-DD'
  course          TEXT NOT NULL,   -- 'Green' | 'Gold' | 'White'
  preferred_time  TEXT NOT NULL,   -- 'HH:MM' 24h
  window_start    TEXT NOT NULL,   -- 'HH:MM' 24h
  window_end      TEXT NOT NULL,   -- 'HH:MM' 24h
  status          TEXT NOT NULL,   -- 'pending' | 'attempted' | 'succeeded' | 'failed' | 'cancelled'
  source_message_id TEXT,          -- IMAP message-id of Carl's request email
  created_at      TIMESTAMP NOT NULL,
  updated_at      TIMESTAMP NOT NULL,
  UNIQUE(target_date, status) ON CONFLICT REPLACE   -- one pending request per date
);
```

Note: the unique constraint enforces "one pending request per target_date" — a new pending request for the same date *replaces* the previous one. Once status moves off 'pending', the row is preserved as history and the constraint no longer applies.

**`bookings`** — what actually happened

```sql
CREATE TABLE bookings (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id               INTEGER NOT NULL REFERENCES requests(id),
  target_date              TEXT NOT NULL,
  booked_time              TEXT,         -- 'HH:MM' actual booked slot
  course                   TEXT,
  foretees_reservation_id  TEXT,
  partner_status           TEXT NOT NULL DEFAULT 'pending_choice',
                                         -- 'pending_choice' | 'leave_open' | 'all_tbd' | 'names_provided'
  partner_names            TEXT,         -- JSON array; NULL until set
  attempt_count            INTEGER NOT NULL DEFAULT 0,
  booking_latency_ms       INTEGER,      -- T+0 to confirmed booking
  confirmation_message_id  TEXT,         -- Message-ID of the email we sent Carl
  failure_reason           TEXT,         -- NULL on success
  created_at               TIMESTAMP NOT NULL
);
```

**`audit_log`** — every HTTP step + every state change

```sql
CREATE TABLE audit_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp    TIMESTAMP NOT NULL,
  event_type   TEXT NOT NULL,
  request_id   INTEGER REFERENCES requests(id),
  booking_id   INTEGER REFERENCES bookings(id),
  details      TEXT,            -- JSON: request, response status, timing, errors
  success      BOOLEAN NOT NULL
);
```

**`config`** — single-row table for runtime flags

```sql
CREATE TABLE config (
  id            INTEGER PRIMARY KEY CHECK (id = 1),
  bot_enabled   BOOLEAN NOT NULL DEFAULT 1,   -- kill switch
  use_browser   BOOLEAN NOT NULL DEFAULT 0,   -- v2 Playwright fallback flag
  last_poll_at  TIMESTAMP                     -- last IMAP poll, for backlog detection
);
INSERT INTO config (id, bot_enabled, use_browser) VALUES (1, 1, 0);
```

**Secrets (NOT in DB):** kept in `/etc/teebot/secrets.env`, mode 0600:
- `FORETEES_USERNAME=Pfifftex`
- `FORETEES_PASSWORD=<rotated-post-deploy>`
- `BOT_GMAIL_ADDRESS=teebotcarl@gmail.com`
- `BOT_GMAIL_APP_PASSWORD=<from-Google>`
- `CARL_EMAIL=cpfiffner62@gmail.com`
- `OPERATOR_EMAIL=<Will's email>` for alerts
- `TIMEZONE=America/Chicago`

### 6.5 SMTP sender (utility module)
- Uses bot Gmail's SMTP with app password
- All outbound emails set `Message-ID` and `Reply-To` so we can correlate replies
- Stores sent Message-IDs in DB for tracking partner-followup replies

---

## 7. The 8 AM Booking Sequence (5 phases)

All timing relative to the 8:00:00.000 Central trigger (T+0).

### Phase 1: Pre-flight (T-5 min, 07:55:00)

1. `systemd` fires `booker.service`
2. Query DB for pending request matching `target_date = today + 5 days`
3. Check `bot_enabled` flag in DB (kill switch)
4. If no request OR bot disabled → log + exit
5. Otherwise → continue

### Phase 2: Authentication (T-2 min, 07:58:00)

1. `POST https://pfcc.clubhouseonline-e3.com/login.aspx?ReturnUrl=%2fMember-Central`
   - Form data: `__VIEWSTATE`, `__EVENTVALIDATION`, `username=Pfifftex`, `password=<from-secrets>`
   - (Pre-fetch viewstate via initial GET — required for ASP.NET form auth)
2. Follow 302 redirect chain to Member Central
3. GET Member Central; parse HTML for the ForeTees SSO link/iframe URL
4. Hit the SSO handoff URL → land on `www1.foretees.com`
5. Verify session by GETting a benign ForeTees page (e.g. `/v5/pfcc_golf_m56/member`)
6. Store all cookies in an `httpx.Client` session
7. **Any failure here → log full audit trail, send failure email, exit. No retry within the same run.**

### Phase 3: Warm hold (T-90s to T-5s)

1. Every 20 seconds, GET a benign ForeTees endpoint to keep session alive
2. Do not access the tee sheet for the target date during this phase (avoid early-poll detection)

### Phase 4: Race (T+0 to T+15s)

1. **At T+0 exactly (08:00:00.000):** `GET https://www1.foretees.com/v5/pfcc_golf_m56/Member_sheet?calDate=MM/DD/YYYY&course=-ALL-&showAvail=-1&displayOpt=0` for the target date.
   - Returns ~100 KB of HTML listing all slots for the date
   - Each slot's row contains: `time`, `course`, `ttdata` token, `index`, and JavaScript click-handlers we can parse
2. Parse the HTML. For every available slot extract `time`, `course`, `ttdata`, `index`, `day-of-week`.
3. Build prioritized slot list:
   - Filter: course matches request, time within `[window_start, window_end]`, slot appears bookable (not greyed out)
   - Sort: `abs(slot_time - preferred_time)` ascending
4. For each slot in priority order, submit the booking via `POST https://www1.foretees.com/v5/pfcc_golf_m56/Member_slot` with form-data combining the `callback_map` (always present) + the `slot_submit_map` (per-player) fields:

   **callback_map** (always present, copied from the slot-selection step):
   ```
   lstate=0
   newreq=yes
   displayOpt=0
   showAvail=-1
   ttdata=<slot's token>
   date=YYYYMMDD
   index=<slot index>
   course=<course name, e.g. "Green to Gold">
   returnCourse=-ALL-
   wasP1=&wasP2=&wasP3=&wasP4=&wasP5=
   p5=Yes
   time:0=<slot time, e.g. "9:08 AM">
   day=<day of week>
   contimes=1
   s_c=pfcc
   s_a=0
   s_m=56
   json_mode=true
   ```

   **slot_submit_map fields** (per-player; `%` placeholder expands to `a`, `b`, `c`, `d`):
   ```
   player_a=<Carl Pfiffner full name>
   user_a=6605
   member_id_a=10326
   player_type_a=Member
   pcw_a=CRT          ← cart flag
   p9_a=18            ← 18 holes (not 9)
   custom_disp_a=     ← empty for v1
   guest_id_a=        ← empty for v1
   player_b=TBD       ← spots 2-4 default to TBD; bot tries leaving them blank if "leave open" was Carl's prior pref
   user_b=
   member_id_b=
   player_type_b=TBD
   ... (same pattern for c, d)
   id_list=           ← will be extracted from the slot-form response
   id_hash=           ← will be extracted from the slot-form response
   hide_notes=
   notes=
   ```
   - On success → break out of the slot loop
   - On "slot taken" or duplicate response → try next slot
   - On unexpected response → log + abort

5. Total wall-clock budget: ~15s. If exhausted, mark request `failed`.

**Note on response-shape uncertainty:** the EXACT format of the success response (JSON shape, status code, confirmation-id field) is not fully known from the HAR — the captured session did not include a real submit. Success-detection logic must be defensive: parse the response, check for any explicit `error` / `failure` keys, but if shape is unexpected, fall back to "did we get the auto-confirmation email from ForeTees within 90s?" (or, if Carl has not configured forwarding, mark as "uncertain — please verify manually").

### Phase 5: Confirm (T+1s to T+30s)

1. On success: parse `foretees_reservation_id` from response
2. Write `bookings` row
3. Send Carl the booking-result email (§8.2)
4. **Cross-check** (optional, requires Carl-side setup): if Carl sets up a Gmail filter forwarding all `auto-send@foretees.com` messages to `teebotcarl@gmail.com`, the bot can confirm bookings by detecting the forwarded auto-confirmation. Absent this filter, we rely solely on the booking POST response for confirmation. Recommend adding the filter; not a v1 hard requirement.

### Defensive instrumentation (running throughout)

- Every HTTP request → `audit_log` row with timing, status, response fingerprint
- **HARD STOP triggers** — bot sets `bot_enabled=false` in DB, sends Will a "POSSIBLE DETECTION" email, and refuses to fire again until manually re-enabled:
  - Any response sets a `datadome` cookie
  - Any response status in `{401, 403, 429}`
  - Response body contains `"captcha"` or `"verification"` keywords
- **Soft alert (no auto-disable):** two consecutive booker runs return zero successful bookings → email Will a "two failures in a row" alert. v1 manual response; v2 flips a `use_browser=true` flag and the next run uses Playwright + `playwright-stealth` instead of raw HTTP.

---

## 8. Email Flows

### 8.1 Inbound: weekly request

**Expected format (Carl emails to `teebotcarl@gmail.com`):**

```
Subject: tee time

Day: Sunday May 24
Course: Green
Window: 8:00 AM to 10:00 AM
Preferred: 9:00 AM
```

**Lenient parser accepts variations:**
- `Sunday, Green, 8-10 AM, prefer 9`
- `Sun 5/24 Green between 8 and 10, ideally 9`
- Bullet lists, paragraphs, all-caps

**Parse pipeline:**
1. Normalize body (strip signatures, lowercase, collapse whitespace)
2. Extract day-of-week or absolute date → resolve to a specific `target_date` within next 7 days
3. Extract course (one of Green/Gold/White; on Thursday auto-restrict to Green/Gold)
4. Extract two times → assign to `window_start`/`window_end`
5. Extract preferred time → must fall within window
6. Validate; if any field missing or ambiguous → reply with error + format example

**Confirmation reply (within 1 minute):**

```
Got it, Carl.

Day:       Sunday, May 24
Course:    Green
Window:    8:00 AM to 10:00 AM
Preferred: 9:00 AM

I'll try to book this at 8:00 AM Central on Tuesday morning.

To cancel, reply with "cancel".
To change, just send a new email — the latest one wins.
```

**Upsert behavior:** if a `pending` request exists for the same `target_date`, the new one replaces it.

### 8.2 Outbound: booking result

**Success:**

```
Subject: ✓ Booked - Sunday May 24 at 9:08 AM

Hi Carl,

You're in:

  Date:    Sunday, May 24, 2026
  Time:    9:08 AM
  Course:  Green
  Group:   Carl Pfiffner (you) + 3 TBD

You'll also get the official ForeTees confirmation email separately.

What do you want to do with the other 3 spots?

Reply to THIS email with one of these:

  • "leave open"   - Other 3 spots stay empty
  • "TBD"          - Mark all 3 as TBD (placeholder)
  • "names: Bob, Tom, Jim"  - Add specific names

Or reply with "nothing" / ignore this email - I'll do nothing.
```

**Failure:**

```
Subject: ✗ Couldn't book Sunday May 24

Hi Carl,

I tried to book Sunday May 24 between 8:00-10:00 AM on Green
but no slots in your window were available.

What WAS available:
  - 10:24 AM Green
  - 10:32 AM Green
  - 7:36 AM Gold

You can book one of these manually at foretees.com, or
send a new request with a wider window.
```

### 8.3 Inbound: partner follow-up reply

- Email-poller matches incoming replies by `In-Reply-To` header against `bookings.confirmation_message_id`
- Body classification (lenient regex):
  - "leave open" / "open" / "empty" → set `partner_status='leave_open'`
  - "tbd" / "all tbd" / "3 tbd" → set `partner_status='all_tbd'`
  - "names: A, B, C" / "names A and B" → parse out names, set `partner_status='names_provided'`, store array
- If parsed names: log into ForeTees again, update the reservation with the names, confirm in reply
- If "leave open" or "TBD" parsed: most cases require ForeTees side-update too (TBD is the default at booking time, "leave open" requires deleting the placeholders)
- If parse fails → reply with the format reminder

---

## 9. Error Handling & Edge Cases

| Case | Handling |
|---|---|
| No request submitted by 8 AM | Booker logs "no request," exits cleanly. No email. |
| Login fails (bad credentials) | Audit log, "credentials may have changed" email to Will, abort |
| Network slow / ForeTees down | 30s timeout per HTTP call, "couldn't reach ForeTees" email, abort |
| Tee sheet returns empty | Email Carl "ForeTees showed no slots at 8 AM - unusual, check manually" |
| No slots match window | Failure email with what WAS available (Carl decides manually) |
| DataDome cookie issued OR 403/429 OR captcha keyword | HARD STOP, bot disabled, alert email to Will |
| ForeTees changes response shape | Detect via response-fingerprint check, abort + alert |
| Carl emails twice same target_date | Upsert (latest wins), reply acknowledges replacement |
| Carl emails "cancel" | Delete pending request matching most recent inbound thread |
| Malformed request email | Polite reply with format example, no DB write |
| Reply from non-Carl sender | Silently mark-read + ignore (no DB write, no reply) |
| Reply received but no matching `In-Reply-To` | Treat as a new request; if it doesn't parse as one, reply with format example |
| Two consecutive booking failures | Set `use_browser=true` flag for next run (Playwright fallback, v2) |
| Carl forgets to specify preferred time | Use midpoint of window as preferred |
| Carl forgets to specify course | Reply asking for course; no DB write |

---

## 10. Operational

### 10.1 First-run validation (mandatory before live use)

Before relying on the bot for a real, competitive 8 AM booking, run this controlled test exactly once:

1. Pick a **low-stakes target**: a weekday afternoon ~5-6 days out where Pine Forest typically has wide availability and no demand pressure (e.g., a Tuesday 3:00 PM tee time). The goal is to verify the bot's behavior, not to actually play.
2. Carl emails the bot with a request for that low-stakes slot.
3. The booker fires at 7:58 AM the corresponding morning (5 days before the target day).
4. **Within 10 minutes of the bot reporting success**, Carl logs into ForeTees and cancels the test reservation manually. This:
   - Validates that the booking was real and visible in ForeTees (not a falsely-reported success)
   - Trains Carl on the cancel UI flow (he'll need it as the safety net)
   - Releases the slot back for other members
5. Will reviews the `audit_log` table to:
   - Confirm the success-response shape we observed
   - Compare booking latency against design target
   - Spot any unexpected requests/responses
6. **Only after a clean first-run test is the bot eligible for a competitive Monday booking.**

If the first run fails or returns ambiguous data, treat that as new information and revise the implementation before trying again.

### 10.2 Manual-cancel safety net

This is the always-on fallback regardless of test status. Carl should know how to cancel a wrong booking from his phone:

1. Go to `pfcc.clubhouseonline-e3.com` → log in → ForeTees → his name → "Tee Times" → "Make Change or View Tee Times"
2. Find the reservation in the upcoming list
3. Click the entry → "Cancel" → confirm

Print this on an index card and keep it next to Carl's computer. The whole flow is <10 seconds once familiar.

### 10.3 Hosting

**Hosting:**
- DigitalOcean Droplet, $4-6/mo, NYC1 or DAL1 (Dallas is geographically closer to Pine Forest, may help by single-digit ms for the 8 AM race)
- Ubuntu 24.04 LTS, Python 3.12
- `systemd` for service supervision

**Files on the VPS:**
- `/opt/teebot/` — code (git-cloned)
- `/var/lib/teebot/teebot.db` — SQLite database
- `/etc/teebot/secrets.env` — credentials, mode 0600
- `/var/log/teebot/` — file logs (also in journalctl)

**Backups:**
- Nightly cron: `sqlite3 teebot.db ".backup /var/lib/teebot/backup-$(date +\%Y\%m\%d).db"`
- Weekly: `rclone` the backup file to Will's Google Drive or local machine

**Monitoring:**
- UptimeRobot pings the VPS health endpoint every 5 min (we'll expose a trivial `/health` via a single-file Python script on port 8080)
- `systemd` failure → emails Will (using a systemd OnFailure handler)
- Weekly digest email: count of bookings attempted, succeeded, failed, with response time stats

**Kill switch:**
- `sqlite3 teebot.db "UPDATE config SET bot_enabled = 0"` immediately stops all booking attempts
- Will documents this command in `/opt/teebot/EMERGENCY.md` so it's easy to recall when stressed

**Logs retention:**
- Full audit_log retained 90 days
- Beyond 90 days: compressed to monthly summaries

---

## 11. Open Questions / Not-Yet-Verified

None of these are hard blockers anymore (a second HAR is no longer required), but each should be confirmed empirically during the designated first-run test (see §10.1):

1. **Success-response shape for booking POST.** Predicted format: JSON with confirmation fields. To be verified live during the first-run test.
2. **"Slot taken" response shape.** Predicted: JSON with an error/already-booked field. Verified live.
3. **`id_list` and `id_hash` field values.** These come from the slot-form-render response (HTML returned by clicking a slot). Implementation must parse them out of that response before submitting.
4. **Cancel endpoint format.** Not captured in HAR. Carl can cancel manually via the ForeTees UI if needed — bot doesn't need to cancel programmatically in v1.
5. **Bot Gmail account.** Will needs to create `teebotcarl@gmail.com` (or available alternative) and generate an app password.
6. **VPS provisioning.** Will needs DigitalOcean account + credit card; documented setup steps will live in `docs/setup.md`.
7. **Day offset verification.** Carl said the offset is +5 days; Carl's earlier message said +6. To be verified by inspecting the live calendar.
8. **Confirm time-slot granularity.** ForeTees appears to use 8-minute slots at Pine Forest based on the HAR. Verify against the calendar UI.
9. **Password rotation.** Pine Forest password should be rotated once after deploy (since the current value was transmitted through chat).

---

## 12. Future Work (not in v1)

- Playwright-stealth fallback path (when raw HTTP gets blocked)
- Multi-day weekly schedule (Carl pre-loads a full week of preferences once)
- Standing weekly recurring requests ("every Sunday at 9 AM on Green")
- Web dashboard for Will showing audit log + recent bookings
- Carl-facing dashboard (replacing or augmenting email)
- Speed assist mode (browser bookmarklet for Carl when bot is disabled)
- SMS notifications via Twilio if email proves too slow for partner follow-up

---

## 13. Decision Log

| Decision | Rationale |
|---|---|
| Approach B (raw HTTP) over A (browser) | DataDome appears passive on Pine Forest's ForeTees; raw HTTP offers ~10x speed advantage at the critical 8 AM moment; we accept higher detection risk in exchange for higher chance of beating other bots |
| Defensive instrumentation + auto-disable | Carl's club standing is more valuable than any individual missed tee time |
| Email-in instead of web form | Carl already uses email comfortably; no domain/HTTPS setup needed; reduces operator maintenance |
| SQLite over Postgres | Single-user system; one writer; SQLite is plenty |
| DigitalOcean over AWS Lambda | Playwright-stealth fallback (v2) is heavy for Lambda; a always-on VPS allows session warm-up |
| Gmail for inbound + outbound | Free, reliable, no domain needed, supports app passwords |
| No retries on detection signal | Detection escalates; one trigger should pause entirely until human review |
