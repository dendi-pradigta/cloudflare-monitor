#!/usr/bin/env python3
# cloudflare_monitor.py (Fixed)

import requests
import time
import logging
import os
import sys
import json
import signal

# Import from shared notification file
import notifications

# ========================
# 🔧 CONFIGURATION
# ========================

TARGET_LOCATIONS = [
    loc.strip().lower()
    for loc in os.getenv("TARGET_LOCATIONS", "jakarta,singapore").split(",")
    if loc.strip()
]
COMPONENTS_URL = os.getenv(
    "COMPONENTS_URL",
    "https://www.cloudflarestatus.com/api/v2/components.json"
).strip()
SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", "60"))
STATUS_FILE = os.getenv("STATUS_FILE", "data/last_statuses.json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
NOTIFY_ON_RESTART = os.getenv("NOTIFY_ON_RESTART", "false").lower()
SYNC_ON_STARTUP = os.getenv("SYNC_ON_STARTUP", "true").lower() == "true"

# Setup logging
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - (LocationMonitor) - %(message)s', stream=sys.stdout)
HEADERS = {"User-Agent": "CloudflareStatusMonitor/1.0"}

STATUS_LABEL = notifications.STATUS_LABEL
last_statuses = {}

# ========================
# 🛠 UTILS
# ========================

def load_last_statuses():
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f: 
                data = json.load(f)
                if not isinstance(data, dict):
                    logging.warning(f"Status file contains invalid data format, expected dict got {type(data)}")
                    return {}
                return data
        except json.JSONDecodeError as e:
            logging.warning(f"Failed to parse status file JSON: {e}")
            return {}
        except Exception as e:
            logging.warning(f"Failed to load status file: {e}")
            return {}
    return {}

def save_last_statuses():
    dir_name = os.path.dirname(STATUS_FILE)
    if dir_name: os.makedirs(dir_name, exist_ok=True)
    try:
        with open(STATUS_FILE, "w") as f: json.dump(last_statuses, f)
    except Exception as e: logging.error(f"Failed to save status file: {e}")

def fetch_components():
    try:
        resp = requests.get(COMPONENTS_URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json().get("components", [])
    except Exception as e:
        logging.exception(f"Failed to fetch Cloudflare status: {e}")
        return []

# ==> [FIX] This function has been fixed <==
def find_matching_components(components, targets):
    matches = {}
    for comp in components:
        name_lower = comp.get("name", "").lower()

        # ERROR-CAUSING LINE HAS BEEN REMOVED FROM HERE
        
        for target in targets:
            # Search for target name within component name, e.g. "jakarta" in "Jakarta, Indonesia"
            if target in name_lower:
                matches[target] = {"component_name": comp.get("name"), "status": comp.get("status")}
                # After match, continue to next component
                break 
    return matches

def verify_status_on_restart():
    """Compare saved vs current status and handle notifications based on NOTIFY_ON_RESTART"""
    global last_statuses
    
    if not SYNC_ON_STARTUP:
        logging.info("Startup sync disabled")
        return
    
    logging.info("🔄 Performing startup status synchronization...")
    
    # Fetch current status
    components = fetch_components()
    if not components:
        logging.warning("Cannot sync startup status - API fetch failed")
        return
    
    current_matches = find_matching_components(components, TARGET_LOCATIONS)
    if not current_matches:
        logging.warning("No matching components found for startup sync")
        return
    
    # Compare and handle differences
    differences = []
    
    for loc, data in current_matches.items():
        saved_status = last_statuses.get(loc)
        current_status = data["status"]
        
        if saved_status != current_status:
            differences.append({
                "location": loc.title(),
                "component": data["component_name"],
                "from_status": saved_status or "unknown",
                "to_status": current_status
            })
    
    # Handle based on notification mode
    if differences:
        logging.info(f"Found {len(differences)} status differences on startup")
        
        if NOTIFY_ON_RESTART == "false":
            # Silent update
            for diff in differences:
                label = STATUS_LABEL.get(diff['to_status'], diff['to_status'])
                logging.info(f"🔄 Sync: {diff['location']} → {label}")
            # Update saved status
            for diff in differences:
                last_statuses[diff['location'].lower()] = diff['to_status']
            save_last_statuses()
            
        elif NOTIFY_ON_RESTART == "true":
            # Individual notifications
            for diff in differences:
                label = STATUS_LABEL.get(diff['to_status'], diff['to_status'])
                logging.info(f"🔔 RESTART SYNC: {diff['location']} → {label}")
                
                # Send individual notification
                slack_fields = [
                    {"title": "Location", "value": diff['location']},
                    {"title": "Component", "value": diff['component']},
                    {"title": "Previous Status", "value": diff['from_status']}
                ]
                notifications.send_slack_alert(
                    title="Cloudflare Status Sync on Restart", 
                    fields=slack_fields, 
                    status=diff['to_status']
                )
                
                # Send Opsgenie notification
                if notifications.OPSGENIE_ENABLED:
                    opsgenie_alias = f"cf-loc-{diff['location'].lower()}"
                    opsgenie_message = f"Cloudflare Status Sync: {diff['location']} is {label}"
                    opsgenie_desc = f"Component '{diff['component']}' status changed from '{diff['from_status']}' to '{label}' during restart sync."
                    notifications.send_opsgenie_alert(
                        alias=opsgenie_alias, 
                        message=opsgenie_message, 
                        description=opsgenie_desc, 
                        status=diff['to_status'], 
                        tags=["cloudflare", "location-monitor", "restart-sync", diff['location'].lower()]
                    )
                
                # Update status
                last_statuses[diff['location'].lower()] = diff['to_status']
            save_last_statuses()
            
        elif NOTIFY_ON_RESTART == "summary":
            # Single summary notification
            notifications.send_restart_summary_notification(
                differences, "location", last_statuses
            )
            
            # Update all statuses
            for diff in differences:
                last_statuses[diff['location'].lower()] = diff['to_status']
            save_last_statuses()
            
        else:
            logging.warning(f"Invalid NOTIFY_ON_RESTART value: {NOTIFY_ON_RESTART}. Using silent sync.")
            for diff in differences:
                last_statuses[diff['location'].lower()] = diff['to_status']
            save_last_statuses()
    
    else:
        logging.info("✅ Startup sync: No status differences found")

def graceful_shutdown(sig, frame):
    logging.info(f"🛑 Received signal {sig}. Shutting down location monitor...")
    sys.exit(0)

# ========================
# MAIN LOOP
# ========================

def main():
    global last_statuses
    last_statuses = load_last_statuses()

    logging.info(f"🚀 Starting Cloudflare Location Monitor for: {', '.join(TARGET_LOCATIONS)}")
    if notifications.slack_client: logging.info(f"slack: Location notifications enabled (broadcasting to all bot channels)")
    if notifications.OPSGENIE_ENABLED: logging.info(f"opsgenie: Location notifications enabled.")
    
    # Perform startup sync if enabled
    verify_status_on_restart()

    while True:
        try:
            logging.info("🔄 Starting new location status check cycle...")
            components = fetch_components()
            if not components:
                time.sleep(SLEEP_INTERVAL)
                continue
            
            current_matches = find_matching_components(components, TARGET_LOCATIONS)
            if not current_matches:
                 logging.warning(f"No matching components found for targets: {', '.join(TARGET_LOCATIONS)}. Check your TARGET_LOCATIONS and Cloudflare's component list.")

            for loc, data in current_matches.items():
                if data["status"] != last_statuses.get(loc):
                    label = STATUS_LABEL.get(data["status"], data["status"])
                    logging.info(f"🔔 STATUS CHANGE: {loc.title()} → {label} (Component: {data['component_name']})")
                    
                    # Send Slack Alert
                    slack_fields = [{"title": "Location", "value": loc.title()}, {"title": "Component", "value": data['component_name']}]
                    notifications.send_slack_alert(title="Cloudflare Location Status Update", fields=slack_fields, status=data["status"])
                    
                    # Send Opsgenie Alert
                    opsgenie_alias = f"cf-loc-{loc.lower()}"
                    opsgenie_message = f"Cloudflare Status: {loc.title()} is {label}"
                    opsgenie_desc = f"Component '{data['component_name']}' status has changed to '{label}'."
                    notifications.send_opsgenie_alert(alias=opsgenie_alias, message=opsgenie_message, description=opsgenie_desc, status=data["status"], tags=["cloudflare", "location-monitor", loc])
                    
                    last_statuses[loc] = data["status"]
                    save_last_statuses()

        except Exception as e:
            logging.exception(f"💥 Unexpected error in location monitor main loop: {e}")
        logging.debug(f"💤 Sleeping for {SLEEP_INTERVAL} seconds...")
        time.sleep(SLEEP_INTERVAL)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    main()