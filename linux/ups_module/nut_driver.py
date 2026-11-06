"""NUT driver socket adapter. Reads telemetry; never opens a USB device."""
from __future__ import annotations

import argparse
import configparser
import logging
import os
from pathlib import Path
import queue
import re
import selectors
import signal
import socket
import stat
import threading
import time

from .command_broker import COMMAND_METHODS, COMMAND_SOCKET, submit_command

LOG = logging.getLogger("enerex-driver")
TOKEN = re.compile(r"[a-zA-Z0-9_.-]+\Z")


def quote(value):
    value = str(value)
    if len(value) > 2048 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid NUT variable value")
    return '"'+value.replace('\\', '\\\\').replace('"', '\\"').replace('#', '\\#')+'"'


def read_snapshot(path, max_age=5):
    with open(path, encoding="utf-8") as stream:
        info = os.fstat(stream.fileno())
        age = time.time()-info.st_mtime
        if not stat.S_ISREG(info.st_mode) or not -1 <= age < max_age or info.st_size > 65536:
            raise ValueError("Telemetry missing or stale")
        text = stream.read(65537)
    if len(text) > 65536:
        raise ValueError("Telemetry too large")
    values = {}
    for line in text.splitlines():
        key, sep, value = line.partition(": ")
        if not sep or not TOKEN.fullmatch(key):
            raise ValueError("Malformed telemetry variable")
        quote(value)
        values[key] = value
    if not values.get("ups.status") or values["ups.status"] == "WAIT":
        raise ValueError("No authoritative UPS status")
    values.update({"driver.name": "enerex", "driver.parameter.mode": "native",
                   "driver.parameter.port": str(path), "driver.version.internal": "1.0"})
    return values


