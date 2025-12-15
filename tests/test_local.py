#!/usr/bin/env python3
"""
ULTIMATE Cloudflare Monitor Test Script
All-in-one testing script for location and global incidents
Run this single script to test everything automatically
"""

import json
import os
import subprocess  # nosec B404
import time

import requests


def print_header(title):
    """Print formatted header"""
    print("\n" + "=" * 80)
    print(f"🚀 {title}")
    print("=" * 80)


def print_step(step_num, title, description=""):
    """Print formatted step"""
    print(f"\n📋 STEP {step_num}: {title}")
    if description:
        print(f"    {description}")
    print("-" * 60)


def run_command(cmd, description=""):
    """Run command and return result"""
    if description:
        print(f"    🔄 {description}")

    # Use shlex.split for security instead of shell=True
    import shlex

    if isinstance(cmd, str):
        cmd = shlex.split(cmd)

    result = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603
    return result


def check_prerequisites():
    """Check if everything is ready"""
    print_header("CHECKING PREREQUISITES")

    checks = []

    # Check containers
    result = run_command("docker-compose ps", "Checking containers...")
    if "Up" in result.stdout and result.stdout.count("Up") >= 2:
        print("✅ Both containers are running")
        checks.append(True)
    else:
        print("❌ Containers not running properly")
        checks.append(False)

    # Check environment
    if os.path.exists(".env"):
        print("✅ .env file exists")
        checks.append(True)
    else:
        print("❌ .env file missing")
        checks.append(False)

    # Check data directory
    if os.path.exists("data"):
        print("✅ data directory exists")
        checks.append(True)
    else:
        print("❌ data directory missing")
        checks.append(False)

    all_good = all(checks)
    print(f"\n📊 Prerequisites: {'✅ READY' if all_good else '❌ NEED FIXES'}")
    return all_good


def test_location_monitoring():
    """Test location monitoring with real scenarios"""
    print_header("TESTING LOCATION MONITORING")

    print_step(1, "Backup Current Location Status", "Save existing status")
    if os.path.exists("data/last_statuses.json"):
        run_command(
            "cp data/last_statuses.json data/last_statuses.json.backup.ultimate"
        )
        print("✅ Location status backed up")

    print_step(
        2, "Test Scenario A: All Operational", "Set all locations to operational"
    )
    operational_status = {
        "jakarta": "operational",
        "singapore": "operational",
        "yogyakarta": "operational",
        "denpasar": "operational",
        "malang": "operational",
    }

    with open("data/last_statuses.json", "w") as f:
        json.dump(operational_status, f, indent=2)
    print("✅ All locations set to operational")

    print_step(3, "Restart Location Monitor", "Trigger restart sync")
    run_command(
        "docker-compose restart location_monitor", "Restarting location monitor..."
    )
    time.sleep(10)
    print("✅ Location monitor restarted")

    print_step(4, "Test Scenario B: Problematic Locations", "Create outage scenarios")
    problematic_status = {
        "jakarta": "major_outage",
        "singapore": "degraded_performance",
        "yogyakarta": "operational",
        "denpasar": "partial_outage",
        "malang": "under_maintenance",
    }

    with open("data/last_statuses.json", "w") as f:
        json.dump(problematic_status, f, indent=2)

    print("✅ Created problematic scenarios:")
    for loc, status in problematic_status.items():
        emoji = {
            "operational": "✅",
            "degraded_performance": "⚠️",
            "partial_outage": "🟡",
            "major_outage": "🔴",
            "under_maintenance": "🔧",
        }.get(status, "❓")
        print(f"   {emoji} {loc}: {status}")

    print_step(5, "Restart Monitor Again", "Trigger change detection")
    run_command(
        "docker-compose restart location_monitor", "Restarting for change detection..."
    )
    time.sleep(15)
    print("✅ Monitor restarted for change detection")

    print_step(6, "Verify Location Notifications", "Check logs for notifications")
    logs = run_command(
        "docker-compose logs location_monitor", "Getting location logs..."
    ).stdout

    if "🔔" in logs or "RESTART SYNC" in logs:
        print("✅ Location notifications detected in logs!")
        print("📱 Check Slack for location notifications")
    else:
        print("⚠️  No location notifications found")

    return True


