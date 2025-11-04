# Cloudflare Status Monitor

Simple Python script to monitor Cloudflare edge locations and send Slack alerts when status changes (e.g. outage, maintenance, degraded performance).

---

## ✨ Features

- Monitors multiple Cloudflare locations by name
- Sends rich Slack notifications on status changes
- Persists last known status to avoid duplicate alerts after restart
- Graceful shutdown (supports Docker/Kubernetes)
- Rate-limit and error resilient
- Configurable via environment variables

---

## 🚀 Quick Start

### 1. Prepare `.env`

```env
TARGET_LOCATIONS=jakarta,singapore,tokyo,manila
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
SLEEP_INTERVAL=60
LOG_LEVEL=INFO
```

> Get your Slack webhook from [Slack API](https://api.slack.com/messaging/webhooks)

### 2. Run with Docker Compose

```bash
mkdir -p monitor-data
docker compose up -d
```

### 3. View logs

```bash
docker compose logs -f
```

---

## 📁 Files

- `cloudflare_monitor.py` — main script
- `Dockerfile` — lightweight image
- `docker-compose.yml` — ready-to-run config
- `requirements.txt` — only `requests`
- `.env` — configuration

---

## 🔁 Persistence

Status history is saved to `monitor-data/last_statuses.json`.  
This prevents duplicate alerts when the container restarts.

---

## 📝 Notes

- Only sends alert **when status changes**
- Uses Cloudflare’s public status API: `https://www.cloudflarestatus.com/api/v2/components.json`
- Location names must match Cloudflare’s naming (e.g. `jakarta`, `tokyo`, `dar es salaam`)

---

## 🛑 Stop

```bash
docker compose down
```

The monitor will resume from last known state on next start.