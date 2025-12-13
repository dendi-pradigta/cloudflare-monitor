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

# Initialize Slack Client
slack_client = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None

# Status Mappings
STATUS_LABEL = { "operational": "Operational", "partial_outage": "Partially Re-routed", "major_outage": "Re-routed", "degraded_performance": "Degraded Performance", "under_maintenance": "Under Maintenance", "investigating": "Investigating", "identified": "Identified", "monitoring": "Monitoring", "resolved": "Resolved" }
STATUS_EMOJI = { "operational": ":white_check_mark:", "partial_outage": ":warning:", "major_outage": ":exclamation:", "degraded_performance": ":zap:", "under_maintenance": ":construction:", "investigating": ":mag:", "identified": ":bulb:", "monitoring": ":eyes:", "resolved": ":heavy_check_mark:" }

def get_all_bot_channels():
    """
    Get all channels (public & private) where bot is a member.
    Returns: list of channel IDs
    """
    if not slack_client:
        return []
    
    all_channels = []
    try:
        # Get public channels
        public_response = slack_client.conversations_list(
            types="public_channel",
            exclude_archived=True,
            limit=200
        )
        
        # Get private channels
        private_response = slack_client.conversations_list(
            types="private_channel",
            exclude_archived=True,
            limit=200
        )
        
        # Filter only channels where bot is a member
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
    Send Slack alert to all channels where bot is a member.
    - title: Main alert title
    - fields: List of dictionaries for section fields
    - status: Status string to determine color and emoji
    - link: URL to display in footer
    """
    if not slack_client:
        return

    # Get all channels where bot is a member
    channels = get_all_bot_channels()
    
    if not channels:
        logging.warning("No channels found to send Slack alert")
        return

    label = STATUS_LABEL.get(status, status.replace("_", " ").title())
    emoji = STATUS_EMOJI.get(status, ":question:")
    
    color = "#2eb886"  # Green for operational/resolved
    if status in ["partial_outage", "degraded_performance", "under_maintenance", "investigating", "identified", "monitoring"]:
        color = "#daa038"  # Yellow
    elif status in ["major_outage"]:
        color = "#a30200"  # Red

    # Create fields for Slack blocks
    mrkdwn_fields = []
    for field in fields:
        mrkdwn_fields.append({"type": "mrkdwn", "text": f"*{field['title']}:*\n{field['value']}"})

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f":cloudflare: {title}", "emoji": True}},
        {"type": "section", "fields": mrkdwn_fields},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{emoji} Status changed to {label}*"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Cloudflare Monitor | <{link}|View Details>"}]}
    ]

    # Send to all channels with delay for rate limiting
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
            
            # Delay 1 second between messages to avoid rate limiting
            time.sleep(1)
            
        except Exception as e:
            failed_count += 1
            logging.warning(f"Failed to send Slack notification to channel {channel_id}: {e}")
            # Skip this channel and continue to next channel
            continue
    
    logging.info(f"Slack notification sent: {title} - {label} | Success: {success_count}, Failed: {failed_count}")

def send_opsgenie_alert(alias: str, message: str, description: str, status: str, tags: list):
    """Create or close alert in Opsgenie."""
    if not OPSGENIE_ENABLED or not OPSGENIE_API_KEY:
        if OPSGENIE_ENABLED:
            logging.warning("Opsgenie enabled but API Key is missing.")
        return

    # If status is considered "resolved", we close existing alert.
    if status in ['operational', 'resolved']:
        url = f"{OPSGENIE_API_URL}/v2/alerts/{alias}/close?identifierType=alias"
        payload = {"note": f"Status kembali normal: {status.title()}"}
        log_message = f"Closing Opsgenie alert with alias: {alias}"
    else:
        # If there's a problem, we create or update alert.
        url = f"{OPSGENIE_API_URL}/v2/alerts"
        priority_map = {
            "critical": "P1", # For Incidents
            "major_outage": "P1", # For Components
            "major": "P2", # For Incidents
            "partial_outage": "P2", # For Components
            "minor": "P3", # For Incidents
            "degraded_performance": "P3", # For Components
            "under_maintenance": "P5",
        }
        # Use 'status' for incidents (critical, major, minor), or component status for PoP.
        payload = {
            "message": message,
            "alias": alias,
            "description": description,
            "priority": priority_map.get(status, "P4"), # Default to P4 if not in map
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