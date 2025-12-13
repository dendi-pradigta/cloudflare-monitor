# notifications.py
import os
import logging
import requests
import time
from slack_sdk import WebClient

# ========================
# 🔧 CONFIGURATION
# ========================
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()
OPSGENIE_ENABLED = os.getenv("OPSGENIE_ENABLED", "false").lower() == "true"
OPSGENIE_API_KEY = os.getenv("OPSGENIE_API_KEY", "").strip()
OPSGENIE_API_URL = os.getenv("OPSGENIE_API_URL", "https://api.opsgenie.com").strip()

# Inisialisasi Slack Client
slack_client = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None

# Status Mappings
STATUS_LABEL = { "operational": "Operational", "partial_outage": "Partially Re-routed", "major_outage": "Re-routed", "degraded_performance": "Degraded Performance", "under_maintenance": "Under Maintenance", "investigating": "Investigating", "identified": "Identified", "monitoring": "Monitoring", "resolved": "Resolved" }
STATUS_EMOJI = { "operational": ":white_check_mark:", "partial_outage": ":warning:", "major_outage": ":exclamation:", "degraded_performance": ":zap:", "under_maintenance": ":construction:", "investigating": ":mag:", "identified": ":bulb:", "monitoring": ":eyes:", "resolved": ":heavy_check_mark:" }

def get_all_bot_channels():
    """
    Mengambil semua channel (public & private) dimana bot adalah member.
    Returns: list of channel IDs
    """
    if not slack_client:
        return []
    
    all_channels = []
    try:
        # Ambil public channels
        public_response = slack_client.conversations_list(
            types="public_channel",
            exclude_archived=True,
            limit=200
        )
        
        # Ambil private channels
        private_response = slack_client.conversations_list(
            types="private_channel",
            exclude_archived=True,
            limit=200
        )
        
        # Filter hanya channel dimana bot adalah member
        for channel in public_response.get("channels", []):
            if channel.get("is_member"):
                all_channels.append(channel["id"])
        
        for channel in private_response.get("channels", []):
            if channel.get("is_member"):
                all_channels.append(channel["id"])
        
        logging.info(f"Found {len(all_channels)} channels where bot is a member")
        return all_channels
        
    except Exception as e:
        logging.error(f"Error fetching bot channels: {e}")
        return []

def send_slack_alert(title: str, fields: list, status: str, link: str = "https://www.cloudflarestatus.com"):
    """
    Mengirim alert Slack ke semua channel dimana bot adalah member.
    - title: Judul utama alert
    - fields: List of dictionaries untuk section fields
    - status: Status string untuk menentukan warna dan emoji
    - link: URL untuk dilihat di footer
    """
    if not slack_client:
        return

    # Dapatkan semua channel dimana bot adalah member
    channels = get_all_bot_channels()
    
    if not channels:
        logging.warning("No channels found to send Slack alert")
        return

    label = STATUS_LABEL.get(status, status.replace("_", " ").title())
    emoji = STATUS_EMOJI.get(status, ":question:")
    
    color = "#2eb886"  # Hijau untuk operational/resolved
    if status in ["partial_outage", "degraded_performance", "under_maintenance", "investigating", "identified", "monitoring"]:
        color = "#daa038"  # Kuning
    elif status in ["major_outage"]:
        color = "#a30200"  # Merah

    # Membuat fields untuk Slack blocks
    mrkdwn_fields = []
    for field in fields:
        mrkdwn_fields.append({"type": "mrkdwn", "text": f"*{field['title']}:*\n{field['value']}"})

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f":cloudflare: {title}", "emoji": True}},
        {"type": "section", "fields": mrkdwn_fields},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{emoji} Status changed to {label}*"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Cloudflare Monitor | <{link}|View Details>"}]}
    ]

    # Kirim ke semua channel dengan delay untuk rate limiting
    success_count = 0
    failed_count = 0
    
    for channel_id in channels:
        try:
            slack_client.chat_postMessage(
                channel=channel_id,
                text=f"{title}: Status changed to {label}",
                attachments=[{"color": color, "blocks": blocks}]
            )
            success_count += 1
            logging.debug(f"Slack notification sent to channel {channel_id}")
            
            # Delay 1 detik antar message untuk avoid rate limiting
            time.sleep(1)
            
        except Exception as e:
            failed_count += 1
            logging.warning(f"Failed to send Slack notification to channel {channel_id}: {e}")
            # Skip channel ini dan lanjut ke channel berikutnya
            continue
    
    logging.info(f"Slack notification sent: {title} - {label} | Success: {success_count}, Failed: {failed_count}")

def send_opsgenie_alert(alias: str, message: str, description: str, status: str, tags: list):
    """Membuat atau menutup alert di Opsgenie."""
    if not OPSGENIE_ENABLED or not OPSGENIE_API_KEY:
        if OPSGENIE_ENABLED:
            logging.warning("Opsgenie enabled but API Key is missing.")
        return

    # Jika status dianggap "selesai", kita tutup alert yang ada.
    if status in ['operational', 'resolved']:
        url = f"{OPSGENIE_API_URL}/v2/alerts/{alias}/close?identifierType=alias"
        payload = {"note": f"Status kembali normal: {status.title()}"}
        log_message = f"Closing Opsgenie alert with alias: {alias}"
    else:
        # Jika ada masalah, kita buat atau perbarui alert.
        url = f"{OPSGENIE_API_URL}/v2/alerts"
        priority_map = {
            "critical": "P1", # Untuk Insiden
            "major_outage": "P1", # Untuk Komponen
            "major": "P2", # Untuk Insiden
            "partial_outage": "P2", # Untuk Komponen
            "minor": "P3", # Untuk Insiden
            "degraded_performance": "P3", # Untuk Komponen
            "under_maintenance": "P5",
        }
        # Gunakan 'status' untuk insiden (critical, major, minor), atau status komponen untuk PoP.
        payload = {
            "message": message,
            "alias": alias,
            "description": description,
            "priority": priority_map.get(status, "P4"), # Default ke P4 jika tidak ada di map
            "tags": tags
        }
        log_message = f"Creating/updating Opsgenie alert for alias {alias} with priority {payload['priority']}"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"GenieKey {OPSGENIE_API_KEY}"
    }

    try:
        logging.info(log_message)
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logging.info(f"Opsgenie API call successful for alias {alias}. Request ID: {response.json().get('requestId')}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling Opsgenie API for alias {alias}: {e}")
        if e.response:
            logging.error(f"Opsgenie Response Body: {e.response.text}")