class DriverServer:
    def __init__(self, socket_path, snapshot_path, command_path=COMMAND_SOCKET, *, command_sender=submit_command):
        self.path, self.snapshot = Path(socket_path), Path(snapshot_path)
        self.command_path, self.command_sender = str(command_path), command_sender
        self.selector = selectors.DefaultSelector()
        self.listener = None
        self.clients = {}
        self.values, self.commands = {}, set()
        self.fresh = False
        self._pid_file = None
        self._owns_path = False
        self._inode = None
        self._requests = queue.Queue(16)
        self._stop = threading.Event()
        self._command_thread = None

    def start(self):
        import fcntl
        self.path.parent.mkdir(mode=0o770, parents=True, exist_ok=True)
        pid_path = str(self.path)+".pid"
        fd = os.open(pid_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o640)
        self._pid_file = os.fdopen(fd, "r+")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self._pid_file.close()
            self._pid_file = None
            raise
        self._owns_path = True
        if self.path.exists():
            if not stat.S_ISSOCK(self.path.lstat().st_mode):
                raise RuntimeError("Refusing to replace a non-socket driver path")
            self.path.unlink()
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(str(self.path))
        os.chmod(self.path, 0o660)
        self._inode = self.path.stat().st_ino
        self.listener.listen(8)
        self.listener.setblocking(False)
        self.selector.register(self.listener, selectors.EVENT_READ)
        self._pid_file.seek(0)
        self._pid_file.truncate()
        self._pid_file.write(str(os.getpid())+"\n")
        self._pid_file.flush()
        self.refresh()
        self._command_thread = threading.Thread(target=self._command_loop, daemon=True)
        self._command_thread.start()

    def _command_loop(self):
        while not self._stop.is_set():
            try:
                command, deadline = self._requests.get(timeout=.1)
            except queue.Empty:
                continue
            if self._stop.is_set() or time.monotonic() >= deadline:
                continue
            try:
                # Re-check the snapshot at execution; no queued work survives stale data.
                data = read_snapshot(self.snapshot)
                if data.get("cmd."+command) != "1":
                    continue
                result = self.command_sender(self.command_path, command)
                LOG.info("Command %s transport outcome: %s", command, result)
            except Exception as exc:
                LOG.warning("Command %s failed without retry: %s", command, exc)

    def _drop(self, client):
        self.clients.pop(client, None)
        try:
            self.selector.unregister(client)
        except (KeyError, ValueError):
            pass
        client.close()

    def _send(self, client, text):
        try:
            payload = text.encode("utf-8")
            if len(payload) > 131072:
                raise ValueError("Driver dump too large")
            client.sendall(payload)
        except (OSError, ValueError):
            self._drop(client)

    def _broadcast(self, text):
        if text:
            for client in list(self.clients):
                self._send(client, text)

    def refresh(self):
        try:
            values = read_snapshot(self.snapshot)
            commands = {c for c in COMMAND_METHODS if values.get("cmd."+c) == "1"}
            fresh = True
        except (OSError, ValueError, UnicodeError):
            values, commands, fresh = self.values, set(), False
        updates = []
        if fresh:
            for key in self.values.keys()-values.keys():
                updates.append(f"DELINFO {key}\n")
            for key, value in sorted(values.items()):
                if self.values.get(key) != value:
                    updates.append(f"SETINFO {key} {quote(value)}\n")
        for command in sorted(self.commands-commands):
            updates.append(f"DELCMD {command}\n")
        for command in sorted(commands-self.commands):
            updates.append(f"ADDCMD {command}\n")
        if fresh != self.fresh:
            updates.append("DATAOK\n" if fresh else "DATASTALE\n")
        self.values, self.commands, self.fresh = values, commands, fresh
        self._broadcast(''.join(updates))

    def _line(self, client, raw):
        try:
            parts = raw.decode("ascii").split()
        except UnicodeError:
            self._drop(client)
            return
        if parts == ["DUMPALL"]:
            self.refresh()
            lines = ["DATASTALE\n"] if not self.fresh else []
            lines.extend(f"SETINFO {k} {quote(v)}\n" for k,v in sorted(self.values.items()))
            lines.extend(f"ADDCMD {c}\n" for c in sorted(self.commands))
            if self.fresh:
                lines.append("DATAOK\n")
            lines.append("DUMPDONE\n")
            self._send(client, ''.join(lines))
        elif parts == ["PING"]:
            self._send(client, "PONG\n")
        elif len(parts) == 2 and parts[0] == "INSTCMD":
            self.refresh()
            if self.fresh and parts[1] in self.commands:
                try:
                    self._requests.put_nowait((parts[1], time.monotonic()+5))
                except queue.Full:
                    LOG.warning("Native command queue full; request discarded")
        # SET and unadvertised hardware commands have no handler.

    def step(self, timeout=.2):
        self.refresh()
        for key, _ in self.selector.select(timeout):
            if key.fileobj is self.listener:
                client, _ = self.listener.accept()
                if len(self.clients) >= 8:
                    client.close()
                    continue
                client.setblocking(False)
                self.clients[client] = b""
                self.selector.register(client, selectors.EVENT_READ)
                continue
            client = key.fileobj
            try:
                data = client.recv(8193)
            except BlockingIOError:
                continue
            except OSError:
                data = b""
            if not data or len(data)+len(self.clients.get(client,b"")) > 8192:
                self._drop(client)
                continue
            self.clients[client] += data
            while client in self.clients and b"\n" in self.clients[client]:
                line, self.clients[client] = self.clients[client].split(b"\n",1)
                self._line(client, line)

    def close(self):
        self._stop.set()
        for client in list(self.clients):
            self._drop(client)
        if self.listener:
            self.selector.unregister(self.listener)
            self.listener.close()
            self.listener = None
        self.selector.close()
        if self._command_thread:
            self._command_thread.join(timeout=.2)
        if self._owns_path:
            if self._inode is not None and self.path.exists() and self.path.stat().st_ino == self._inode:
                self.path.unlink()
            pid_path = Path(str(self.path)+".pid")
            if self._pid_file and pid_path.exists() and pid_path.stat().st_ino == os.fstat(self._pid_file.fileno()).st_ino:
                pid_path.unlink()
            if self._pid_file:
                self._pid_file.close()
                self._pid_file = None
            self._owns_path = False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-a', dest='ups', required=True)
    parser.add_argument('-F', dest='foreground', action='store_true')
    parser.add_argument('-D', dest='debug', action='count', default=0)
    parser.add_argument('-u', dest='user', default='nut')
    parser.add_argument('-k', dest='killpower', action='store_true')
    parser.add_argument('--state-dir', default=os.environ.get('NUT_STATEPATH', '/run/nut'))
    parser.add_argument('--snapshot')
    parser.add_argument('--command-socket', default=COMMAND_SOCKET)
    args = parser.parse_args(argv)
    if args.killpower:
        parser.error('Hardware shutdown is unsupported; no command was sent')
    if not TOKEN.fullmatch(args.ups) or len(args.ups)>64:
        parser.error('Invalid UPS name')
    if args.snapshot:
        snapshot = args.snapshot
    else:
        conf = Path(os.environ.get('NUT_CONFPATH', '/etc/nut'))/'ups.conf'
        config = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=('#',))
        config.read_string('[GLOBAL]\n'+conf.read_text())
        if config.get(args.ups, 'driver') != 'enerex':
            parser.error('Selected UPS does not use enerex')
        snapshot = config.get(args.ups, 'port')
    import pwd
    user = pwd.getpwnam(args.user)
    runtime = Path(args.state_dir)
    new_runtime = not runtime.exists()
    runtime.mkdir(mode=0o770, parents=True, exist_ok=True)
    if os.geteuid() == 0:
        if new_runtime:
            os.chown(runtime, user.pw_uid, user.pw_gid)
        os.initgroups(user.pw_name, user.pw_gid)
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    if not args.foreground and not args.debug and Path('/dev/log').exists():
        from logging.handlers import SysLogHandler
        logging.basicConfig(level=logging.INFO, handlers=[SysLogHandler(address='/dev/log')],
                            format='enerex-driver: %(message)s')
    else:
        logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    ready_writer = None
    if not args.foreground and not args.debug:
        reader, writer = os.pipe()
        child = os.fork()
        if child:
            os.close(writer)
            import select
            available, _, _ = select.select([reader], [], [], 5)
            message = os.read(reader, 4096) if available else b''
            os.close(reader)
            if message == b'OK\n':
                return 0
            print('Driver startup failed: '+message.decode(errors='replace'))
            return 1
        os.close(reader)
        os.setsid()
        ready_writer = writer
    server = DriverServer(runtime/('enerex-'+args.ups), snapshot, args.command_socket)
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    try:
        server.start()
        if ready_writer is not None:
            null = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(null, fd)
            if null>2:
                os.close(null)
            os.write(ready_writer, b'OK\n')
            os.close(ready_writer)
            ready_writer = None
        while not stopped.is_set():
            server.step()
        return 0
    except Exception as exc:
        if ready_writer is not None:
            os.write(ready_writer, ('ERROR '+str(exc)).encode())
            os.close(ready_writer)
        else:
            LOG.exception('Adapter failed')
        return 1
    finally:
        server.close()


if __name__ == '__main__':
    raise SystemExit(main())

