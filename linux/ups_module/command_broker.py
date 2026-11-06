"""Bounded local command transport; USB execution stays in the bridge main loop."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import queue
import select
import socket
import socketserver
import stat
import threading
import time

COMMAND_METHODS = {
    "test.battery.start": "test_battery_quick",
    "test.battery.start.quick": "test_battery_quick",
    "test.battery.start.deep": "test_battery_deep",
    "test.battery.stop": "test_battery_stop",
}
COMMAND_SOCKET = "/run/enerex-ups/commands.sock"


@dataclass
class _Request:
    command: str
    deadline: float
    done: threading.Event = field(default_factory=threading.Event)
    cancelled: bool = False
    started: bool = False
    result: dict = field(default_factory=dict)
    peer: socket.socket | None = None


def _error(message):
    return {"ok": False, "message": message}


def submit_command(path, command, timeout=35):
    """Submit once; transport loss means unknown outcome, never an automatic retry."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout + .5)
            client.connect(str(path))
            client.sendall(json.dumps({"command": command, "timeout": timeout}).encode()+b"\n")
            with client.makefile("rb") as stream:
                raw = stream.readline(4097)
            if len(raw) > 4096 or not raw.endswith(b"\n"):
                return _error("Invalid bridge response; outcome unknown")
            result = json.loads(raw)
            if not isinstance(result, dict) or type(result.get("ok")) is not bool:
                return _error("Invalid bridge response; outcome unknown")
            return result
    except (OSError, ValueError) as exc:
        return _error(f"Bridge transport failed; outcome unknown: {exc}")


class CommandBroker:
    def __init__(self, path=COMMAND_SOCKET, max_pending=16, owner_group="nut"):
        self.path = Path(path)
        self.owner_group = owner_group
        self.pending = queue.Queue(max_pending)
        self._lock = threading.RLock()
        self._slots = threading.BoundedSemaphore(max_pending)
        self.connected = False
        self.server = None
        self.thread = None
        self._inode = None
        self._lock_file = None

    @property
    def pending_count(self):
        return self.pending.qsize()

    def start(self):
        import fcntl
        self.path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
        if self.owner_group:
            import grp
            os.chown(self.path.parent, 0, grp.getgrnam(self.owner_group).gr_gid)
            os.chmod(self.path.parent, 0o750)
        self._lock_file = open(str(self.path)+".lock", "a")
        fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if self.path.exists():
            if not stat.S_ISSOCK(self.path.lstat().st_mode):
                raise RuntimeError("Refusing to replace a non-socket command path")
            self.path.unlink()
        broker = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(1)
                request = None
                try:
                    raw = self.rfile.readline(4097)
                    if len(raw) > 4096 or not raw.endswith(b"\n"):
                        result = _error("Request too large or incomplete")
                    else:
                        value = json.loads(raw)
                        result, request = broker._enqueue(value, self.connection)
                        if request is not None:
                            while not request.done.wait(.05):
                                with broker._lock:
                                    readable, _, _ = select.select([self.connection], [], [], 0)
                                    gone = readable and not self.connection.recv(1, socket.MSG_PEEK)
                                    if time.monotonic() >= request.deadline or gone:
                                        request.cancelled = True
                                        result = _error("Request expired; outcome unknown" if request.started else "Request expired before execution")
                                        break
                            else:
                                result = request.result
                    self.wfile.write(json.dumps(result).encode()+b"\n")
                except (OSError, ValueError, TypeError):
                    try:
                        self.wfile.write(json.dumps(_error("Invalid command request")).encode()+b"\n")
                    except OSError:
                        pass
                finally:
                    if request is not None:
                        with broker._lock:
                            request.cancelled = True

        class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
            daemon_threads = True
            def process_request(self, request, address):
                if not broker._slots.acquire(blocking=False):
                    request.close()
                    return
                super().process_request(request, address)

            def process_request_thread(self, request, address):
                try:
                    super().process_request_thread(request, address)
                finally:
                    broker._slots.release()

        self.server = Server(str(self.path), Handler)
        os.chmod(self.path, 0o660)
        if self.owner_group:
            os.chown(self.path, 0, grp.getgrnam(self.owner_group).gr_gid)
        self._inode = self.path.stat().st_ino
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(.05), daemon=True)
        self.thread.start()

    def _enqueue(self, value, peer):
        with self._lock:
            if not isinstance(value, dict) or set(value) - {"command", "timeout"}:
                return _error("Invalid request fields"), None
            command, timeout = value.get("command"), value.get("timeout", 35)
            if not isinstance(command, str) or command not in COMMAND_METHODS:
                return _error("Unsupported command"), None
            if type(timeout) not in (int, float) or not 0 < timeout <= 35:
                return _error("Invalid command deadline"), None
            if not self.connected:
                return _error("UPS disconnected or command capability unavailable"), None
            request = _Request(command, time.monotonic()+timeout)
            request.peer = peer
            try:
                self.pending.put_nowait(request)
            except queue.Full:
                return _error("Command queue full"), None
            return None, request

    def set_connected(self, connected):
        with self._lock:
            self.connected = connected
            if not connected:
                while not self.pending.empty():
                    request = self.pending.get_nowait()
                    request.cancelled = True
                    request.result = _error("UPS connection ended before execution")
                    request.done.set()

    def execute_pending(self, executor):
        for _ in range(self.pending.maxsize):
            with self._lock:
                try:
                    request = self.pending.get_nowait()
                except queue.Empty:
                    break
                peer_gone = False
                if not request.cancelled:
                    try:
                        # After its one frame, readable means EOF or invalid extra input.
                        peer_gone = bool(select.select([request.peer], [], [], 0)[0])
                    except (OSError, ValueError):
                        peer_gone = True
                if request.cancelled or peer_gone or not self.connected or time.monotonic() >= request.deadline:
                    request.result = _error("Command expired before execution")
                    request.done.set()
                    continue
                request.started = True
            try:
                ok, message = executor(request.command)
                request.result = {"ok": bool(ok), "message": str(message)}
            except Exception as exc:
                request.result = _error(f"Command failed; outcome unknown: {exc}")
            finally:
                request.done.set()

    def close(self):
        self.set_connected(False)
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join(timeout=1)
            self.thread = None
        if self._inode is not None and self.path.exists() and self.path.stat().st_ino == self._inode:
            self.path.unlink()
        if self._lock_file:
            self._lock_file.close()
            self._lock_file = None
