#!/usr/bin/env python3
import requests
import time
import logging
import os
import sys
import json
import signal
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ========================
# 🔧 CONFIGURATION
# ========================

# Docker Compose akan menyuntikkan .env, jadi kita tidak butuh dotenv di sini.

TARGET_LOCATIONS = [
    loc.strip().lower()
    for loc in os.getenv("TARGET_LOCATIONS", "jakarta,singapore").split(",")
    if loc.strip()
]

# Konfigurasi Slack
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "").strip()
slack_client = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None

# ==> [PERUBAHAN] Konfigurasi Opsgenie <==
OPSGENIE_ENABLED = os.getenv("OPSGENIE_ENABLED", "false").lower() == "true"
OPSGENIE_API_KEY = os.getenv("OPSGENIE_API_KEY", "").strip()
OPSGENIE_API_URL = os.getenv("OPSGENIE_API_URL", "https://api.opsgenie.com").strip()
# ==> ------------------------------------ <==

COMPONENTS_URL = os.getenv(
    "COMPONENTS_URL",
    "https://www.cloudflarestatus.com/api/v2/components.json"
).strip()
SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", "60"))
STATUS_FILE = os.getenv("STATUS_FILE", "data/last_statuses.json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# ... bagian setup logging, headers, dan mapping status tetap sama ...
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
HEADERS = {"User-Agent": "CloudflareStatusMonitor/1.0"}
STATUS_LABEL = { "operational": "Operational", "partial_outage": "Partially Re-routed", "major_outage": "Re-routed", "degraded_performance": "Degraded Performance", "under_maintenance": "Under Maintenance" }
STATUS_EMOJI = { "operational": ":white_check_mark:", "partial_outage": ":warning:", "major_outage": ":exclamation:", "degraded_performance": ":zap:", "under_maintenance": ":construction:" }
last_statuses = {}

# ========================
# 🛠 UTILS
# ========================

# ... fungsi load_last_statuses dan save_last_statuses tetap sama ...
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

# ... fungsi send_slack_alert tetap sama ...
def send_slack_alert(location: str, component_name: str, status: str):
    if not slack_client or not SLACK_CHANNEL: return
    label = STATUS_LABEL.get(status, status)
    emoji = STATUS_EMOJI.get(status, ":question:")
    color = "#2eb886"  # Hijau
    if status in ["partial_outage", "degraded_performance", "under_maintenance"]: color = "#daa038"  # Kuning
    elif status == "major_outage": color = "#a30200"  # Merah
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f":cloudflare: Cloudflare Status Update", "emoji": True}}, {"type": "section", "fields": [{"type": "mrkdwn", "text": f"*Location:*\n{location.title()}"}, {"type": "mrkdwn", "text": f"*Component:*\n{component_name}"}, {"type": "mrkdwn", "text": f"*Status:*\n{emoji} {label}"}]}, {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Cloudflare Monitor | <https://www.cloudflarestatus.com|View Status Page>"}]}]
    try:
        slack_client.chat_postMessage(channel=SLACK_CHANNEL, text=f"Status Update: {location.title()} is {label}", attachments=[{"color": color, "blocks": blocks}])
        logging.info(f"Slack notification sent for {location.title()}")
    except Exception as e:
        logging.error(f"Error sending Slack notification: {e}")

# ==> [PERUBAHAN] Fungsi baru untuk mengirim alert ke Opsgenie <==
def send_opsgenie_alert(location: str, component_name: str, status: str):
    """Membuat atau menutup alert di Opsgenie."""
    if not OPSGENIE_ENABLED or not OPSGENIE_API_KEY:
        if OPSGENIE_ENABLED: logging.warning("Opsgenie enabled but API Key is missing.")
        return

    label = STATUS_LABEL.get(status, status)
    # Alias digunakan untuk de-duplikasi. "cf-monitor-jakarta", "cf-monitor-singapore", etc.
    alert_alias = f"cf-monitor-{location}"

    # Jika status kembali normal, kita tutup alert yang ada.
    if status == 'operational':
        url = f"{OPSGENIE_API_URL}/v2/alerts/{alert_alias}/close?identifierType=alias"
        payload = {"note": "Status kembali ke Operational."}
        log_message = f"Closing Opsgenie alert for {location.title()}"
    else:
        # Jika ada masalah, kita buat atau perbarui alert.
        url = f"{OPSGENIE_API_URL}/v2/alerts"
        # Mapping status ke prioritas Opsgenie
        priority_map = {
            "major_outage": "P1",
            "partial_outage": "P2",
            "degraded_performance": "P3",
            "under_maintenance": "P5",
        }
        payload = {
            "message": f"Cloudflare Status: {location.title()} is {label}",
            "alias": alert_alias,
            "description": f"Status komponen '{component_name}' telah berubah menjadi '{label}'.\n\nSilakan periksa halaman status Cloudflare untuk detail lebih lanjut.",
            "priority": priority_map.get(status, "P4"), # Default ke P4 jika tidak ada di map
            "tags": ["cloudflare", "monitoring", location]
        }
        log_message = f"Creating/updating Opsgenie alert for {location.title()} with priority {payload['priority']}"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"GenieKey {OPSGENIE_API_KEY}"
    }

    try:
        logging.info(log_message)
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status() # Akan error jika status code 4xx atau 5xx
        logging.info(f"Opsgenie API call successful. Request ID: {response.json().get('requestId')}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling Opsgenie API: {e}")
        if e.response:
            logging.error(f"Opsgenie Response Body: {e.response.text}")
