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
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLEEP_INTERVAL=60
LOG_LEVEL=INFO
```

> **Slack Setup:**
> 1. Create a Slack App at [Slack API](https://api.slack.com/apps)
> 2. Add Bot Token Scopes: `channels:read`, `groups:read`, `chat:write`
> 3. Install app to workspace and copy Bot User OAuth Token
> 4. Invite bot to desired channels with `/invite @YourBotName`
> 5. Bot will automatically send alerts to all channels where it's a member

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

## 🚨 Alert Status & Color Mapping

### Location Monitor (Component Status)
| Status | Color | Description |
|--------|-------|-------------|
| `operational` | 🟢 Green | System is working normally |
| `partial_outage` | 🟡 Yellow | Some services are re-routed |
| `major_outage` | 🔴 Red | Services are fully re-routed |
| `degraded_performance` | 🔴 Red | Performance is degraded |
| `under_maintenance` | 🟡 Yellow | Scheduled maintenance in progress |

### Incident Monitor (Global Incidents)
| Status | Color | Description |
|--------|-------|-------------|
| `investigating` | 🔴 Red | Incident is being investigated |
| `identified` | 🔴 Red | Root cause has been identified |
| `monitoring` | 🔴 Red | Incident is being monitored |
| `resolved` | 🟢 Green | Incident has been resolved |

### Opsgenie Priority Mapping
| Status | Priority | Severity |
|--------|----------|----------|
| `critical`, `major_outage` | P1 | Critical |
| `major`, `partial_outage` | P2 | High |
| `minor`, `degraded_performance` | P3 | Medium |
| `under_maintenance` | P5 | Low |
| Other statuses | P4 | Normal |

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