#!/usr/bin/env python3
# cloudflare_monitor.py (Diperbaiki)

import requests
import time
import logging
import os
import sys
import json
import signal

# Impor dari file notifikasi shared
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
            with open(STATUS_FILE, "r") as f: return json.load(f)
        except Exception as e: logging.warning(f"Failed to load status file: {e}")
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

# ==> [PERBAIKAN] Fungsi ini telah diperbaiki <==
def find_matching_components(components, targets):
    matches = {}
    for comp in components:
        name_lower = comp.get("name", "").lower()

        # BARIS YANG MENYEBABKAN ERROR TELAH DIHAPUS DARI SINI
        
        for target in targets:
            # Cari nama target di dalam nama komponen, misal "jakarta" di "Jakarta, Indonesia"
            if target in name_lower:
                matches[target] = {"component_name": comp.get("name"), "status": comp.get("status")}
                # Setelah match, lanjut ke komponen berikutnya
                break 
    return matches

def graceful_shutdown(sig, frame):
    logging.info(f"🛑 Received signal {sig}. Shutting down location monitor...")
    sys.exit(0)

# ========================
# मुख्य LOOP
# ========================

def main():
    global last_statuses
    last_statuses = load_last_statuses()

    logging.info(f"🚀 Starting Cloudflare Location Monitor for: {', '.join(TARGET_LOCATIONS)}")
    if notifications.slack_client: logging.info(f"slack: Location notifications enabled (broadcasting to all bot channels)")
    if notifications.OPSGENIE_ENABLED: logging.info(f"opsgenie: Location notifications enabled.")

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
                    
                    # Kirim Slack Alert
                    slack_fields = [{"title": "Location", "value": loc.title()}, {"title": "Component", "value": data['component_name']}]
                    notifications.send_slack_alert(title="Cloudflare Location Status Update", fields=slack_fields, status=data["status"])
                    
                    # Kirim Opsgenie Alert
                    opsgenie_alias = f"cf-loc-{loc}"
                    opsgenie_message = f"Cloudflare Status: {loc.title()} is {label}"
                    opsgenie_desc = f"Status komponen '{data['component_name']}' telah berubah menjadi '{label}'."
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