# ==> ------------------------------------ <==


# ... fungsi fetch_components dan find_matching_components tetap sama ...
def fetch_components():
    try:
        resp = requests.get(COMPONENTS_URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json().get("components", [])
    except Exception as e:
        logging.exception(f"Failed to fetch Cloudflare status: {e}")
        return []

def find_matching_components(components, targets):
    matches = {}
    for comp in components:
        name_lower = comp.get("name", "").lower()
        for target in targets:
            if target in name_lower:
                matches[target] = {"component_name": comp.get("name"), "status": comp.get("status")}
                break
    return matches

# ... graceful_shutdown and main tetap sama, dengan satu tambahan panggilan fungsi ...
def graceful_shutdown(sig, frame):
    logging.info(f"🛑 Received signal {sig}. Shutting down...")
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

def main():
    global last_statuses
    last_statuses = load_last_statuses()

    logging.info(f"🚀 Starting Cloudflare monitor for: {', '.join(TARGET_LOCATIONS)}")
    if slack_client and SLACK_CHANNEL: logging.info(f"slack: Notifications enabled for channel '{SLACK_CHANNEL}'")
    if OPSGENIE_ENABLED and OPSGENIE_API_KEY: logging.info(f"opsgenie: Notifications enabled.")

    while True:
        try:
            logging.info("🔄 Starting new status check cycle...")
            components = fetch_components()
            if not components:
                time.sleep(SLEEP_INTERVAL)
                continue
            
            current_matches = find_matching_components(components, TARGET_LOCATIONS)
            for loc, data in current_matches.items():
                if data["status"] != last_statuses.get(loc):
                    label = STATUS_LABEL.get(data["status"], data["status"])
                    logging.info(f"🔔 STATUS CHANGE: {loc.title()} → {label} (Component: {data['component_name']})")
                    
                    # ==> [PERUBAHAN] Panggil kedua fungsi notifikasi <==
                    send_slack_alert(loc, data["component_name"], data["status"])
                    send_opsgenie_alert(loc, data["component_name"], data["status"])
                    # ==> ------------------------------------ <==

                    last_statuses[loc] = data["status"]
                    save_last_statuses()

        except Exception as e:
            logging.exception(f"💥 Unexpected error in main loop: {e}")
        logging.debug(f"💤 Sleeping for {SLEEP_INTERVAL} seconds...")
        time.sleep(SLEEP_INTERVAL)

if __name__ == "__main__":
    main()