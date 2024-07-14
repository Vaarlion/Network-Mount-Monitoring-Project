"""
Module for managing network mount monitoring using D-Bus and systemd
with the goal of avoiding system hanging due to network mount.

Made by Guillaume De KOKER in 2024

This module includes classes and functions to monitor and control network mounts
using D-Bus interfaces provided by NetworkManager and systemd.

Classes:
- DbusMonitoring: Monitors NetworkManager D-Bus signals for network device and
  global state changes.
- JournalctlMonitoring: Monitors systemd journal for kernel log messages related
  to network mount errors.
- MountControl: Controls systemd units (mounts and automounts) via D-Bus.

"""

from .dbus_monitoring import DbusMonitoring
from .journal_monitoring import JournalctlMonitoring
from .mount_control import MountControl
