"""Bound the bridge's native USB calls, including handle close, in one process.

The library UPSClient stays synchronous. Only the daemon uses this supervisor.
One worker owns one handle; a lost/timed-out reply discards that worker and is
never retried here (especially important for commands with hardware effects).
"""
from __future__ import annotations

import multiprocessing
import signal
import time


class WorkerStillAlive(RuntimeError):
    """The existing native owner must be reaped before another can be opened."""


def _create_client():
    from .client import UPSClient
    return UPSClient.auto_detect()


def _worker(connection, client_factory):
    # A spawned daemon entry point may have imported bridge signal handlers.
    # This process must remain terminable even if a native call never returns.
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    client = None
    try:
        client = client_factory()
        client.connect()
        connection.send((True, (client.device_info, client.profile)))
        while True:
            method = connection.recv()
            if method == "disconnect":
                client.disconnect()
                client = None
                connection.send((True, None))
                break
            try:
                result = getattr(client, method)()
            except Exception as exc:
                connection.send((False, f"{type(exc).__name__}: {exc}"))
            else:
                connection.send((True, result))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            connection.send((False, f"{type(exc).__name__}: {exc}"))
        except (EOFError, BrokenPipeError):
            pass
    finally:
        if client is not None:
            # Parent bounds even a native close that hangs forever here.
            client.disconnect()
        connection.close()


class HardwareSession:
    def __init__(self, *, client_factory=_create_client, request_timeout=30,
                 startup_timeout=30, close_timeout=1, should_run=None):
        self.client_factory = client_factory
        self.request_timeout = request_timeout
        self.startup_timeout = startup_timeout
        self.close_timeout = close_timeout
        self.should_run = should_run
        self.device_info = {}
        self.profile = None
        self._process = None
        self._connection = None
        self.is_connected = False
        self.worker_pid = None

    def connect(self):
        if self._process is not None:
            raise RuntimeError("Hardware session already started")
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        self._connection = parent
        self._process = context.Process(target=_worker,
                                        args=(child, self.client_factory), daemon=True)
        try:
            self._process.start()
            self.worker_pid = self._process.pid
            child.close()
            self.device_info, self.profile = self._receive(self.startup_timeout)
            self.is_connected = True
        except BaseException:
            child.close()
            self._dispose()
            raise

    def _receive(self, timeout):
        deadline = time.monotonic() + timeout
        try:
            while True:
                if self.should_run is not None and not self.should_run():
                    raise InterruptedError("Bridge shutdown requested")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("USB worker did not respond; result is unknown")
                if self._connection.poll(min(0.1, remaining)):
                    ok, result = self._connection.recv()
                    if not ok:
                        raise ConnectionError(result)
                    return result
        except BaseException:
            self._dispose()
            raise

    def _call(self, method):
        if not self.is_connected:
            raise ConnectionError("USB worker is disconnected")
        try:
            self._connection.send(method)
        except (BrokenPipeError, EOFError, OSError) as exc:
            self._dispose()
            raise ConnectionError("USB worker exited") from exc
        return self._receive(self.request_timeout)

    def get_vars(self):
        return self._call("get_vars")

    def test_battery_quick(self):
        return self._call("test_battery_quick")

    def test_battery_deep(self):
        return self._call("test_battery_deep")

    def test_battery_stop(self):
        return self._call("test_battery_stop")

    def _dispose(self):
        self.is_connected = False
        process = self._process
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if process is not None and process.pid is not None:
            process.join(0.1)
            if process.is_alive():
                process.terminate()
                process.join(0.5)
            if process.is_alive():
                process.kill()
                process.join(0.5)
            if process.is_alive():
                # Never open another USB owner while this one is still alive.
                raise WorkerStillAlive("USB worker could not be killed")
            process.close()
        self._process = None

    def disconnect(self):
        try:
            if self.is_connected:
                self._connection.send("disconnect")
                self._receive(self.close_timeout)
        except (ConnectionError, EOFError, OSError, TimeoutError, InterruptedError):
            pass
        finally:
            self._dispose()
