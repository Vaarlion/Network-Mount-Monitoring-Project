"""
Module for controlling systemd units (mounts and automounts) via D-Bus.

This module contains the MountControl class which manages systemd units
(mounts and automounts) using D-Bus interfaces provided by systemd.

"""

import asyncio
import logging
from typing import List

from dbus_next.aio import MessageBus
from dbus_next.aio.proxy_object import ProxyInterface

logger = logging.getLogger(__name__)


class MountControl:
    """
    Controls systemd units (mounts and automounts) via D-Bus.
    """

    def __init__(self, bus: MessageBus, list_of_mount: List[str]):
        """
        Initialize MountControl instance.

        Args:
            bus: D-Bus message bus instance.
            list_of_mount: List of mount and automount names to manage.
        """
        self.bus = bus
        self.systemd_manager_interface: ProxyInterface
        self.list_of_mount = list_of_mount
        asyncio.get_running_loop().create_task(self.__async_init__())

    async def __async_init__(self):
        """
        Asynchronously initialize systemd manager interface.
        """
        self.systemd_manager_interface = await self.get_dbus_systemd_interface(self.bus)

    async def get_dbus_systemd_interface(self, bus: MessageBus) -> ProxyInterface:
        """
        Get the D-Bus interface for systemd manager.

        Args:
            bus: D-Bus message bus instance.

        Returns:
            ProxyInterface: D-Bus proxy interface for systemd manager.
        """
        introspection = await bus.introspect(
            "org.freedesktop.systemd1", "/org/freedesktop/systemd1"
        )
        obj = bus.get_proxy_object(
            "org.freedesktop.systemd1", "/org/freedesktop/systemd1", introspection
        )
        return obj.get_interface("org.freedesktop.systemd1.Manager")

    async def get_unit_status(self, unit_name: str) -> tuple:
        """
        Get the active and sub state of a systemd unit.

        Args:
            unit_name: Name of the systemd unit.

        Returns:
            tuple: Tuple containing the active state and sub state.
        """
        unit_path = await self.systemd_manager_interface.call_get_unit(unit_name)
        introspection = await self.bus.introspect("org.freedesktop.systemd1", unit_path)
        unit_obj = self.bus.get_proxy_object(
            "org.freedesktop.systemd1", unit_path, introspection
        )
        unit_interface = unit_obj.get_interface("org.freedesktop.DBus.Properties")

        active_state = await unit_interface.call_get(
            "org.freedesktop.systemd1.Unit", "ActiveState"
        )
        sub_state = await unit_interface.call_get(
            "org.freedesktop.systemd1.Unit", "SubState"
        )

        return active_state.value, sub_state.value

    async def reset_failed(self, unit_name: str):
        """
        Reset the failed state of a systemd unit.

        Args:
            unit_name: Name of the systemd unit to reset.
        """
        await self.systemd_manager_interface.call_reset_failed_unit(unit_name)

    async def stop_unit(self, unit_name: str):
        """
        Stop a systemd unit.

        Args:
            unit_name: Name of the systemd unit to stop.
        """
        await self.systemd_manager_interface.call_stop_unit(unit_name, "replace")

    async def start_unit(self, unit_name: str):
        """
        Start a systemd unit.

        Args:
            unit_name: Name of the systemd unit to start.
        """
        await self.systemd_manager_interface.call_start_unit(unit_name, "replace")

    async def restart_all_mounts(self):
        """
        Restart all mounts and automounts managed by MountControl.
        """
        automount_to_restart = []

        for name in self.list_of_mount:
            active_state, _ = await self.get_unit_status(f"{name}.mount")
            if active_state == "failed":
                logger.info("%s.mount is failed, resetting", name)
                await self.reset_failed(f"{name}.mount")

            active_state, _ = await self.get_unit_status(f"{name}.automount")
            if active_state != "active":
                logger.info(
                    "%s.automount is not active (%s), restarting", name, active_state
                )
                automount_to_restart.append(name)

        if automount_to_restart:
            await self.stop_unit("network-online.target")
            await self.stop_unit("NetworkManager-wait-online.service")
            for name in automount_to_restart:
                await self.reset_failed(f"{name}.automount")
                await self.start_unit(f"{name}.automount")

    async def stop_mounts(self):
        """
        Stop all mounts and automounts managed by MountControl.
        """
        for name in self.list_of_mount:
            await self.stop_unit(f"{name}.mount")
