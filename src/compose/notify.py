"""Desktop notifications: when a run needs a person, or ends.

Sent with the command each OS already has: ``osascript`` on macOS, ``notify-send`` on Linux
and a PowerShell toast on Windows, showing only the message: no title, no logo. A notification is
a courtesy: it never raises, never blocks a run for more than a few seconds, and is skipped
when ``COMPOSE_NOTIFY`` is off.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape as xml_escape

log = logging.getLogger(__name__)

TIMEOUT_S = 5
OFF = frozenset({"0", "false", "no", "off"})


def enabled(configured: bool = True) -> bool:
    """Notifications are on unless the config or ``COMPOSE_NOTIFY`` turns them off."""
    return configured and os.environ.get("COMPOSE_NOTIFY", "").strip().lower() not in OFF


def _applescript(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _powershell(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def command(message: str, platform: str | None = None) -> list[str] | None:
    """The command that shows the notification here, or None when there's none."""
    platform = platform or sys.platform
    if platform == "darwin":
        return ["osascript", "-e", f"display notification {_applescript(message)}"]
    if platform.startswith("win"):
        xml = (
            "<toast><visual><binding template='ToastGeneric'>"
            f"<text>{xml_escape(message)}</text>"
            "</binding></visual></toast>"
        )
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications,"
            " ContentType=WindowsRuntime] > $null;"
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument,"
            " ContentType=WindowsRuntime] > $null;"
            "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
            f"$x.LoadXml({_powershell(xml)});"
            "$t = [Windows.UI.Notifications.ToastNotification]::new($x);"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
            "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe'"
            ").Show($t)"
        )
        return ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
    if shutil.which("notify-send"):
        return ["notify-send", "--app-name=compose", message]
    return None


def notify(message: str, *, configured: bool = True) -> None:
    """Show ``message`` as a desktop notification, if notifications are on. Never raises."""
    if not enabled(configured):
        return
    try:
        argv = command(message)
        if argv is None:
            return
        subprocess.run(argv, capture_output=True, timeout=TIMEOUT_S, check=False)
    except Exception as exc:  # a notification must never break a run
        log.debug("notification failed: %s", exc)


def setup_hint(platform: str | None = None) -> str:
    """What a person must allow, once, for notifications to appear on this system."""
    platform = platform or sys.platform
    if platform == "darwin":
        return (
            'Desktop notifications: allow "Script Editor" in System Settings > Notifications'
            " (and turn off Focus / Do Not Disturb) to see them."
        )
    if platform.startswith("win"):
        return (
            'Desktop notifications: allow "Windows PowerShell" in Settings > System >'
            " Notifications to see them."
        )
    return "Desktop notifications use notify-send (libnotify): install it to see them."
