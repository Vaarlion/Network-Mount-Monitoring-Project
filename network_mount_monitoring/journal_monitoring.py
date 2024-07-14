"""
Module for monitoring systemd journal for network mount errors.

This module contains the JournalctlMonitoring class which listens to systemd
journal for kernel log messages related to network mount errors.

"""

import asyncio
import logging
from typing import Awaitable, Callable, Any

from systemd import journal

logger = logging.getLogger(__name__)


class JournalctlMonitoring:
    """
    Monitors systemd journal for kernel messages related to network mounts.
    """

    def __init__(self, stop_handler: Callable[[], Awaitable[Any]]):
        """
        Initialize systemd journal monitoring instance.

        Args:
            stop_handler: A callable to stop all mounts upon detecting network issues.
        """
        self.stop_handler = stop_handler
        self.journal = journal.Reader()
        self.loop = asyncio.get_running_loop()
        self.journal.log_level(journal.LOG_WARNING)
        self.journal.add_match(SYSLOG_IDENTIFIER="kernel")
        self.journal.this_boot()
        self.running = True

    async def start(self):
        """
        Start monitoring systemd journal for kernel messages.
        """
        self.journal.seek_tail()
        self.journal.get_previous()
        logger.info("Listening for kernel log...")

        while self.running:
            await self.loop.run_in_executor(None, self.journal.wait, 1)
            for entry in self.journal:
                if (
                    entry["MESSAGE"].startswith("CIFS: VFS:")
                    and "has not responded" in entry["MESSAGE"]
                ):
                    logger.debug(
                        "%s: %s", entry["__REALTIME_TIMESTAMP"], entry["MESSAGE"]
                    )
                    logger.info(
                        "Kernel has detected Frozen network mount, stopping all of them now."
                    )
                    await self.stop_handler()
            await asyncio.sleep(0.5)

    def stop(self):
        """
        Cleanly stop systemd journal monitoring.
        """
        logger.info("Cleaning up Journalctl monitoring")
        self.running = False
        self.journal.close()