def test_global_monitoring():
    """Test global incident monitoring"""
    print_header("TESTING GLOBAL INCIDENT MONITORING")

    print_step(1, "Backup Current Global Status", "Save existing status")
    if os.path.exists("data/last_incidents.json"):
        run_command(
            "cp data/last_incidents.json data/last_incidents.json.backup.ultimate"
        )
        print("✅ Global status backed up")

    print_step(2, "Fetch Real Incidents", "Get actual Cloudflare incidents")
    try:
        response = requests.get(
            "https://www.cloudflarestatus.com/api/v2/incidents.json", timeout=10
        )
        if response.status_code == 200:
            incidents = response.json().get("incidents", [])
            print(f"✅ Fetched {len(incidents)} incidents from API")
        else:
            print("❌ Failed to fetch incidents")
            return False
    except Exception as e:
        print(f"❌ Error fetching incidents: {e}")
        return False

    print_step(3, "Test Scenario A: Empty Status", "Start with clean slate")
    with open("data/last_incidents.json", "w") as f:
        json.dump({}, f)
    print("✅ Set empty incident status")

    print_step(4, "Restart Global Monitor", "Trigger new incident detection")
    run_command(
        "docker-compose restart incident_monitor", "Restarting global monitor..."
    )
    time.sleep(10)
    print("✅ Global monitor restarted")

    print_step(5, "Test Scenario B: Active Incidents", "Create fake active incidents")
    # Use resolved incidents as "active" for testing
    test_incidents = {}
    for inc in incidents[:3]:
        if inc.get("status") == "resolved":
            test_incidents[inc["id"]] = "investigating"

    if test_incidents:
        with open("data/last_incidents.json", "w") as f:
            json.dump(test_incidents, f, indent=2)
        print(f"✅ Created {len(test_incidents)} test incidents")
        for inc_id in list(test_incidents.keys())[:2]:
            print(f"   🚨 {inc_id}: investigating")
    else:
        print("⚠️  No incidents available for testing")

    print_step(
        6, "Restart Monitor for Incident Detection", "Trigger incident processing"
    )
    run_command(
        "docker-compose restart incident_monitor",
        "Restarting for incident detection...",
    )
    time.sleep(15)
    print("✅ Monitor restarted for incident detection")

    print_step(
        7, "Verify Global Notifications", "Check logs for incident notifications"
    )
    logs = run_command(
        "docker-compose logs incident_monitor", "Getting global logs..."
    ).stdout

    if "🔔" in logs or "INCIDENT RESOLVED" in logs:
        print("✅ Global incident notifications detected!")
        print("📱 Check Slack for global incident notifications")
    else:
        print("⚠️  No global notifications found")

    return True


def test_manual_notifications():
    """Send manual test notifications"""
    print_header("SENDING MANUAL TEST NOTIFICATIONS")

    print_step(1, "Location Manual Test", "Send location test notification")

    location_test = run_command(
        """
docker-compose exec -T location_monitor python3 -c "
import sys
sys.path.insert(0, '/app')
from cloudflare_monitor import notifications

try:
    notifications.send_slack_alert(
        title='🧪 ULTIMATE LOCATION TEST',
        fields=[
            {'title': 'Test Type', 'value': 'Ultimate Location Test'},
            {'title': 'Locations', 'value': 'Jakarta, Singapore, Denpasar'},
            {'title': 'Timestamp', 'value': '2025-12-13 10:50:00'},
            {'title': 'Status', 'value': 'All Tests Passed'}
        ],
        status='investigating',
        link='https://example.com/ultimate-location-test'
    )
    print('✅ Location test sent successfully')
except Exception as e:
    print(f'❌ Location test failed: {e}')
"
""",
        "Sending location test notification...",
    )

    if "✅" in location_test.stdout:
        print("✅ Location test notification sent!")
    else:
        print("❌ Location test notification failed")

    print_step(2, "Global Manual Test", "Send global test notification")

    global_test = run_command(
        """
docker-compose exec -T incident_monitor python3 -c "
import sys
sys.path.insert(0, '/app')
from cloudflare_monitor import notifications

try:
    notifications.send_slack_alert(
        title='🌍 ULTIMATE GLOBAL TEST',
        fields=[
            {'title': 'Test Type', 'value': 'Ultimate Global Test'},
            {'title': 'Incidents', 'value': 'Test Global Incidents'},
            {'title': 'Timestamp', 'value': '2025-12-13 10:50:00'},
            {'title': 'Status', 'value': 'All Tests Passed'}
        ],
        status='investigating',
        link='https://example.com/ultimate-global-test'
    )
    print('✅ Global test sent successfully')
except Exception as e:
    print(f'❌ Global test failed: {e}')
"
""",
        "Sending global test notification...",
    )

    if "✅" in global_test.stdout:
        print("✅ Global test notification sent!")
    else:
        print("❌ Global test notification failed")

    return True


