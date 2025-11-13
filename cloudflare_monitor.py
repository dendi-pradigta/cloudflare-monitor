#!/usr/bin/env python3
import requests
import time
import logging
import os
import sys
import json
import signal
from logging.handlers import RotatingFileHandler
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ==> [PERBAIKAN #1] - Tambahkan ini untuk membaca file .env secara otomatis
from dotenv import load_dotenv
load_dotenv()
# <==

# ========================
# 🔧 CONFIGURATION
# ========================

TARGET_LOCATIONS = [
    loc.strip().lower()
    for loc in os.getenv("TARGET_LOCATIONS", "jakarta,singapore").split(",")
    if loc.strip()
]

# ==> [PERBAIKAN #2] - Kembalikan ke cara yang benar untuk membaca variabel
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "").strip()

# Inisialisasi Slack Client jika token ada
slack_client = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None
# <==

COMPONENTS_URL = os.getenv(
    "COMPONENTS_URL",
    "https://www.cloudflarestatus.com/api/v2/components.json"
).strip()

SLEEP_INTERVAL = int(os.getenv("SLEEP_INTERVAL", "60"))

# ==> [PERBAIKAN #3] - Beri nilai default yang aman jika di .env tidak diset
STATUS_FILE = os.getenv("STATUS_FILE", "data/last_statuses.json") # Simpan di folder lokal
# <==

# ... sisa skrip Anda dari sini ke bawah sudah benar dan tidak perlu diubah ...
# (Saya sertakan lagi untuk kelengkapan)

# Setup log level
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
logger = logging.getLogger()

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
    dir_name = os.path.dirname(STATUS_FILE)
    if dir_name: # Cek jika ada nama direktori (bukan file di root)
        os.makedirs(dir_name, exist_ok=True)
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(last_statuses, f)
    except Exception as e:
        logging.error("Failed to save last statuses to %s: %s", STATUS_FILE, e)

# --- GANTI FUNGSI LAMA DENGAN YANG INI ---
def send_slack_alert(location: str, component_name: str, status: str):
    """Mengirim notifikasi Slack menggunakan Bot Token API dengan warna."""
    if not slack_client or not SLACK_CHANNEL:
        logging.warning("SLACK_BOT_TOKEN or SLACK_CHANNEL is not set! Skipping Slack notification.")
        return

    if not SLACK_BOT_TOKEN.startswith("xoxb-"):
        logging.error("Invalid Slack Token format. Must start with 'xoxb-'.")
        return

    label = STATUS_LABEL.get(status, status)
    emoji = STATUS_EMOJI.get(status, ":question:")

    # === [PERUBAHAN] Menentukan warna berdasarkan status ===
    # Hijau (good), Kuning (warning), Merah (danger)
    color = "#2eb886"  # Default: Hijau untuk 'operational'
    if status in ["partial_outage", "degraded_performance", "under_maintenance"]:
        color = "#daa038"  # Kuning/Oranye untuk peringatan
    elif status == "major_outage":
        color = "#a30200"  # Merah untuk gangguan besar
    # =======================================================

    # Block Kit ini tetap sama, mendefinisikan isi pesan
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":earth_asia: Cloudflare Status Update",
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Location:*\n{location.title()}"},
                {"type": "mrkdwn", "text": f"*Component:*\n{component_name}"},
                {"type": "mrkdwn", "text": f"*Status:*\n{emoji} {label}"}
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Cloudflare Monitor | <https://www.cloudflarestatus.com|View Status Page>"
                }
            ]
        }
    ]

    try:
        # === [PERUBAHAN] Membungkus blocks di dalam attachments untuk mendapatkan warna ===
        slack_client.chat_postMessage(
            channel=SLACK_CHANNEL,
            text=f"Cloudflare Status Update: {location.title()} is now {label}",  # Fallback text
            attachments=[{
                "color": color,  # Memberikan warna pada garis di kiri
                "blocks": blocks  # Menempatkan konten pesan kita di dalam attachment
            }]
        )
        # =================================================================================
        logging.info(f"Slack notification sent for {location.title()} to channel {SLACK_CHANNEL}")
    except SlackApiError as e:
        logging.error(f"Error sending Slack notification: {e.response['error']}")
    except Exception as e:
        logging.error(f"An unexpected error occurred when sending to Slack: {e}")

def fetch_components():
    try:
        logging.debug("Fetching components from Cloudflare...")
        resp = requests.get(COMPONENTS_URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("components", [])
    except Exception as e:
        logging.exception("Failed to fetch Cloudflare status: %s", e)
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

def graceful_shutdown(sig, frame):
    logging.info("🛑 Received signal %s. Shutting down gracefully...", sig)
    sys.exit(0)

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

def main():
    global last_statuses
    if SLACK_BOT_TOKEN and not SLACK_CHANNEL:
        logging.critical("SLACK_BOT_TOKEN is set, but SLACK_CHANNEL is missing!")
        sys.exit(1)

    last_statuses = load_last_statuses()
    logging.info(f"🚀 Starting Cloudflare monitor for: {', '.join(TARGET_LOCATIONS) or '(none)'}")
    logging.info(f"🔁 Check interval: {SLEEP_INTERVAL} seconds")
    logging.info(f"💾 Status file: {STATUS_FILE}")
    if slack_client and SLACK_CHANNEL:
        logging.info(f"slack: Notifications will be sent to channel '{SLACK_CHANNEL}'")
    else:
        logging.warning("slack: Slack notifications are disabled (token/channel not set).")

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
                    send_slack_alert(loc, data["component_name"], data["status"])
                    last_statuses[loc] = data["status"]
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
