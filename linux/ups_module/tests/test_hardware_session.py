"""Real subprocess supervision with fake hardware; never discovers USB."""
import multiprocessing
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from ups_module.hardware_session import HardwareSession


class FakeClient:
    device_info = {"product_string": "fake"}
    profile = SimpleNamespace(protocol="fake")

    def connect(self):
        pass

    def get_vars(self):
        return {"ups.status": "OL", "output.voltage": 230}

    def test_battery_quick(self):
        return True, "queued once"

    def disconnect(self):
        pass


class ReadHangs(FakeClient):
    def get_vars(self):
        time.sleep(60)


class CloseHangs(FakeClient):
    def disconnect(self):
        time.sleep(60)


class CommandHangs(FakeClient):
    def test_battery_quick(self):
        time.sleep(60)


class TestHardwareSession(unittest.TestCase):
    def test_worker_reference_survives_kill_until_exit_is_confirmed(self):
        session = HardwareSession()
        process = Mock(pid=123)
        process.is_alive.return_value = True
        session._process = process
        with self.assertRaises(RuntimeError):
            session.disconnect()
        self.assertIs(session._process, process)
        with self.assertRaisesRegex(RuntimeError, "already started"):
            session.connect()
        process.is_alive.return_value = False
        session.disconnect()
        self.assertIsNone(session._process)

    def session(self, factory):
        session = HardwareSession(client_factory=factory, request_timeout=0.4,
                                  startup_timeout=8, close_timeout=0.2)
        self.addCleanup(session.disconnect)
        session.connect()
        return session

    def assert_reaped(self, pid):
        self.assertNotIn(pid, [p.pid for p in multiprocessing.active_children()])

    def test_round_trip_preserves_data_identity_and_command_result(self):
        session = self.session(FakeClient)
        self.assertEqual(session.device_info["product_string"], "fake")
        self.assertEqual(session.profile.protocol, "fake")
        self.assertEqual(session.get_vars(), {"ups.status": "OL", "output.voltage": 230})
        self.assertEqual(session.test_battery_quick(), (True, "queued once"))
        pid = session.worker_pid
        session.disconnect()
        self.assertFalse(session.is_connected)
        self.assert_reaped(pid)

    def test_native_read_hang_is_bounded_and_next_connection_works(self):
        session = self.session(ReadHangs)
        pid = session.worker_pid
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            session.get_vars()
        self.assertLess(time.monotonic() - started, 3)
        self.assertFalse(session.is_connected)
        self.assert_reaped(pid)
        recovered = self.session(FakeClient)
        self.assertEqual(recovered.get_vars()["ups.status"], "OL")

    def test_native_close_hang_does_not_block_shutdown(self):
        session = self.session(CloseHangs)
        pid = session.worker_pid
        started = time.monotonic()
        session.disconnect()
        self.assertLess(time.monotonic() - started, 3)
        self.assert_reaped(pid)

    def test_timed_out_command_is_not_retried_and_worker_is_discarded(self):
        session = self.session(CommandHangs)
        pid = session.worker_pid
        with self.assertRaises(TimeoutError):
            session.test_battery_quick()
        self.assert_reaped(pid)
        with self.assertRaises(ConnectionError):
            session.test_battery_quick()

    def test_shutdown_cancels_pending_read_without_waiting_for_deadline(self):
        session = self.session(ReadHangs)
        session.request_timeout = 60
        started = time.monotonic()
        session.should_run = lambda: time.monotonic() - started < 0.2
        with self.assertRaises(InterruptedError):
            session.get_vars()
        self.assertLess(time.monotonic() - started, 3)
        self.assert_reaped(session.worker_pid)


if __name__ == "__main__":
    unittest.main()
