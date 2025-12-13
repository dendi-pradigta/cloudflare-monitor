# Cloudflare Status Monitor

![CI Pipeline](https://github.com/dendi-pradigta/cloudflare-monitor/workflows/CI%20Pipeline/badge.svg)
![Docker Validation](https://github.com/dendi-pradigta/cloudflare-monitor/workflows/Docker%20Validation/badge.svg)

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
- `incident_monitor.py` — global incident monitor
- `notifications.py` — shared notification functions
- `Dockerfile` — lightweight image
- `docker-compose.yml` — ready-to-run config
- `requirements.txt` — production dependencies
- `requirements-dev.txt` — development dependencies
- `pyproject.toml` — project configuration
- `.env` — configuration

---

## 🔧 Development

### Code Quality & CI/CD

This project uses automated workflows to ensure code quality:

- **CI Pipeline**: Linting, formatting, type checking, and security scanning
- **Docker Validation**: Dockerfile and docker-compose validation
- **Release Pipeline**: Automated releases (disabled by default)

### Development Setup

```bash
# Clone repository
git clone https://github.com/dendi-pradigta/cloudflare-monitor.git
cd cloudflare-monitor

# Install development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run linting
ruff check .

# Format code
ruff format .

# Type checking
mypy .

# Security scanning
bandit -r .
safety check
```

### Workflow Triggers

- **Push/Pull Request**: Automatic CI and Docker validation
- **Manual Dispatch**: Run workflows manually for testing
- **Release**: Manual release workflow (enable when needed)

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