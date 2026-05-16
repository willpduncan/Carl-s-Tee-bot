# TeeBot Deployment Guide

Step-by-step setup for a fresh VPS. Estimated time: ~45 minutes.

## 1. Pre-deploy: accounts

- **DigitalOcean account** (or Hetzner / Linode). Add a credit card.
- **Bot Gmail account.** Sign up for `teebotcarl@gmail.com` (or similar). Then:
  - Enable 2-step verification (required for app passwords)
  - Generate an "App password" at https://myaccount.google.com/apppasswords
    - Select app = Mail, device = "TeeBot VPS"
    - Save the 16-char password somewhere safe (you'll paste it into secrets.env later)
- **Optional: Gmail filter on Carl's `cpfiffner62@gmail.com`** to auto-forward `auto-send@foretees.com` to the bot Gmail. This enables the success cross-check.

## 2. Create the VPS

1. DigitalOcean → "Create Droplet"
2. Choose: Ubuntu 24.04 LTS, $4/mo plan (1 vCPU, 512 MB RAM), datacenter DAL or NYC1
3. Add your SSH public key (or set a root password)
4. Create the droplet, note the IP address

## 3. Initial server setup

SSH in as root:

```bash
ssh root@<IP>
```

Run:
```bash
apt update && apt upgrade -y
apt install -y python3.12 python3.12-venv git sqlite3 unattended-upgrades

# Create a non-root user for the bot
useradd -m -s /bin/bash teebot

# Create directories
mkdir -p /opt/teebot /etc/teebot /var/lib/teebot /var/log/teebot
chown teebot:teebot /opt/teebot /var/lib/teebot /var/log/teebot
chmod 700 /etc/teebot

# Enable unattended security upgrades
dpkg-reconfigure -plow unattended-upgrades
```

## 4. Clone the code and install deps

As the `teebot` user:
```bash
sudo -iu teebot
cd /opt/teebot
git clone <your-repo-url> .
python3.12 -m venv .venv
.venv/bin/pip install -e .
exit  # back to root
```

## 5. Configure secrets

As root:
```bash
cat > /etc/teebot/secrets.env <<EOF
FORETEES_USERNAME=Pfifftex
FORETEES_PASSWORD=<rotated-password-here>
BOT_GMAIL_ADDRESS=teebotcarl@gmail.com
BOT_GMAIL_APP_PASSWORD=<16-char app password>
CARL_EMAIL=cpfiffner62@gmail.com
OPERATOR_EMAIL=willpduncan@gmail.com
TIMEZONE=America/Chicago
DB_PATH=/var/lib/teebot/teebot.db
EOF
chown root:teebot /etc/teebot/secrets.env
chmod 640 /etc/teebot/secrets.env
```

⚠ **Important:** Rotate `FORETEES_PASSWORD` to a NEW value (don't reuse the one you used during development).

## 6. Initialize the database

```bash
sudo -u teebot bash -c "set -a; source /etc/teebot/secrets.env; set +a; cd /opt/teebot && .venv/bin/python scripts/init_db.py"
```

Expected output: `Initialized schema at /var/lib/teebot/teebot.db`

## 7. Install systemd units

```bash
cp /opt/teebot/systemd/teebot-*.service /etc/systemd/system/
cp /opt/teebot/systemd/teebot-*.timer /etc/systemd/system/
systemctl daemon-reload

# Enable the timers (they will fire automatically)
systemctl enable --now teebot-booker.timer
systemctl enable --now teebot-poller.timer

# Verify
systemctl list-timers | grep teebot
```

You should see both timers listed with their next-fire times.

## 8. Verify the poller is running

```bash
# Trigger one manual run
sudo -u teebot bash -c "set -a; source /etc/teebot/secrets.env; set +a; cd /opt/teebot && .venv/bin/python scripts/run_poller.py"

# Check journalctl
journalctl -u teebot-poller.service -n 50
```

## 9. Send a test request from Carl's email

From `cpfiffner62@gmail.com`, email `teebotcarl@gmail.com` with subject "tee time" and a valid request body. Wait ~60 seconds, then verify the DB:

```bash
sqlite3 /var/lib/teebot/teebot.db "SELECT * FROM requests ORDER BY id DESC LIMIT 1"
```

Confirm Carl received a confirmation email reply.

## 10. The mandatory first-run test

DO NOT rely on the bot for a competitive Monday booking until you've completed the first-run test described in `first_run.md`.

Pick a low-stakes weekday afternoon, send a request, wait for the booker to fire on the corresponding morning, then have Carl cancel the resulting reservation immediately.

## 11. Nightly database backup

As root, add a cron job:

```bash
cat > /etc/cron.daily/teebot-backup <<'EOF'
#!/bin/bash
set -e
mkdir -p /var/lib/teebot/backups
TS=$(date +%Y%m%d)
sqlite3 /var/lib/teebot/teebot.db ".backup /var/lib/teebot/backups/teebot-${TS}.db"
# Keep last 14 days
find /var/lib/teebot/backups -name 'teebot-*.db' -mtime +14 -delete
chown -R teebot:teebot /var/lib/teebot/backups
EOF
chmod +x /etc/cron.daily/teebot-backup

# Test it once
/etc/cron.daily/teebot-backup
ls -la /var/lib/teebot/backups/
```

Weekly off-box: copy the latest backup to your local machine:

```bash
# Run on Will's laptop, weekly
rsync -av root@<VPS-IP>:/var/lib/teebot/backups/ ~/teebot-backups/
```

## 12. (Optional) UptimeRobot

Sign up at uptimerobot.com (free). Add a "Ping" monitor for the VPS's IP.
