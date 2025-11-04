#!/usr/bin/env python3
import requests
import time
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# ========================
# 🔧 MAIN CONFIGURATION
# ========================

# Locations to monitor (use lowercase).
# Add city names exactly as they appear on Cloudflare Status (e.g., "hong kong", "tokyo").
TARGET_LOCATIONS = [
    loc.strip().lower()
    for loc in os.getenv("TARGET_LOCATIONS", "jakarta,singapore").split(",")
    if loc.strip()
]

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

COMPONENTS_URL = os.getenv(
    "COMPONENTS_URL",
    "https://www.cloudflarestatus.com/api/v2/components.json"
)

SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", "60"))

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
# 🛠 LOGGING SETUP
# ========================
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

# file_handler = RotatingFileHandler("cloudflare_monitor.log", maxBytes=5*1024*1024, backupCount=2)
# file_handler.setFormatter(log_formatter)
# root_logger.addHandler(file_handler)


def send_slack_alert(location: str, component_name: str, status: str):
    if not SLACK_WEBHOOK_URL:
        logging.warning("SLACK_WEBHOOK_URL is not set! Skipping Slack notification.")
        return

    label = STATUS_LABEL.get(status, status)
    emoji = STATUS_EMOJI.get(status, ":question:")

    color = "good"
    if status in  ["partial_outage", "under_maintenance"]:
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
            logging.error(f"Failed to send to Slack: {response.status_code} - {response.text}")
    except Exception as e:
        logging.error(f"Error sending to Slack: {e}")


def fetch_components():
    try:
        logging.debug("Fetching components from Cloudflare...")
        resp = requests.get(COMPONENTS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        components = data.get("components", [])
        logging.debug(f"Successfully retrieved {len(components)} components.")
        return components
    except Exception as e:
        logging.error(f"Failed to fetch data from Cloudflare: {e}")
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
                matches[target] = {
                    "component_name": name,
                    "status": status,
                }
                break  # first match is enough
    return matches


def main():
    if not SLACK_WEBHOOK_URL:
        logging.warning("SLACK_WEBHOOK_URL is not set. Slack notifications WILL NOT be sent.")
        logging.warning("   ⇒ Run with: export SLACK_WEBHOOK_URL='https://hooks.slack.com/...'")
    
    locations_str = ", ".join(TARGET_LOCATIONS) if TARGET_LOCATIONS else "(none)"
    logging.info(f"Starting monitoring for locations: {locations_str}")
    logging.info(f"Checking every {SLEEP_INTERVAL} seconds...")

    while True:
        components = fetch_components()
        if not components:
            time.sleep(SLEEP_INTERVAL)
            continue

        current_matches = find_matching_components(components, TARGET_LOCATIONS)

        # Warn if a target location isn't found
        for loc in [t.strip().lower() for t in TARGET_LOCATIONS]:
            if loc not in current_matches:
                logging.warning(
                    f"Location '{loc}' NOT FOUND on Cloudflare Status! "
                    "Check the spelling or visit https://www.cloudflarestatus.com"
                )

        # Detect status changes
        for loc, data in current_matches.items():
            current_status = data["status"]
            prev_status = last_statuses.get(loc)

            if current_status != prev_status:
                label = STATUS_LABEL.get(current_status, current_status)
                logging.info(f"STATUS CHANGE: {loc.title()} → {label} (Component: {data['component_name']})")

                # Send to Slack
                send_slack_alert(loc, data["component_name"], current_status)

                # Save latest status
                last_statuses[loc] = current_status

        time.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Stopped by user.")
        sys.exit(0)
