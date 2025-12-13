#!/usr/bin/env python3
import os
import sys

sys.path.append("/app")

import notifications

print("Testing channel discovery...")
print(f"Slack client available: {notifications.slack_client is not None}")

if notifications.slack_client:
    channels = notifications.get_all_bot_channels()
    print(f"Found {len(channels)} channels:")
    for i, channel_id in enumerate(channels[:5]):  # Show first 5
        print(f"  {i + 1}. {channel_id}")

    if len(channels) > 5:
        print(f"  ... and {len(channels) - 5} more")
else:
    print("No slack client")
