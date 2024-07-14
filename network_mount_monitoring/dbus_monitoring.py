"""
Module for monitoring NetworkManager D-Bus signals.

This module contains the DbusMonitoring class which listens to NetworkManager
D-Bus signals for network device state changes and global network state changes.

"""

import asyncio
import logging
from typing import Awaitable, Any, Callable

from dbus_next.aio import MessageBus
from dbus_next.message_bus import Message
from dbus_next.constants import MessageType
from dbus_next.aio.proxy_object import ProxyInterface
from sdbus_async.networkmanager.enums import DeviceState, NetworkManagerState

logger = logging.getLogger(__name__)


class DbusMonitoring:
    """
    Monitors NetworkManager signals via D-Bus for device and global state changes.
    """

    DEVICE_ONLINE_STATE = [
        DeviceState.ACTIVATED,
        DeviceState.IP_CHECK,
        DeviceState.SECONDARIES,
    ]

    GLOBAL_ONLINE_STATE = [
        NetworkManagerState.CONNECTED_LOCAL,
        NetworkManagerState.CONNECTED_SITE,
        NetworkManagerState.GLOBAL,
    ]

    def __init__(
        self,
        bus: MessageBus,
        stop_handler: Callable[[], Awaitable[Any]],
        restart_handler: Callable[[], Awaitable[Any]],
    ):
        """
        Initialize D-Bus monitoring instance.

        Args:
            bus: The D-Bus message bus.
            stop_handler: A callable to stop all mounts upon network failure.
            restart_handler: A callable to restart mounts upon network recovery.
        """
        self.device_list = {}
        self.current_global_state = None
        self.networkmanager_global_state_interface: ProxyInterface
        self.bus = bus
        self.running = True
        self.stop_handler = stop_handler
        self.restart_handler = restart_handler

    async def start(self):
        """
        Start listening for NetworkManager signals and handle state changes.
        """
        self.networkmanager_global_state_interface = (
            await self.get_dbus_networkmanager_interface(self.bus)
        )
        self.networkmanager_global_state_interface.on_state_changed(
            self.global_state_changed
        )
        await self.listen_dbus_networkmanager_device(self.bus)
        self.bus.add_message_handler(self.device_state_changed)

        logger.info("Listening for NetworkManager signals...")
        while self.running:
            await asyncio.sleep(1)

    def stop(self):
        """
        Cleanly stop D-Bus monitoring.
        """
        logger.info("Cleaning up dbus monitoring")
        self.running = False
        if self.bus.connected:
            self.bus.disconnect()

    async def get_dbus_networkmanager_interface(
        self, bus: MessageBus
    ) -> ProxyInterface:
        """
        Get the D-Bus interface for NetworkManager.

        Args:
            bus: The D-Bus message bus.

        Returns:
            ProxyInterface: The D-Bus proxy interface for NetworkManager.
        """
        introspection = await bus.introspect(
            "org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager"
        )
        obj = bus.get_proxy_object(
            "org.freedesktop.NetworkManager",
            "/org/freedesktop/NetworkManager",
            introspection,
        )
        return obj.get_interface("org.freedesktop.NetworkManager")

    async def listen_dbus_networkmanager_device(self, bus: MessageBus) -> None:
        """
        Listen for NetworkManager device state change signals.

        Args:
            bus: The D-Bus message bus.
        """
        reply = await bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[
                    (
                        "type='signal', "
                        "interface='org.freedesktop.NetworkManager.Device', "
                        "member='StateChanged'"
                    )
                ],
            )
        )
        assert reply.message_type == MessageType.METHOD_RETURN

    def get_device_id(self, message: Message):
        """
        Extract the device ID from a D-Bus message path.

        Args:
            message: The D-Bus message containing the device path.

        Returns:
            str: The device ID extracted from the message path.
        """
        return message.path.split("/")[-1]

    def device_state_changed(self, message: Message) -> False:
        """
        Handle device state changes received via D-Bus signals.

        Args:
            message: The D-Bus message containing the device state change.

        Returns:
            bool: False to indicate the handler did not process the message.
        """
        if (
            message.message_type is MessageType.SIGNAL
            and message.interface == "org.freedesktop.NetworkManager.Device"
        ):
            device_id = self.get_device_id(message)
            device_state = message.body[0] in self.DEVICE_ONLINE_STATE
            if (
                device_id not in self.device_list
                or self.device_list[device_id] != device_state
            ):
                self.device_list[device_id] = device_state
                if device_state:
                    asyncio.get_running_loop().create_task(self.restart_handler())

                logger.debug("Device %s is now %s", device_id, device_state)
        return False

    async def global_state_changed(self, state: int):
        """
        Handle global state changes received via NetworkManager signals.

        Args:
            state: The new global state received.

        Notes:
            If the global state indicates a network failure, stops all mounts.
        """
        network_state = NetworkManagerState(state)
        if self.current_global_state != (network_state in self.GLOBAL_ONLINE_STATE):
            self.current_global_state = network_state in self.GLOBAL_ONLINE_STATE
            logger.debug("Global network state is now %s", self.current_global_state)
            if not self.current_global_state:
                logger.info("Stopping all mounts")
                await self.stop_handler()
