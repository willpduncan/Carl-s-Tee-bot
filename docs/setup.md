# TeeBot Deployment Guide (Railway)

Step-by-step setup for deploying TeeBot to [Railway](https://railway.app). Estimated time: **~25 minutes**, mostly waiting for the bot Gmail account to be ready.

---

## 1. Pre-deploy: accounts you need

### 1a. Bot Gmail account (already done in this project)

Already created: `carlpfiffnerteebot@gmail.com`. You also need a Gmail **App Password** for IMAP/SMTP:

1. Sign into the bot Gmail account
2. Go to https://myaccount.google.com/security
3. Enable **2-Step Verification** if not already on (App Passwords require it)
4. Go to https://myaccount.google.com/apppasswords
5. Select app **Mail**, device **Other** → name it "TeeBot Railway"
6. Copy the 16-character app password — save it somewhere (you'll paste it into Railway env vars later). Treat it like a real password.

### 1b. GitHub account

You'll push the TeeBot code to a GitHub repo. Railway deploys from GitHub.

- Sign in at https://github.com if you have an account, or create one
- Make a new private repo (name: e.g. `teebot`)
- Don't initialize it with anything — we'll push our existing code

### 1c. Railway account

- Sign up at https://railway.app (free tier exists; the Hobby plan is $5/mo)
- Use "Sign in with GitHub" so Railway can access your repos
- Add a payment method (~$5/mo charge after free trial)

### 1d. Optional: Carl's Gmail filter

In `cpfiffner62@gmail.com`'s settings, add a filter:
- **From:** `auto-send@foretees.com`
- Action: **Forward to** `carlpfiffnerteebot@gmail.com`

This lets the bot cross-check its bookings against ForeTees' official confirmation emails. Optional but recommended.

---

## 2. Push the code to GitHub

From your laptop (in the `/Users/willduncan/teebot` directory):

```bash
cd /Users/willduncan/teebot

# Add GitHub as the remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/teebot.git

# Push the code
git push -u origin main
```

If `git push` asks for a password, use a [GitHub Personal Access Token](https://github.com/settings/tokens) (Settings → Developer settings → Tokens), not your account password.

---

## 3. Create the Railway project

1. Go to https://railway.app/dashboard
2. Click **New Project**
3. Choose **Deploy from GitHub repo**
4. Select your `teebot` repo
5. Railway auto-detects Python via the `pyproject.toml` and `Procfile`. It will start building immediately — let it.

The first build will FAIL because env vars aren't set yet. That's expected. Continue to step 4.

---

## 4. Add a persistent volume

The SQLite database needs to survive restarts.

1. In your Railway project, click on the service
2. Go to **Settings** → **Volumes**
3. Click **+ New Volume**
4. Mount path: `/data`
5. Size: 1 GB (more than enough)
6. Click **Add**

---

## 5. Set environment variables

In the Railway service:

1. Go to **Variables** tab
2. Click **+ New Variable** for each of these (or use Raw Editor):

| Variable | Value |
|---|---|
| `FORETEES_USERNAME` | `Pfifftex` |
| `FORETEES_PASSWORD` | *(Carl's rotated ForeTees password)* |
| `BOT_GMAIL_ADDRESS` | `carlpfiffnerteebot@gmail.com` |
| `BOT_GMAIL_APP_PASSWORD` | *(the 16-char app password from step 1a)* |
| `CARL_EMAIL` | `cpfiffner62@gmail.com` |
| `OPERATOR_EMAIL` | `willpduncan@gmail.com` |
| `TIMEZONE` | `America/Chicago` |
| `DB_PATH` | `/data/teebot.db` |

⚠️ **Important:** `FORETEES_PASSWORD` should be a NEWLY ROTATED password — don't reuse the one shared during development.

After saving, Railway will redeploy automatically.

---

## 6. Initialize the database

The SQLite file doesn't exist yet on the volume. Use the Railway CLI (one-time setup):

```bash
# Install Railway CLI
npm install -g @railway/cli

# Link to your project
railway login
railway link

# Run the init script in the deployed environment
railway run python scripts/init_db.py
```

You should see: `Initialized schema at /data/teebot.db`

(Alternative: temporarily change the start command in railway.toml to `python scripts/init_db.py && python scripts/run_daemon.py`, deploy, then revert.)

---

## 7. Verify the daemon is running

In Railway's **Logs** tab, you should see (within ~30s of deploy):

```
Daemon starting — poll every 30s, booker window 7:58–7:59 Central
```

Then every 30 seconds the poller fires (silent unless emails arrive, but no errors either).

---

## 8. Send a test email from Carl's account

From `cpfiffner62@gmail.com`, email `carlpfiffnerteebot@gmail.com`:

```
Subject: tee time

Day: <next Tuesday's date>
Course: Green
Window: 2:00 PM to 4:00 PM
Preferred: 3:00 PM
```

Within ~30 seconds, Carl should get a confirmation reply: "Got it, Carl. Day: Tuesday … Course: Green …"

If Carl gets that reply, **the bot is online and processing email correctly.** 🎉

---

## 9. The mandatory first-run test

Before relying on the bot for a competitive Monday booking, complete the first-run test in [docs/first_run.md](first_run.md). Pick a low-stakes weekday slot, let the bot book it, and have Carl cancel the reservation within 10 minutes. This validates the booking actually works against live ForeTees.

---

## 10. Backups

Once a month, use the Railway CLI to copy the DB locally:

```bash
railway run cat /data/teebot.db > ~/teebot-backup-$(date +%Y%m%d).db
```

---

## Costs

| | $/mo |
|---|---|
| Railway Hobby plan | $5 |
| Volume (1 GB) | included |
| Estimated compute (1 small container, 24/7) | included in Hobby plan |
| **Total** | **~$5/mo** |

Railway gives $5/mo of usage included in the Hobby plan, which covers everything for a small bot like this.

---

## Troubleshooting

**Daemon won't start (build fails):** Check Railway's build logs. Most likely: missing dependency in `pyproject.toml` or Python version mismatch. The project requires Python 3.13 (declared in `.python-version`).

**Daemon starts but Carl's emails aren't being processed:** Check that `BOT_GMAIL_APP_PASSWORD` was copy-pasted correctly (no spaces). The Gmail app password is 16 chars, sometimes shown with spaces — strip them.

**Booker fires but `auth_failed`:** Carl's ForeTees password may have changed. Update `FORETEES_PASSWORD` in Railway env vars and redeploy.

**"POSSIBLE DETECTION" email arrives:** Bot has self-disabled. See [docs/EMERGENCY.md](EMERGENCY.md).
