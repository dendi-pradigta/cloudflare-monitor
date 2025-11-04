#!/usr/bin/env python3
import requests
import time
import logging
import os
import sys
import json
import signal
from logging.handlers import RotatingFileHandler

# ========================
# 🔧 CONFIGURATION
# ========================

TARGET_LOCATIONS = [
    loc.strip().lower()
    for loc in os.getenv("TARGET_LOCATIONS", "jakarta,singapore").split(",")
    if loc.strip()
]

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()

COMPONENTS_URL = os.getenv(
    "COMPONENTS_URL",
    "https://www.cloudflarestatus.com/api/v2/components.json"
).strip()

SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", "60"))

# Lokasi file status (harus di volume persisten di Docker)
STATUS_FILE = os.getenv("STATUS_FILE", "/data/last_statuses.json")

# Setup log level
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger()

# Logging handler
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

# Optional: file logging
# file_handler = RotatingFileHandler("/data/cloudflare_monitor.log", maxBytes=5*1024*1024, backupCount=2)
# file_handler.setFormatter(log_formatter)
# root_logger.addHandler(file_handler)

# Headers
HEADERS = {
    "User-Agent": "CloudflareStatusMonitor/1.0 (+https://github.com/your-org/cloudflare-monitor)"
}

# Status mapping
STATUS_LABEL = {
    "operational": "Operational",
    "partial_outage": "Partially Re-routed",
    "major_outage": "Re-routed",
    "degraded_performance": "Degraded Performance",
    "under_maintenance": "Under Maintenance",
}

STATUS_EMOJI = {
    "operational": ":white_check_mark:",
    "partial_outage": ":warning:",
    "major_outage": ":exclamation::exclamation::exclamation:",
    "degraded_performance": ":zap:",
    "under_maintenance": ":construction:",
}

last_statuses = {}


# ========================
# 🛠 UTILS
# ========================

def load_last_statuses():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.warning("Failed to load last statuses from %s: %s", STATUS_FILE, e)
    return {}

def save_last_statuses():
    # Ensure directory exists
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(last_statuses, f)
    except Exception as e:
        logging.warning("Failed to save last statuses to %s: %s", STATUS_FILE, e)

def send_slack_alert(location: str, component_name: str, status: str):
    if not SLACK_WEBHOOK_URL:
        logging.warning("SLACK_WEBHOOK_URL is not set! Skipping Slack notification.")
        return

    if not SLACK_WEBHOOK_URL.startswith("https://hooks.slack.com/"):
        logging.error("Invalid SLACK_WEBHOOK_URL format — must start with 'https://hooks.slack.com/'")
        return

    label = STATUS_LABEL.get(status, status)
    emoji = STATUS_EMOJI.get(status, ":question:")

    color = "good"
    if status in ["partial_outage", "under_maintenance"]:
        color = "warning"
    elif status in ["major_outage", "degraded_performance"]:
        color = "danger"

    payload = {
        "text": ":earth_asia: *Cloudflare Status Update*",
        "attachments": [
            {
                "color": color,
                "fields": [
                    {"title": "Location", "value": location.title(), "short": True},
                    {"title": "Component", "value": component_name, "short": True},
                    {"title": "Status", "value": f"{emoji} {label}", "short": True},
                ],
                "footer": "Cloudflare Monitor",
                "ts": int(time.time()),
            }
        ],
    }

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            logging.info(f"Slack notification sent for {location}")
        else:
            logging.error(f"Slack send failed: {response.status_code} - {response.text[:300]}")
    except Exception as e:
        logging.error(f"Error sending to Slack: {e}")


def fetch_components():
    try:
        logging.debug("Fetching components from Cloudflare...")
        resp = requests.get(COMPONENTS_URL, headers=HEADERS, timeout=10)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            logging.warning("Rate limited by Cloudflare. Retrying after %d seconds.", retry_after)
            time.sleep(retry_after)
            return []
        resp.raise_for_status()

        ct = resp.headers.get("content-type", "").lower()
        if "application/json" not in ct:
            logging.error("Unexpected Content-Type: %s", ct)
            logging.error("Response preview: %s", resp.text[:300])
            return []

        data = resp.json()
        components = data.get("components", [])
        logging.debug(f"Retrieved {len(components)} components.")
        return components
    except Exception as e:
        logging.exception("Failed to fetch Cloudflare status: %s", e)
        return []


def find_matching_components(components, targets):
    targets_clean = [t.strip().lower() for t in targets]
    matches = {}
    for comp in components:
        name = comp.get("name", "")
        name_lower = name.lower()
        status = comp.get("status", "unknown")
        for target in targets_clean:
            if target in name_lower:
                matches[target] = {"component_name": name, "status": status}
                break
    return matches


# ========================
# 🛑 SHUTDOWN HANDLER
# ========================

def graceful_shutdown(sig, frame):
    logging.info("🛑 Received signal %s. Shutting down gracefully...", sig)
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)


# ========================
# 🔄 MAIN LOOP
# ========================

def main():
    global last_statuses

    # Validate webhook early
    if SLACK_WEBHOOK_URL and not SLACK_WEBHOOK_URL.startswith("https://hooks.slack.com/"):
        logging.critical("Invalid SLACK_WEBHOOK_URL format!")
        sys.exit(1)

    # Load persisted statuses
    last_statuses = load_last_statuses()

    locations_str = ", ".join(TARGET_LOCATIONS) if TARGET_LOCATIONS else "(none)"
    logging.info(f"🚀 Starting Cloudflare monitor for: {locations_str}")
    logging.info(f"🔁 Check interval: {SLEEP_INTERVAL} seconds")
    logging.info(f"💾 Status file: {STATUS_FILE}")

    while True:
        try:
            logging.info("🔄 Starting new status check cycle...")

            components = fetch_components()
            if not components:
                logging.warning("No valid component data. Skipping cycle.")
                time.sleep(SLEEP_INTERVAL)
                continue

            current_matches = find_matching_components(components, TARGET_LOCATIONS)

            # Warn about missing locations
            for loc in [t.strip().lower() for t in TARGET_LOCATIONS]:
                if loc not in current_matches:
                    logging.warning(
                        f"Location '{loc}' NOT FOUND in Cloudflare status! "
                        "Check spelling at https://www.cloudflarestatus.com"
                    )

            # Check for status changes
            for loc, data in current_matches.items():
                current_status = data["status"]
                prev_status = last_statuses.get(loc)

                if current_status != prev_status:
                    label = STATUS_LABEL.get(current_status, current_status)
                    logging.info(f"🔔 STATUS CHANGE: {loc.title()} → {label} (Component: {data['component_name']})")
                    send_slack_alert(loc, data["component_name"], current_status)
                    last_statuses[loc] = current_status
                    save_last_statuses()

        except Exception as e:
            logging.exception("💥 Unexpected error in main loop: %s", e)

        logging.debug("💤 Sleeping for %d seconds...", SLEEP_INTERVAL)
        time.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("🛑 Interrupted by user.")
        sys.exit(0)