#!/usr/bin/env python3
# incident_monitor.py

import json
import logging
import os
import signal
import sys
import time

import requests

# Import notification functions from shared file
import notifications

# ========================
# 🔧 CONFIGURATION
# ========================
# ==> [CHANGE 1] Replaced URL with valid endpoint <==
INCIDENTS_URL = os.getenv(
    "INCIDENTS_URL",
    "https://www.cloudflarestatus.com/api/v2/incidents.json",  # <-- URL FIXED
).strip()
SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", "60"))
STATUS_FILE = os.getenv("INCIDENT_STATUS_FILE", "data/last_incidents.json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Setup logging
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(levelname)s - (IncidentMonitor) - %(message)s",
    stream=sys.stdout,
)
HEADERS = {"User-Agent": "CloudflareIncidentMonitor/1.0"}

# Dictionary to store last known incident status
last_incident_statuses = {}

# ========================
# 🛠 UTILS
# ========================


def load_last_statuses():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logging.warning(
                f"Could not load incident status file '{STATUS_FILE}', starting fresh. Error: {e}"
            )
    return {}


def save_last_statuses():
    dir_name = os.path.dirname(STATUS_FILE)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(last_incident_statuses, f)
    except OSError as e:
        logging.error(f"Failed to save incident status file: {e}")


# ==> [CHANGE 2] Function name changed for better accuracy <==
def fetch_incidents():
    """Fetch latest incidents from Cloudflare API."""
    try:
        response = requests.get(INCIDENTS_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.json().get("incidents", [])
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch Cloudflare incidents: {e}")
    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON response from Cloudflare: {e}")
    return []


def graceful_shutdown(sig, frame):
    logging.info(f"🛑 Received signal {sig}. Shutting down incident monitor...")
    sys.exit(0)


# ========================
# MAIN LOOP
# ========================


def main():
    global last_incident_statuses
    last_incident_statuses = load_last_statuses()

    logging.info("🚀 Starting Cloudflare Incident Monitor...")
    if notifications.slack_client:
        logging.info(
            "slack: Incident notifications enabled (broadcasting to all bot channels)"
        )
    if notifications.OPSGENIE_ENABLED:
        logging.info("opsgenie: Incident notifications enabled")

    while True:
        try:
            logging.info("🔄 Checking for new or updated incidents...")
            all_incidents = fetch_incidents()  # Fetch all incidents
            if not all_incidents:
                time.sleep(SLEEP_INTERVAL)
                continue

            # ==> [CHANGE 3] Filter only incidents that are NOT resolved <==
            unresolved_incidents = [
                inc for inc in all_incidents if inc.get("status") != "resolved"
            ]

            current_incident_ids = {inc["id"]: inc for inc in unresolved_incidents}

            # 1. Check for new incidents or status changes
            for inc_id, incident in current_incident_ids.items():
                last_status = last_incident_statuses.get(inc_id)
                current_status = incident["status"]

                if current_status != last_status:
                    logging.info(
                        f"🔔 INCIDENT CHANGE: '{incident['name']}' -> {current_status.upper()} (ID: {inc_id})"
                    )

                    impact = incident.get("impact", "unknown")
                    incident_url = incident.get(
                        "shortlink", "https://www.cloudflarestatus.com"
                    )
                    component_names = ", ".join(
                        [comp["name"] for comp in incident.get("components", [])]
                    )

                    slack_fields = [
                        {"title": "Incident", "value": incident["name"]},
                        {"title": "Impact", "value": impact.title()},
                        {
                            "title": "Affected Components",
                            "value": component_names or "Not specified",
                        },
                    ]
                    notifications.send_slack_alert(
                        title="Cloudflare Global Incident",
                        fields=slack_fields,
                        status=current_status,
                        link=incident_url,
                    )

                    opsgenie_alias = f"cf-incident-{inc_id}"
                    opsgenie_message = (
                        f"Cloudflare Incident: {incident['name']} [{impact.upper()}]"
                    )
                    opsgenie_description = f"Incident '{incident['name']}' status has changed to {current_status}.\nImpact: {impact}\nComponents: {component_names}\nLink: {incident_url}"
                    notifications.send_opsgenie_alert(
                        alias=opsgenie_alias,
                        message=opsgenie_message,
                        description=opsgenie_description,
                        status=current_status,
                        tags=["cloudflare", "incident-monitor", impact],
                    )

                    last_incident_statuses[inc_id] = current_status

            # 2. Check for resolved incidents
            resolved_ids = set(last_incident_statuses.keys()) - set(
                current_incident_ids.keys()
            )
            for inc_id in resolved_ids:
                # First check if this ID exists in our state
                if inc_id in last_incident_statuses:
                    logging.info(
                        f"✅ INCIDENT RESOLVED: ID {inc_id} has been resolved and removed from the unresolved list."
                    )
                    # Remove from our state
                    del last_incident_statuses[inc_id]
                    # Send closure notification to Opsgenie
                    opsgenie_alias = f"cf-incident-{inc_id}"
                    notifications.send_opsgenie_alert(
                        alias=opsgenie_alias,
                        message=f"Cloudflare Incident {inc_id} Resolved",
                        description=f"Incident {inc_id} has been resolved and is no longer active",
                        status="resolved",
                        tags=["cloudflare", "incident-resolved"],
                    )

            save_last_statuses()

        except Exception as e:
            logging.exception(f"💥 Unexpected error in incident monitor main loop: {e}")

        logging.debug(f"💤 Sleeping for {SLEEP_INTERVAL} seconds...")
        time.sleep(SLEEP_INTERVAL)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    main()
