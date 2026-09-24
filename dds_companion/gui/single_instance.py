from __future__ import annotations

import hashlib
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def default_server_name() -> str:
    """Return a stable per-Windows-user IPC name for DDS Companion."""
    identity = "\\".join(
        part for part in (
            os.environ.get("USERDOMAIN", ""),
            os.environ.get("USERNAME", ""),
        )
        if part
    ) or "default-user"
    digest = hashlib.sha256(identity.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"DDS-DiscordDataSnatcher-{digest}"


class SingleInstanceCoordinator(QObject):
    """Own the GUI single-instance boundary and notify the primary instance."""

    activation_requested = Signal()

    def __init__(self, server_name: str | None = None, *, connect_timeout_ms: int = 500):
        super().__init__()
        self.server_name = server_name or default_server_name()
        self.connect_timeout_ms = max(50, int(connect_timeout_ms))
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept_secondary)

    def claim_or_notify(self) -> bool:
        """Return True for the primary instance, False after notifying an existing one."""
        if self._notify_existing(self.connect_timeout_ms):
            return False

        if self._server.listen(self.server_name):
            return True

        # A competing process may have won the startup race after our first probe.
        if self._notify_existing(max(1000, self.connect_timeout_ms)):
            return False

        # Unix-like platforms can leave a stale socket pathname after a crash.
        # Windows QLocalServer uses named pipes, so there is nothing stale to unlink.
        if os.name != "nt":
            QLocalServer.removeServer(self.server_name)
            if self._server.listen(self.server_name):
                return True

        raise RuntimeError(
            "DDS could not establish the single-instance guard: "
            + self._server.errorString()
        )

    def _notify_existing(self, timeout_ms: int) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        connected = socket.waitForConnected(timeout_ms)
        if connected:
            # The connection itself is the activation request. No payload is needed.
            socket.disconnectFromServer()
        return connected

    def _accept_secondary(self) -> None:
        activated = False
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                break
            activated = True
            socket.disconnectFromServer()
            socket.deleteLater()
        if activated:
            self.activation_requested.emit()

    def close(self) -> None:
        self._server.close()
