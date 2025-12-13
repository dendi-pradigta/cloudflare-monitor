#!/usr/bin/env python3
# notifications.py - Shared notification functions

import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ========================
# 🔧 CONFIGURATION
# ========================

# Slack Configuration
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#alerts").strip()

# Opsgenie Configuration
OPSGENIE_API_KEY = os.getenv("OPSGENIE_API_KEY", "").strip()
OPSGENIE_ENABLED = bool(OPSGENIE_API_KEY)

# Email Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
EMAIL_TO = os.getenv("EMAIL_TO", "").strip()

# Status labels
STATUS_LABEL = {
    "operational": "✅ Operational",
    "degraded_performance": "⚠️ Degraded Performance",
    "partial_outage": "🔴 Partial Outage",
    "major_outage": "🚨 Major Outage",
    "under_maintenance": "🔧 Under Maintenance",
    "investigating": "🔍 Investigating",
    "identified": "🔍 Identified",
    "monitoring": "👀 Monitoring",
    "resolved": "✅ Resolved",
    "scheduled": "📅 Scheduled",
    "in_progress": "🔄 In Progress",
    "completed": "✅ Completed",
    "postmortem": "📋 Postmortem",
}

# Initialize Slack client
slack_client: Optional[WebClient] = None
if SLACK_BOT_TOKEN:
    try:
        slack_client = WebClient(token=SLACK_BOT_TOKEN)
        # Test connection
        slack_client.auth_test()
        logging.info("Slack client initialized successfully")
    except SlackApiError as e:
        logging.warning(f"Failed to initialize Slack client: {e}")
        slack_client = None
    except Exception as e:
        logging.warning(f"Error initializing Slack client: {e}")
        slack_client = None

# ========================
# 📧 EMAIL FUNCTIONS
# ========================


