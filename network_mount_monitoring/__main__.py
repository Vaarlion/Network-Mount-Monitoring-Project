"""
Main module to run network mount monitoring.

This module initializes the D-Bus connections and starts monitoring processes
for network mounts using DbusMonitoring and JournalctlMonitoring classes.

"""

import asyncio
import logging

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

from network_mount_monitoring.config import NETWORK_MOUNT_NAMES
from network_mount_monitoring import DbusMonitoring, JournalctlMonitoring, MountControl

logging.basicConfig(level=logging.INFO)


async def main():
    """
    Main entry point of the program.

    This function sets up the necessary components for monitoring network mounts
    and handles any interruptions or cancellations gracefully.
    """
    # Connect to the D-Bus system bus
    dbus_system_bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    # Initialize the MountControl to manage network mounts
    mount_controller = MountControl(dbus_system_bus, NETWORK_MOUNT_NAMES)

    # Initialize D-Bus monitoring for NetworkManager device and global state changes
    dbus_monitoring = DbusMonitoring(
        dbus_system_bus,
        mount_controller.stop_mounts,
        mount_controller.restart_all_mounts,
    )

    # Initialize systemd journal monitoring for kernel messages related to network mounts
    journal_monitoring = JournalctlMonitoring(mount_controller.stop_mounts)

    try:
        # Start the systemd journal monitoring and D-Bus monitoring concurrently
        journal_monitoring_task = asyncio.create_task(journal_monitoring.start())
        dbus_monitoring_task = asyncio.create_task(dbus_monitoring.start())
        await asyncio.gather(journal_monitoring_task, dbus_monitoring_task)
    except (KeyboardInterrupt, asyncio.CancelledError):
        # Handle keyboard interrupts or task cancellations by stopping D-Bus and journal monitoring
        dbus_monitoring.stop()
        journal_monitoring.stop()


if __name__ == "__main__":
    asyncio.run(main())
