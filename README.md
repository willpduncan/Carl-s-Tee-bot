# TeeBot

Automated ForeTees tee-time booking bot for Carl Pfiffner at Pine Forest Country Club.

## Quick reference
- Spec: [docs/specs/2026-05-15-foretees-bot-design.md](docs/specs/2026-05-15-foretees-bot-design.md)
- Implementation plan: [docs/plans/2026-05-15-teebot-implementation.md](docs/plans/2026-05-15-teebot-implementation.md)
- Deployment guide: [docs/setup.md](docs/setup.md)
- Emergency runbook: [docs/EMERGENCY.md](docs/EMERGENCY.md)

## Local development

```bash
python3.13 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
