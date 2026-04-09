"""macOS status bar app for HackMD sync control."""

import os
import sys
import subprocess

from AppKit import (
    NSObject,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSMenu,
    NSMenuItem,
)
from Foundation import NSTimer

from .scheduler import get_service_status


class HackMDSyncStatusApp(NSObject):
    def initWithConfigPath_(self, config_path):
        self = super().init()
        if self is None:
            return None
        self.config_path = config_path
        self.python = sys.executable
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.menu = NSMenu.alloc().init()
        self.status_line = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Status: loading...", None, "")
        self.status_line.setEnabled_(False)
        self.menu.addItem_(self.status_line)
        self.menu.addItem_(NSMenuItem.separatorItem())

        self.start_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Start Sync Service", "startService:", "")
        self.start_item.setTarget_(self)
        self.menu.addItem_(self.start_item)

        self.stop_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Stop Sync Service", "stopService:", "")
        self.stop_item.setTarget_(self)
        self.menu.addItem_(self.stop_item)

        self.run_now_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Run Sync Now", "runNow:", "")
        self.run_now_item.setTarget_(self)
        self.menu.addItem_(self.run_now_item)

        self.refresh_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Refresh Status", "refreshStatus:", "")
        self.refresh_item.setTarget_(self)
        self.menu.addItem_(self.refresh_item)

        self.menu.addItem_(NSMenuItem.separatorItem())
        self.quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit Menu Bar", "quitApp:", "")
        self.quit_item.setTarget_(self)
        self.menu.addItem_(self.quit_item)

        self.status_item.setMenu_(self.menu)
        self.refreshStatus_(None)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            10.0, self, "refreshStatus:", None, True
        )
        return self

    def _command(self, *args):
        cmd = [self.python, "-m", "hackmd_sync"]
        if self.config_path:
            cmd.extend(["--config", self.config_path])
        cmd.extend(args)
        return cmd

    def refreshStatus_(self, _sender):
        try:
            status = get_service_status()
            running = status.get("running", False)
            self.status_item.button().setTitle_("H✓" if running else "H⏸")
            self.status_line.setTitle_(f"Status: {'Running' if running else 'Stopped'}")
        except Exception as exc:
            self.status_item.button().setTitle_("H!")
            self.status_line.setTitle_(f"Status: error ({exc})")

    def startService_(self, _sender):
        subprocess.run(self._command("start"), check=False)
        self.refreshStatus_(None)

    def stopService_(self, _sender):
        subprocess.run(self._command("stop"), check=False)
        self.refreshStatus_(None)

    def runNow_(self, _sender):
        subprocess.Popen(self._command("run"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.status_line.setTitle_("Status: sync triggered")

    def quitApp_(self, _sender):
        NSApplication.sharedApplication().terminate_(None)


def launch_menubar_app(config_path=None):
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    delegate = HackMDSyncStatusApp.alloc().initWithConfigPath_(config_path)
    app.setDelegate_(delegate)
    app.run()
