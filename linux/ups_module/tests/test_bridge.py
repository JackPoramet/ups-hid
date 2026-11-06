"""Bridge regressions; all service/DB/system paths are isolated."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock, call
from types import SimpleNamespace
import subprocess

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import enerex_ups_bridge as bridge


class TestDummyWriter(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "myups.dev"
        self.guards = [
            patch.object(bridge, "DUMMY_FILE", str(self.target)),
            patch.object(bridge, "_nut_gid", return_value=123, create=True),
            patch.object(bridge.os, "chown", create=True),
        ]
        self.mocks = [g.start() for g in self.guards]
        for g in self.guards:
            self.addCleanup(g.stop)

    def test_permissions_are_set_before_each_atomic_publish(self):
        real_replace = bridge.os.replace
        with patch.object(bridge.os, "chmod") as chmod:
            def publish(src, dst):
                self.mocks[2].assert_called_with(src, 0, 123)
                chmod.assert_called_with(src, 0o640)
                real_replace(src, dst)
            with patch.object(bridge.os, "replace", side_effect=publish):
                for status in ("OL", "OB", "OL"):
                    bridge.write_dummy_file({"ups.status": status})
                    self.assertEqual(self.target.read_text(), f"ups.status: {status}\n")
        self.assertEqual(list(Path(self.temp.name).iterdir()), [self.target])

    def test_failed_publish_keeps_previous_snapshot_and_cleans_temp(self):
        self.target.write_text("old snapshot\n")
        with patch.object(bridge.os, "chmod"), patch.object(bridge.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                bridge.write_dummy_file({"ups.status": "OL"})
        self.assertEqual(self.target.read_text(), "old snapshot\n")
        self.assertEqual(list(Path(self.temp.name).iterdir()), [self.target])


class TestDriverReconciliation(unittest.TestCase):
    def setUp(self):
        for guard in (
            patch.object(bridge, "_driver_running", None),
            patch.object(bridge, "_driver_checked_at", 0.0, create=True),
            patch.object(bridge.time, "monotonic", return_value=20.0),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def test_failed_start_retries_without_success_cache(self):
        with patch("subprocess.run", side_effect=[SimpleNamespace(returncode=n) for n in (3, 1, 3, 1)]) as run:
            self.assertFalse(bridge.set_nut_driver_state(True))
            self.assertFalse(bridge.set_nut_driver_state(True))
        starts = [c for c in run.call_args_list if "start" in c.args[0]]
        self.assertEqual(len(starts), 2)
        self.assertIsNot(bridge._driver_running, True)

    def test_unknown_service_state_not_treated_as_stopped(self):
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=4)):
            self.assertFalse(bridge.set_nut_driver_state(False))
        self.assertIsNone(bridge._driver_running)

    def test_failed_stop_does_not_cache_stopped(self):
        bridge._driver_running = True
        with patch("subprocess.run", side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=1)]):
            self.assertFalse(bridge.set_nut_driver_state(False))
        self.assertIsNot(bridge._driver_running, False)

    def test_timeout_is_retryable(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("systemctl", 5)) as run:
            self.assertFalse(bridge.set_nut_driver_state(True))
            self.assertFalse(bridge.set_nut_driver_state(True))
            self.assertGreaterEqual(run.call_count, 2)

    def test_driver_stopped_externally_is_started_again(self):
        bridge._driver_running = True
        bridge._driver_checked_at = 10.0
        responses = [SimpleNamespace(returncode=3), SimpleNamespace(returncode=0), SimpleNamespace(returncode=0)]
        with patch("subprocess.run", side_effect=responses) as run:
            self.assertTrue(bridge.set_nut_driver_state(True))
            self.assertTrue(any("start" in c.args[0] for c in run.call_args_list))

    def test_active_service_is_not_restarted(self):
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0)) as run:
            self.assertTrue(bridge.set_nut_driver_state(True))
            self.assertTrue(bridge.set_nut_driver_state(True))
            self.assertEqual(run.call_count, 1)
            self.assertNotIn("start", run.call_args.args[0])


class TestUnknownMeter(unittest.TestCase):
    def test_missing_load_never_estimates_zero_power_on_rated_model(self):
        result = bridge.enrich_nut_variables({"ups.status": "OL"}, {"product_string": "Offline UPS"})
        for key in ("ups.load", "output.power", "output.power.apparent"):
            self.assertNotIn(key, result)

    def test_measured_zero_load_can_estimate_zero_power(self):
        result = bridge.enrich_nut_variables({"ups.status": "OL", "ups.load": 0}, {"product_string": "Offline UPS"})
        self.assertEqual(result["output.power"], 0)
        self.assertEqual(result["output.power.apparent"], 0)

    def test_missing_voltage_preserves_online_load_and_power(self):
        data = {"ups.status": "OL", "input.voltage": 220.0, "ups.load": 35,
                "output.power": 100}
        result = bridge.enrich_nut_variables(data, {"product_string": "Innova Unity"})
        self.assertEqual(result["ups.status"], "OL")
        self.assertEqual(result["ups.load"], 35)
        self.assertEqual(result["output.power"], 100)
        self.assertNotIn("output.voltage", result)
        self.assertNotEqual(result["outlet.1.status"], "off")

    def test_measured_zero_output_still_means_off(self):
        result = bridge.enrich_nut_variables(
            {"ups.status": "OL", "input.voltage": 220.0, "output.voltage": 0.0}, {})
        self.assertEqual(result["ups.status"], "OFF")
        self.assertEqual(result["output.voltage"], 0.0)


class TestCommandRouting(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.queue = Path(temp.name) / "commands"
        self.queue.touch()
        for guard in (
            patch.object(bridge, "CMD_FILES", [str(self.queue)]),
            patch.object(bridge, "_pending_commands", []),
            patch.dict(sys.modules, {"pymysql": None, "mysql.connector": None, "MySQLdb": None}),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def test_file_command_invokes_exactly_one_matching_method(self):
        for mode in ("quick", "deep", "stop"):
            with self.subTest(mode=mode):
                client = Mock()
                for name in ("quick", "deep", "stop"):
                    getattr(client, "test_battery_" + name).return_value = (True, "fake write")
                self.queue.write_text("cmd_test_battery_" + mode)
                bridge.check_and_execute_commands(client)
                self.assertEqual(client.method_calls, [getattr(call, "test_battery_" + mode)()])
                self.assertEqual(self.queue.read_text(), "")

    def test_direct_quick_signal_remains_supported(self):
        client = Mock()
        client.test_battery_quick.return_value = (True, "fake write")
        with patch.object(bridge.signal, "SIGUSR1", 10, create=True):
            bridge.handle_battery_test_signal(10, None)
        bridge.check_and_execute_commands(client)
        client.test_battery_quick.assert_called_once_with()

    def test_native_command_allowlist_preserves_transport_failure(self):
        client = Mock(is_connected=True,profile=SimpleNamespace(features={'has_battery_test':True}))
        client.test_battery_quick.return_value = (False, "NAK")
        snapshot=self.queue.parent/'snapshot.dev'
        snapshot.write_text('ups.status: OL\n')
        with patch.object(bridge,'DUMMY_FILE',str(snapshot)):
            self.assertEqual(bridge.execute_nut_command(client, "test.battery.start.quick"), (False, "NAK"))
        self.assertEqual(client.method_calls, [call.test_battery_quick()])
        client.reset_mock()
        with self.assertRaises(ValueError):
            bridge.execute_nut_command(client, "load.off")
        self.assertEqual(client.method_calls, [])

    def test_native_dispatch_rejects_snapshot_that_expired_while_queued(self):
        import os,time
        snapshot=self.queue.parent/'snapshot.dev'
        snapshot.write_text('ups.status: OL\n')
        os.utime(snapshot,(time.time()-10,time.time()-10))
        client=Mock(is_connected=True,profile=SimpleNamespace(features={'has_battery_test':True}))
        client.test_battery_stop.return_value=(True,'fake USB write')
        with patch.object(bridge,'DUMMY_FILE',str(snapshot)):
            success,_=bridge.execute_nut_command(client,'test.battery.stop')
        self.assertFalse(success)
        self.assertEqual(client.method_calls,[])

    def test_inline_driver_comment_does_not_put_valid_native_config_in_standby(self):
        conf=self.queue.parent/'ups.conf'
        conf.write_text('[myups]\ndriver = enerex # native adapter\nport=/etc/nut/myups.dev\n')
        with patch.object(bridge,'Path',return_value=conf):
            self.assertTrue(bridge.is_enerex_driver_active())

    def test_existing_web_worker_owns_database_commands(self):
        import types
        owner=self.queue.parent/'ups-command.py'
        owner.write_text('# configured original web command consumer\n')
        attempts=[]
        def connect(**_):
            attempts.append('database command poll')
            raise AssertionError('Original web worker owns this queue')
        with patch.object(bridge,'WEB_COMMAND_OWNER',str(owner),create=True), patch.dict(sys.modules,{'pymysql':types.SimpleNamespace(connect=connect)}):
            bridge.check_and_execute_commands(Mock())
        self.assertEqual(attempts,[])

    def test_standalone_database_close_failure_does_not_break_usb_polling(self):
        import types
        cursor=Mock()
        cursor.fetchall.return_value=[]
        connection=Mock()
        connection.cursor.return_value=cursor
        connection.close.side_effect=OSError('fake database close failure')
        with patch.object(bridge,'WEB_COMMAND_OWNER',str(self.queue.parent/'missing.py')), patch.dict(sys.modules,{'pymysql':types.SimpleNamespace(connect=lambda **_:connection)}):
            self.assertEqual(bridge._read_database_commands(),[])

    def test_command_flags_follow_profile_capability(self):
        data = {"ups.status": "OL"}
        unsupported = SimpleNamespace(id="unknown", manufacturer="PPC", model="unknown", features={}, nominal_va=None, nominal_watts=None)
        result = bridge.enrich_nut_variables(data.copy(), {}, unsupported)
        self.assertFalse(any(k.startswith("cmd.test.") for k in result))
        unsupported.features = {"has_battery_test": True}
        result = bridge.enrich_nut_variables(data.copy(), {}, unsupported)
        self.assertEqual(result["cmd.test.battery.start.quick"], 1)


class TestMainRecovery(TestDummyWriter):
    def setUp(self):
        super().setUp()
        self.sessions = []
        self.sleeps = 0
        self.starts = []
        for guard in (
            patch.object(bridge, "_running", True),
            patch.object(bridge, "acquire_single_instance_lock"),
            patch.object(bridge, "CommandBroker", create=True),
            patch.object(bridge, "is_enerex_driver_active", return_value=True),
            patch.object(bridge, "check_and_execute_commands"),
            patch.object(bridge, "HardwareSession", side_effect=self.new_session, create=True),
            patch.object(bridge.UPSClient, "auto_detect", side_effect=AssertionError("Unsupervised hardware blocked")),
            patch.object(bridge.time, "sleep", side_effect=self.sleep),
            patch("subprocess.run", return_value=SimpleNamespace(returncode=0)),
            patch.object(bridge.os, "chmod"),
            patch.object(bridge, "set_nut_driver_state", side_effect=self.driver),
        ):
            guard.start()
            self.addCleanup(guard.stop)

    def sleep(self, _):
        self.sleeps += 1
        if self.sleeps >= 4:
            bridge._running = False

    def driver(self, running):
        if running:
            self.assertIn("ups.status: OL", self.target.read_text())
        self.starts.append(running)
        return len(self.starts) > 1  # First start fails; next poll must retry.

    def new_session(self, **kwargs):
        session = Mock(is_connected=True, profile=None,
                       device_info={"product_string": "Innova Unity"})
        session.get_vars.side_effect = self.read
        self.sessions.append(session)
        return session

    def read(self):
        return {"ups.status": "OL", "output.voltage": 230}

    def test_driver_failure_retries_without_closing_healthy_usb(self):
        bridge.main()
        self.assertEqual(len(self.sessions), 1)
        self.assertGreaterEqual(self.starts.count(True), 2)
        self.sessions[0].disconnect.assert_called_once()

    def test_unreaped_owner_is_retained_until_cleanup_succeeds(self):
        from ups_module.hardware_session import WorkerStillAlive
        owner = self.new_session()
        owner.get_vars.side_effect = RuntimeError("lost USB")
        cleanup_calls = 0
        def cleanup():
            nonlocal cleanup_calls
            cleanup_calls += 1
            if cleanup_calls == 1:
                raise WorkerStillAlive("still alive")
        owner.disconnect.side_effect = cleanup
        with patch.object(bridge, "HardwareSession", return_value=owner) as factory:
            bridge.main()
        self.assertGreaterEqual(owner.disconnect.call_count, 2)
        # A new session cannot replace an unreaped one on the next scan.
        self.assertLess(factory.call_count, owner.connect.call_count)

    def test_invalid_initial_or_poll_telemetry_clears_state_and_reconnects(self):
        from ups_module.drivers.megatec import MegatecQ1Driver
        for initial_failure in (True, False):
            with self.subTest(initial_failure=initial_failure):
                self.target.write_text("stale")
                self.sessions.clear()
                self.starts.clear()
                self.sleeps = 0
                bridge._running = True
                reads = 0
                def read():
                    nonlocal reads
                    reads += 1
                    if reads == (1 if initial_failure else 2):
                        device = Mock()
                        device.get_indexed_string.return_value = "NAK"
                        return MegatecQ1Driver(device).get_vars()
                    if len(self.sessions) > 1:
                        self.assertIn(False, self.starts)
                        self.assertFalse(self.target.exists())
                        bridge._running = False
                    return {"ups.status": "OL", "output.voltage": 230}
                self.read = read
                bridge.main()
                self.assertEqual(len(self.sessions), 2)
                self.sessions[0].disconnect.assert_called_once()
                self.assertIn("ups.status: OL", self.target.read_text())


if __name__ == "__main__":
    unittest.main()
