# 🌐 Cloudflare Status Monitor

A lightweight Python-based service that monitors Cloudflare’s regional component statuses and sends real-time alerts to **Slack** when any region’s status changes (e.g., from *Operational* to *Degraded* or *Outage*).

This project can run locally or inside a **Docker container** using **Docker Compose**, and is fully configurable via environment variables.

---

## 🧭 Features

* ✅ Monitors specific Cloudflare locations (e.g., *Jakarta*, *Singapore*, *Tokyo*)
* 🔔 Sends alerts to **Slack** via webhook integration
* ⚙️ Configurable check interval and monitored locations
* 💚 Lightweight and containerized (Python + Docker)
* 🧾 Includes logging and health checks
* 🧱 Easy to deploy on servers or Kubernetes

---

## 🏗️ Project Structure

```
cloudflare-monitor/
├─ cloudflare_monitor.py      # Main Python script
├─ Dockerfile                 # Docker image definition
├─ docker-compose.yml         # Docker Compose configuration
├─ requirements.txt           # Python dependencies
├─ .env                       # Environment variables (not committed)
└─ .gitignore                 # Ignored files and secrets
```

---

## ⚙️ Requirements

* **Docker** ≥ 20.x
* **Docker Compose** ≥ 1.29
* Optional: Python ≥ 3.11 (if you run without Docker)

---

## 🚀 Quick Start (with Docker Compose)

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-org/cloudflare-monitor.git
   cd cloudflare-monitor
   ```

2. **Create a `.env` file**

   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` with your settings**

   ```env
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
   SLEEP_INTERVAL=60
   TARGET_LOCATIONS=jakarta,singapore,manila,bangkok
   ```

4. **Build and start the service**

   ```bash
   docker compose up -d
   ```

5. **Check logs**

   ```bash
   docker compose logs -f cloudflare-monitor
   ```

6. **Verify health**

   ```bash
   docker inspect --format='{{json .State.Health}}' cloudflare-monitor | jq
   ```

---

## ⚡ Configuration

All runtime configuration is done via environment variables.

| Variable            | Required | Description                                        | Example                                                   |
| ------------------- | -------- | -------------------------------------------------- | --------------------------------------------------------- |
| `SLACK_WEBHOOK_URL` | ✅        | Slack webhook URL for notifications                | `https://hooks.slack.com/services/AAA/BBB/CCC`            |
| `SLEEP_INTERVAL`    | ❌        | Time (in seconds) between Cloudflare status checks | `60`                                                      |
| `TARGET_LOCATIONS`  | ❌        | Comma-separated list of locations to monitor       | `jakarta,singapore,tokyo`                                 |
| `COMPONENTS_URL`    | ❌        | Cloudflare Status API endpoint                     | `https://www.cloudflarestatus.com/api/v2/components.json` |

> 💡 **Tip:** You can override these values directly in `docker-compose.yml` or via CLI with `-e`.


---

## 🧰 Running Locally (without Docker)

If you prefer running directly with Python:

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Export environment variables:

   ```bash
   export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
   export TARGET_LOCATIONS=jakarta,singapore
   export SLEEP_INTERVAL=60
   ```

3. Run the monitor:

   ```bash
   python cloudflare_monitor.py
   ```

---

## 🪵 Logging

Logs are printed to **stdout** and can be viewed using:

```bash
docker compose logs -f cloudflare-monitor
```

You can optionally enable file-based logging by uncommenting the RotatingFileHandler lines in `cloudflare_monitor.py`.

---

## 🧩 Docker Healthcheck

The service includes a built-in **health check** in `docker-compose.yml`:

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -fsS https://www.cloudflarestatus.com/api/v2/components.json >/dev/null || exit 1"]
  interval: 1m
  timeout: 10s
  retries: 3
```

This ensures the container is only marked “healthy” if Cloudflare’s API is reachable.

---

## 🔐 Security Notes

* **Never commit your `.env` file** — it contains your Slack webhook URL.
* The `.gitignore` file already excludes `.env` to prevent accidental leaks.
* If your webhook is exposed, **rotate it immediately** in Slack.

---

## 🧱 Example Slack Alert

When a monitored location changes status, you’ll receive a message like this:

> 🌐 *Cloudflare Status Update*
> **Location:** Singapore
> **Component:** Singapore - (Cloudflare Network)
> **Status:** ⚠️ Partially Re-routed

---

