"""Cross-platform scheduler installation (launchd / cron / systemd)."""

import os
import sys
import shutil
import subprocess
import platform
import logging

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABEL = "com.hackmd-obsidian.sync"
MENUBAR_LABEL = "com.hackmd-obsidian.menubar"


def _get_launchd_plist_path():
    return os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def _get_menubar_plist_path():
    return os.path.expanduser(f"~/Library/LaunchAgents/{MENUBAR_LABEL}.plist")


def detect_platform():
    system = platform.system()
    if system == "Darwin":
        return "launchd"
    elif system == "Linux":
        # Check for systemd
        try:
            subprocess.run(
                ["systemctl", "--version"],
                capture_output=True,
                check=True,
            )
            return "systemd"
        except (FileNotFoundError, subprocess.CalledProcessError):
            return "cron"
    return "cron"


def install(config, python_path=None):
    scheduler = detect_platform()
    python = python_path or sys.executable
    interval = config.get("sync", {}).get("interval", 300)
    config_path = os.path.join(config["_config_dir"], "config.yaml")

    if scheduler == "launchd":
        return _install_launchd(python, config_path, interval)
    elif scheduler == "systemd":
        return _install_systemd(python, config_path, interval)
    else:
        return _install_cron(python, config_path, interval)


def uninstall():
    scheduler = detect_platform()
    if scheduler == "launchd":
        return _uninstall_launchd()
    elif scheduler == "systemd":
        return _uninstall_systemd()
    else:
        return _uninstall_cron()


def _install_launchd(python, config_path, interval):
    plist_path = _get_launchd_plist_path()
    log_path = os.path.expanduser("~/.config/hackmd-sync/sync.log")

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>hackmd_sync</string>
        <string>--config</string>
        <string>{config_path}</string>
        <string>run</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{SCRIPT_DIR}</string>
    <key>StartInterval</key>
    <integer>{interval}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>"""

    # Unload first if exists
    if os.path.exists(plist_path):
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)

    with open(plist_path, "w") as f:
        f.write(plist)

    subprocess.run(["launchctl", "load", plist_path], check=True)
    return f"launchd service installed: every {interval}s"


def _uninstall_launchd():
    plist_path = _get_launchd_plist_path()
    if os.path.exists(plist_path):
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        os.remove(plist_path)
        return "launchd service removed"
    return "No launchd service found"


def get_service_status():
    scheduler = detect_platform()
    status = {
        "scheduler": scheduler,
        "label": LABEL,
        "installed": False,
        "loaded": False,
        "running": False,
    }
    if scheduler == "launchd":
        plist_path = _get_launchd_plist_path()
        status["installed"] = os.path.exists(plist_path)
        result = subprocess.run(["launchctl", "list", LABEL], capture_output=True, text=True)
        if result.returncode == 0:
            status["loaded"] = True
            status["running"] = True
        return status
    status["installed"] = True
    status["loaded"] = True
    status["running"] = True
    return status


def start_service():
    scheduler = detect_platform()
    if scheduler == "launchd":
        plist_path = _get_launchd_plist_path()
        if not os.path.exists(plist_path):
            return "Service is not installed. Run install first."
        subprocess.run(["launchctl", "load", plist_path], check=True)
        return "Service started (launchd loaded)"
    return "Manual start is only implemented for launchd right now"


def stop_service():
    scheduler = detect_platform()
    if scheduler == "launchd":
        plist_path = _get_launchd_plist_path()
        if not os.path.exists(plist_path):
            return "Service is not installed."
        subprocess.run(["launchctl", "unload", plist_path], check=True)
        return "Service stopped (launchd unloaded)"
    return "Manual stop is only implemented for launchd right now"


def install_menubar(python, config_path):
    if detect_platform() != "launchd":
        return "Menu bar app is only supported on macOS/launchd"
    plist_path = _get_menubar_plist_path()
    log_path = os.path.expanduser("~/.config/hackmd-sync/menubar.log")
    gui_python = shutil.which("pythonw") or python
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{MENUBAR_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{gui_python}</string>
        <string>-m</string>
        <string>hackmd_sync</string>
        <string>--config</string>
        <string>{config_path}</string>
        <string>menubar</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{SCRIPT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>"""
    with open(plist_path, "w") as f:
        f.write(plist)
    subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
    subprocess.run(["launchctl", "load", plist_path], check=True)
    return "Menu bar app installed and loaded"


def uninstall_menubar():
    if detect_platform() != "launchd":
        return "Menu bar app is only supported on macOS/launchd"
    plist_path = _get_menubar_plist_path()
    if os.path.exists(plist_path):
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        os.remove(plist_path)
        return "Menu bar app removed"
    return "No menu bar app found"


def _install_systemd(python, config_path, interval):
    unit_dir = os.path.expanduser("~/.config/systemd/user")
    os.makedirs(unit_dir, exist_ok=True)

    service = f"""[Unit]
Description=HackMD-Obsidian Sync

[Service]
Type=oneshot
WorkingDirectory={SCRIPT_DIR}
ExecStart={python} -m hackmd_sync --config {config_path} run
"""

    timer = f"""[Unit]
Description=HackMD-Obsidian Sync Timer

[Timer]
OnBootSec=30
OnUnitActiveSec={interval}s
AccuracySec=10s

[Install]
WantedBy=timers.target
"""

    with open(os.path.join(unit_dir, f"{LABEL}.service"), "w") as f:
        f.write(service)
    with open(os.path.join(unit_dir, f"{LABEL}.timer"), "w") as f:
        f.write(timer)

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", f"{LABEL}.timer"], check=True
    )
    return f"systemd timer installed: every {interval}s"


def _uninstall_systemd():
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", f"{LABEL}.timer"],
        capture_output=True,
    )
    unit_dir = os.path.expanduser("~/.config/systemd/user")
    for f in (f"{LABEL}.service", f"{LABEL}.timer"):
        path = os.path.join(unit_dir, f)
        if os.path.exists(path):
            os.remove(path)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return "systemd service removed"


def _install_cron(python, config_path, interval):
    minutes = max(1, interval // 60)
    cmd = f"*/{minutes} * * * * cd {SCRIPT_DIR} && {python} -m hackmd_sync --config {config_path} run >> ~/.config/hackmd-sync/sync.log 2>&1"

    # Get existing crontab
    try:
        existing = subprocess.check_output(["crontab", "-l"], text=True)
    except subprocess.CalledProcessError:
        existing = ""

    # Remove old entry if exists
    lines = [l for l in existing.strip().split("\n") if "hackmd_sync" not in l and l]
    lines.append(cmd)

    proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
    proc.communicate("\n".join(lines) + "\n")
    return f"cron job installed: every {minutes} minutes"


def _uninstall_cron():
    try:
        existing = subprocess.check_output(["crontab", "-l"], text=True)
    except subprocess.CalledProcessError:
        return "No cron job found"

    lines = [l for l in existing.strip().split("\n") if "hackmd_sync" not in l and l]

    proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
    proc.communicate("\n".join(lines) + "\n")
    return "cron job removed"