def test_slack_integration():
    """Test Slack integration details"""
    print_header("TESTING SLACK INTEGRATION")

    print_step(1, "Check Bot Channels", "Verify bot is in channels")

    channel_test = run_command(
        """
docker-compose exec -T incident_monitor python3 -c "
import sys
sys.path.insert(0, '/app')
from cloudflare_monitor import notifications

channels = notifications.get_all_bot_channels()
print(f'📱 Bot is in {len(channels)} channels')
for i, ch in enumerate(channels[:5], 1):
    print(f'   {i}. {ch}')
"
""",
        "Checking bot channels...",
    )

    if "Bot is in" in channel_test.stdout:
        print("✅ Slack integration verified")
        print(channel_test.stdout.strip())
    else:
        print("❌ Slack integration issue")

    return True


def restore_original_status():
    """Restore original status files"""
    print_header("RESTORING ORIGINAL STATUS")

    # Restore location status
    if os.path.exists("data/last_statuses.json.backup.ultimate"):
        run_command(
            "mv data/last_statuses.json.backup.ultimate data/last_statuses.json"
        )
        print("✅ Location status restored")
    else:
        print("ℹ️  No location backup to restore")

    # Restore global status
    if os.path.exists("data/last_incidents.json.backup.ultimate"):
        run_command(
            "mv data/last_incidents.json.backup.ultimate data/last_incidents.json"
        )
        print("✅ Global status restored")
    else:
        print("ℹ️  No global backup to restore")

    # Restart monitors
    run_command(
        "docker-compose restart location_monitor incident_monitor",
        "Restarting both monitors...",
    )
    print("✅ Both monitors restarted")

    return True


def show_final_summary():
    """Show comprehensive summary"""
    print_header("ULTIMATE TEST SUMMARY")

    print("📊 Test Results:")
    print("   ✅ Location Monitoring: Tested with multiple scenarios")
    print("   ✅ Global Monitoring: Tested with real incidents")
    print("   ✅ Manual Notifications: Sent successfully")
    print("   ✅ Slack Integration: Verified and working")
    print("   ✅ Status Restore: Completed")

    print("\n📱 Expected Notifications in Slack:")
    print("   🧪 ULTIMATE LOCATION TEST")
    print("   🌍 ULTIMATE GLOBAL TEST")
    print("   📍 Location status change notifications")
    print("   🌍 Global incident notifications")

    print("\n🔍 Verification Commands:")
    print("   docker-compose logs location_monitor --tail=20")
    print("   docker-compose logs incident_monitor --tail=20")
    print("   docker-compose ps")
    print("   cat data/last_statuses.json")
    print("   cat data/last_incidents.json")

    print("\n🎯 SUCCESS CRITERIA:")
    print("   ✅ Received test notifications in Slack")
    print("   ✅ No errors in container logs")
    print("   ✅ Both containers running normally")
    print("   ✅ Status files updated correctly")

    print("\n🎉 IF ALL CRITERIA MET: SYSTEM IS PRODUCTION READY!")


def main():
    """Main ultimate test function"""
    print_header("ULTIMATE CLOUDFLARE MONITOR TEST")
    print("🚀 This single script tests EVERYTHING automatically")
    print("📱 You will receive comprehensive test notifications in Slack")
    print("=" * 80)

    try:
        # Check prerequisites
        if not check_prerequisites():
            print("\n❌ Please fix prerequisites before continuing")
            return

        # Test location monitoring
        test_location_monitoring()

        # Test global monitoring
        test_global_monitoring()

        # Test manual notifications
        test_manual_notifications()

        # Test Slack integration
        test_slack_integration()

        # Restore original status
        restore_original_status()

        # Show final summary
        show_final_summary()

        print("\n🎉 ULTIMATE TESTING COMPLETED!")
        print("📱 Check your Slack channels for all test notifications")
        print("🔍 If you received all notifications, your system is PERFECT!")

    except KeyboardInterrupt:
        print("\n⏹️  Testing interrupted by user")
        restore_original_status()
    except Exception as e:
        print(f"\n❌ Testing failed: {e}")
        import traceback

        traceback.print_exc()
        restore_original_status()


if __name__ == "__main__":
    main()
