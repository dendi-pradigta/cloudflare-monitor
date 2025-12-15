# cloudflare_monitor package
from .monitor import main as main
from .incident import main as incident_main
from .notifications import STATUS_LABEL, send_slack_alert
