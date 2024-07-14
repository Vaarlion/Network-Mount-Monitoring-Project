"""
This script monitor the network and system journal with the goal
of avoiding system hanging due to network mount.
Made by Guillaume De KOKER in 2024
"""

import asyncio
import string
from typing import Awaitable, Any, Callable

from dbus_next.aio import MessageBus
from dbus_next.message_bus import Message
from dbus_next.constants import MessageType, BusType
from dbus_next.aio.proxy_object import ProxyInterface
from sdbus_async.networkmanager.enums import (
    DeviceState,
    NetworkManagerState,
)
from systemd import journal


NETWORK_MOUNT_NAME = ["home-vaarlion-Nas", "home-vaarlion-Media"]


###################
###################


class DbusMonitoring:
    """
    Monitor the network manager dbus api for network stage change
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
        self.device_list = {}
        self.current_global_state = None
        self.networkmanager_global_state_interface: ProxyInterface
        self.bus = bus
        self.running = True
        self.stop_handler = stop_handler
        self.restart_handler = restart_handler

    async def start(self):
        """
        Start listening for NetworkManager signals
        """

        # Listen for NetworkManager global state change and add the handler
        self.networkmanager_global_state_interface = (
            await self.get_dbus_networkmanager_interface(self.bus)
        )
        self.networkmanager_global_state_interface.on_state_changed(
            self.global_state_changed
        )

        # Listen for all NetworkManager Device state change and add the handler
        await self.listen_dbus_networkmanager_device(self.bus)
        self.bus.add_message_handler(self.device_state_changed)

        print("Listening for NetworkManager signals...")

        while self.running:
            await asyncio.sleep(1)

    def stop(self):
        """
        Cleanly stop of the script
        """
        print("Cleaning up dbus monitoring")
        self.running = False
        if self.bus.connected:
            self.bus.disconnect()

    async def get_dbus_networkmanager_interface(
        self, bus: MessageBus
    ) -> ProxyInterface:
        """
        Return the interface of the network manager state
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
        Ask dbus to send us all network device state change signal
        """
        # Listen for any NetworkManager device state change
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
        Return the network device id from the message path string.
        """
        return message.path.split("/")[-1]

    def device_state_changed(self, message: Message) -> False:
        """
        Handle device state change from Networkmanager dbus message
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
                # Device changed state
                self.device_list[device_id] = device_state
                if device_state:
                    # New network, let's retry the mount
                    asyncio.get_running_loop().create_task(self.restart_handler())

                print(f"Device {device_id} is now {device_state}")
        return False

    async def global_state_changed(self, state: int):
        """
        Handle global state change from Networkmanager dbus interface
        """
        network_state = NetworkManagerState(state)

        if self.current_global_state != (network_state in self.GLOBAL_ONLINE_STATE):
            self.current_global_state = network_state in self.GLOBAL_ONLINE_STATE
            print(f"Global network state is now {self.current_global_state}")
            if not self.current_global_state:
                print("Stopping all mounts")
                await self.stop_handler()


class JournalctlMonitoring:
    """
    Monitor the system journal for kernel network mount error
    """

    def __init__(
        self,
        stop_handler: Callable[[], Awaitable[Any]],
    ):
        """
        Setup journalctl listener
        """
        self.stop_handler = stop_handler
        self.journal = journal.Reader()
        self.loop = asyncio.get_running_loop()
        self.journal.log_level(journal.LOG_WARNING)  # Adjust log level if needed
        self.journal.add_match(SYSLOG_IDENTIFIER="kernel")  # Only match kernel log
        self.journal.this_boot()  # Only show logs from this boot
        self.running = True

    async def start(self):
        """
        Start journalctl listening loop
        """

        # Move to the end of the journal so we only get new messages
        self.journal.seek_tail()
        self.journal.get_previous()

        print("Listening for kernel log...")
        while self.running:
            # Wait for new messages
            await self.loop.run_in_executor(None, self.journal.wait, 1)

            # Process new messages
            for entry in self.journal:
                if (
                    entry["MESSAGE"].startswith("CIFS: VFS:")
                    and "has not responded" in entry["MESSAGE"]
                ):
                    print(f"{entry['__REALTIME_TIMESTAMP']}: {entry['MESSAGE']}")
                    print(
                        "Kernel has detected Frozen network mount, stopping all of them now."
                    )
                    await self.stop_handler()

            # Sleep for a bit to avoid busy waiting
            await asyncio.sleep(0.5)

    def stop(self):
        """
        Cleanly stop journalctl listener
        """
        print("Cleaning up Journalctl monitoring")
        self.running = False
        self.journal.close()


###################
###################


class MountControl:
    """
    Group of function used to manipulate mount and automount on the system
    """

    def __init__(self, bus: MessageBus, list_of_mount: list):
        """
        Setup the mount control
        """
        self.bus = bus
        self.systemd_manager_interface: ProxyInterface
        self.list_of_mount = list_of_mount
        asyncio.get_running_loop().create_task(self.__async_init__())

    async def __async_init__(self):
        self.systemd_manager_interface = await self.get_dbus_systemd_interface(self.bus)

    async def get_dbus_systemd_interface(self, bus: MessageBus) -> ProxyInterface:
        """
        Return the interface of the systemd manager dbus api
        """
        introspection = await bus.introspect(
            "org.freedesktop.systemd1", "/org/freedesktop/systemd1"
        )
        obj = bus.get_proxy_object(
            "org.freedesktop.systemd1",
            "/org/freedesktop/systemd1",
            introspection,
        )
        return obj.get_interface("org.freedesktop.systemd1.Manager")

    async def get_unit_status(self, unit_name: str) -> str:
        """
        Return the active state and sub state of the provided unit file.
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

    async def reset_failed(self, unit_name: string):
        """
        Reset failed state of a unit.
        """
        await self.systemd_manager_interface.call_reset_failed_unit(unit_name)

    async def stop_unit(self, unit_name: string):
        """
        Stop a unit.
        """
        await self.systemd_manager_interface.call_stop_unit(unit_name, "replace")

    async def start_unit(self, unit_name: string):
        """
        Start a unit.
        """
        await self.systemd_manager_interface.call_start_unit(unit_name, "replace")

    async def restart_all_mount(self):
        """
        run the restart_mount() for every mount in list_of_mount if they are stopped/failed
        """
        automount_to_restart = []

        for name in self.list_of_mount:
            # Reset all failed mount
            active_state, _ = await self.get_unit_status(f"{name}.mount")
            if active_state == "failed":
                print(f"{name}.mount is failed, resetting")
                await self.reset_failed(f"{name}.mount")
            # Build a list of all failed automount
            active_state, _ = await self.get_unit_status(f"{name}.automount")
            if active_state != "active":
                print(
                    (
                        f"{name}.automount is not active ({active_state}), "
                        "running the restart mount service"
                    )
                )
                automount_to_restart.append(name)

        if len(automount_to_restart) >= 1:
            # We need to restart some automount
            await self.stop_unit("network-online.target")
            await self.stop_unit("NetworkManager-wait-online.service")
            # Reset failed all automount and start them back up
            for name in automount_to_restart:
                await self.reset_failed(f"{name}.automount")
                await self.start_unit(f"{name}.automount")

    async def stop_mounts(self):
        """
        Stop all network mount to avoid timeout
        """
        for name in self.list_of_mount:
            await self.stop_unit(f"{name}.mount")


###################
###################


async def main():
    """
    Init and run the main program loop
    """

    # Initialise Dbus object
    dbus_system_bus = await MessageBus(bus_type=BusType.SYSTEM).connect()

    # Create a mount controller using systemd dbus
    mount_controller = MountControl(dbus_system_bus, NETWORK_MOUNT_NAME)

    # Initialise a dbus monitoring of NetworkManager device state
    dbus_monitoring = DbusMonitoring(
        dbus_system_bus,
        mount_controller.stop_mounts,
        mount_controller.restart_all_mount,
    )

    # Initialise a systemd journal monitoring of Kernel message about CIFS timeout
    journal_monitoring = JournalctlMonitoring(mount_controller.stop_mounts)

    try:
        journal_monitoring_task = asyncio.create_task(journal_monitoring.start())
        dbus_monitoring_task = asyncio.create_task(dbus_monitoring.start())
        await asyncio.gather(journal_monitoring_task, dbus_monitoring_task)

    except (KeyboardInterrupt, asyncio.CancelledError):
        dbus_monitoring.stop()
        journal_monitoring.stop()


if __name__ == "__main__":
    asyncio.run(main())