def send_email_alert(subject: str, message: str) -> bool:
    """Send email alert"""
    if not all([SMTP_USERNAME, SMTP_PASSWORD, EMAIL_TO]):
        logging.warning("Email credentials not configured")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USERNAME
        msg["To"] = EMAIL_TO
        msg["Subject"] = subject

        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        logging.info(f"Email alert sent: {subject}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        return False


# ========================
# 💬 SLACK FUNCTIONS
# ========================


def send_slack_alert(
    title: str,
    message: Optional[str] = None,
    color: str = "danger",
    location: Optional[str] = None,
    incident_id: Optional[str] = None,
    fields: Optional[list] = None,
    status: Optional[str] = None,
    link: Optional[str] = None,
) -> bool:
    """Send Slack alert"""
    if not slack_client:
        logging.warning("Slack client not available")
        return False

    try:
        # Build attachment
        attachment = {
            "color": color,
            "title": title,
            "footer": "Cloudflare Monitor",
            "ts": int(time.time()),
        }

        # Add message if provided
        if message:
            attachment["text"] = message

        # Build fields list
        fields_list = []
        if location:
            fields_list.append({"title": "Location", "value": location, "short": True})
        if incident_id:
            fields_list.append(
                {"title": "Incident ID", "value": incident_id, "short": True}
            )
        if status:
            fields_list.append({"title": "Status", "value": status, "short": True})
        if link:
            fields_list.append({"title": "Link", "value": link, "short": False})

        # Add custom fields if provided
        if fields:
            fields_list.extend(fields)

        if fields_list:
            attachment["fields"] = fields_list

        slack_client.chat_postMessage(
            channel=SLACK_CHANNEL,
            attachments=[attachment],
        )

        logging.info(f"Slack alert sent: {title}")
        return True
    except SlackApiError as e:
        logging.error(f"Failed to send Slack alert: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error sending Slack alert: {e}")
        return False


def send_restart_summary_notification(
    component_changes: list,
    location_type: str = "location",
    last_statuses: Optional[dict] = None,
) -> bool:
    """Send restart summary notification to Slack"""
    if not slack_client or not component_changes:
        return False

    try:
        message = "🔄 **Monitor Restarted**\n\n"
        message += f"Found {len(component_changes)} components with status changes:\n\n"

        for change in component_changes:
            location = change.get("location", "Unknown")
            old_status = change.get("old_status", "Unknown")
            new_status = change.get("new_status", "Unknown")
            message += f"• **{location}**: {old_status} → {new_status}\n"

        message += "\nMonitoring resumed..."

        return send_slack_alert(
            title="🔄 Cloudflare Monitor Restarted",
            message=message,
            color="warning",
        )
    except Exception as e:
        logging.error(f"Failed to send restart summary: {e}")
        return False


# ========================
# 🚨 OPSGENIE FUNCTIONS
# ========================


def send_opsgenie_alert(
    message: str,
    alias: Optional[str] = None,
    description: Optional[str] = None,
    priority: str = "P3",
    entity: Optional[str] = None,
    status: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> bool:
    """Send Opsgenie alert"""
    if not OPSGENIE_API_KEY:
        logging.warning("Opsgenie API key not configured")
        return False

    try:
        url = "https://api.opsgenie.com/v2/alerts"
        headers = {
            "Authorization": f"GenieKey {OPSGENIE_API_KEY}",
            "Content-Type": "application/json",
        }

        payload: dict = {
            "message": message,
            "priority": priority,
            "source": "Cloudflare Monitor",
        }

        if alias:
            payload["alias"] = alias
        if description:
            payload["description"] = description
        if entity:
            payload["entity"] = entity
        if status:
            payload["status"] = status
        if tags:
            payload["tags"] = list(tags)  # Ensure it's a list

        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()

        logging.info(f"Opsgenie alert sent: {message}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send Opsgenie alert: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error sending Opsgenie alert: {e}")
        return False


def close_opsgenie_alert(alias: str) -> bool:
    """Close Opsgenie alert by alias"""
    if not OPSGENIE_API_KEY:
        return False

    try:
        url = f"https://api.opsgenie.com/v2/alerts/{alias}/close?identifierType=alias"
        headers = {
            "Authorization": f"GenieKey {OPSGENIE_API_KEY}",
            "Content-Type": "application/json",
        }

        response = requests.post(url, headers=headers, timeout=30)
        response.raise_for_status()

        logging.info(f"Opsgenie alert closed: {alias}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to close Opsgenie alert: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error closing Opsgenie alert: {e}")
        return False


# ========================
# 📊 NOTIFICATION COORDINATOR
# ========================


def send_component_alert(
    location: str,
    component_name: str,
    old_status: str,
    new_status: str,
    incident_id: Optional[str] = None,
) -> bool:
    """Send coordinated alert for component status change"""
    status_emoji = (
        "🔴" if "outage" in new_status else "⚠️" if "degraded" in new_status else "✅"
    )

    title = f"{status_emoji} Cloudflare Status Change - {location}"
    message = (
        f"Component: **{component_name}**\n"
        f"Status: {STATUS_LABEL.get(old_status, old_status)} → {STATUS_LABEL.get(new_status, new_status)}"
    )

    # Send to all configured channels
    success = True

    # Slack
    if slack_client:
        success &= send_slack_alert(
            title=title,
            message=message,
            color="danger" if "outage" in new_status else "warning",
            location=location,
            incident_id=incident_id,
        )

    # Opsgenie
    if OPSGENIE_ENABLED:
        alias = f"cloudflare-{location.lower().replace(' ', '-')}"
        description = (
            f"{component_name} status changed from {old_status} to {new_status}"
        )
        success &= send_opsgenie_alert(
            message=title,
            alias=alias,
            description=description,
            priority="P1"
            if "major_outage" in new_status
            else "P2"
            if "outage" in new_status
            else "P3",
            entity=location,
        )

    # Email
    if SMTP_USERNAME and SMTP_PASSWORD and EMAIL_TO:
        email_message = f"{message}\n\nLocation: {location}"
        if incident_id:
            email_message += f"\nIncident ID: {incident_id}"
        success &= send_email_alert(title, email_message)

    return success


def send_incident_alert(
    incident_name: str,
    incident_status: str,
    incident_impact: str,
    incident_id: str,
    incident_updates: Optional[list] = None,
) -> bool:
    """Send coordinated alert for incident status change"""
    status_emoji = (
        "🚨"
        if incident_status == "investigating"
        else "🔍"
        if incident_status == "identified"
        else "👀"
        if incident_status == "monitoring"
        else "✅"
    )

    title = f"{status_emoji} Cloudflare Incident - {incident_name}"
    message = (
        f"Incident ID: {incident_id}\n"
        f"Status: {STATUS_LABEL.get(incident_status, incident_status)}\n"
        f"Impact: {incident_impact}"
    )

    if incident_updates:
        latest_update = incident_updates[0] if incident_updates else None
        if latest_update:
            message += f"\n\nLatest Update:\n{latest_update.get('body', 'No details available')}"

    # Send to all configured channels
    success = True

    # Slack
    if slack_client:
        success &= send_slack_alert(
            title=title,
            message=message,
            color="danger"
            if incident_status in ["investigating", "identified"]
            else "warning",
            incident_id=incident_id,
        )

    # Opsgenie
    if OPSGENIE_ENABLED:
        alias = f"incident-{incident_id}"
        description = f"Incident: {incident_name}\nStatus: {incident_status}\nImpact: {incident_impact}"

        if incident_status == "resolved":
            success &= close_opsgenie_alert(alias)
        else:
            success &= send_opsgenie_alert(
                message=title,
                alias=alias,
                description=description,
                priority="P1" if incident_status == "investigating" else "P2",
                entity=incident_id,
            )

    # Email
    if SMTP_USERNAME and SMTP_PASSWORD and EMAIL_TO:
        email_message = f"{message}\n\nIncident Name: {incident_name}"
        success &= send_email_alert(title, email_message)

    return success
