"""Execute CLI helpers only after replacing every system path with sandbox paths."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import unittest

LINUX = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
if os.name == "nt":
    BASH = "C:/Program Files/Git/bin/bash.exe" if Path("C:/Program Files/Git/bin/bash.exe").exists() else None


@unittest.skipUnless(BASH, "Bash is required for sandbox CLI checks")
class TestCommandScripts(unittest.TestCase):
    def test_legacy_cleanup_matches_bridge_process_only_not_ssh_payload(self):
        fake_commands = '''
systemctl() { return 0; }
flock() { return 0; }
pkill() {
    local pattern="${@: -1}"
    if [[ '/usr/bin/python3 /opt/enerex-ups/enerex_ups_bridge.py' =~ $pattern ]]; then echo MATCH_BRIDGE; fi
    if [[ 'python3 ./enerex_ups_bridge.py' =~ $pattern ]]; then echo MATCH_RELATIVE; fi
    if [[ 'python3 -u /opt/enerex-ups/enerex_ups_bridge.py' =~ $pattern ]]; then echo MATCH_UNBUFFERED; fi
    if [[ "bash -c sha256sum /opt/enerex-ups/enerex_ups_bridge.py" =~ $pattern ]]; then echo MATCH_SSH; fi
    if [[ "python3 utility.py --note enerex_ups_bridge.py" =~ $pattern ]]; then echo MATCH_OTHER; fi
}
'''
        for name, end_marker in (("update.sh", "# Clear stale"), ("install.sh", 'echo "--- 3.'), ("uninstall.sh", 'echo "--- 3.')):
            with self.subTest(script=name):
                source = (LINUX / name).read_text()
                start = 'echo "--- 2. Stopping' if name == "install.sh" else 'echo "--- 1. Stopping'
                block = source[source.index(start):source.index(end_marker)]
                result = subprocess.run([BASH, "-c", fake_commands + block], text=True,
                                        capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                matches = [line for line in result.stdout.splitlines() if line.startswith("MATCH_")]
                self.assertEqual(matches, ["MATCH_BRIDGE", "MATCH_RELATIVE", "MATCH_UNBUFFERED"])

    @unittest.skipUnless(os.name == "posix", "Requires native Linux Bash")
    def test_cleanup_refuses_locked_bridge_without_unlinking_inode(self):
        import fcntl
        lock = self.root / "bridge.lock"
        with lock.open("w") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            inode = lock.stat().st_ino
            for name in ("install.sh", "update.sh", "uninstall.sh"):
                with self.subTest(script=name):
                    source = (LINUX / name).read_text()
                    block = source[source.index("# Never unlink"):source.index("done", source.index("# Never unlink")) + 4]
                    block = block.replace("/run/enerex_ups_bridge.lock", str(lock))
                    block = block.replace("/tmp/enerex_ups_bridge.lock", str(self.root / "unused.lock"))
                    result = subprocess.run([BASH, "-c", block], text=True, capture_output=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Bridge still owns", result.stderr)
                    self.assertEqual(lock.stat().st_ino, inode)
                    self.assertNotIn("rm -f /run/enerex_ups_bridge.lock", source)
                    # An unused /tmp lock cannot block the /run owner policy.
                    alternate = source[source.index("# Never unlink"):source.index("done", source.index("# Never unlink")) + 4]
                    alternate = alternate.replace("/tmp/enerex_ups_bridge.lock", str(lock))
                    alternate = alternate.replace("/run/enerex_ups_bridge.lock", str(self.root / "unused.lock"))
                    result = subprocess.run([BASH, "-c", alternate], text=True, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.name == "posix", "Requires native Linux Bash")
    def test_release_scripts_parse_without_rewriting_packaged_bytes(self):
        for name in ("install.sh", "update.sh", "uninstall.sh", "enerex-test", "upscmd", "enerex-driver"):
            with self.subTest(script=name):
                result = subprocess.run([BASH, "-n", str(LINUX / name)],
                                        text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_queue = self.root / "run-queue"
        self.tmp_queue = self.root / "tmp-queue"
        self.conf = self.root / "ups.conf"
        self.conf.write_text("[myups]\ndriver = enerex\n")
        self.native = self.root / "native-upscmd"
        self.native.write_text("#!/bin/bash\nprintf 'NATIVE:%s\\n' \"$*\"\n", newline="\n")
        self.native.chmod(0o755)

    def _stage(self, name):
        text = (LINUX / name).read_text(encoding="utf-8")
        paths = {"/run/enerex_ups_cmd": self.run_queue,
                 "/tmp/enerex_ups_cmd": self.tmp_queue,
                 "/etc/nut/ups.conf": self.conf,
                 "/usr/local/bin/enerex-test": self.root / "enerex-test",
                 "/usr/bin/upscmd.orig": self.native,
                 "/usr/bin/upscmd": self.native}
        for src, dst in paths.items():
            text = text.replace(src, dst.as_posix())
        for original in paths:
            self.assertNotIn(original, text)
        dest = self.root / name
        dest.write_text(text, newline="\n")
        dest.chmod(0o755)
        return dest

    def _run(self, name, *args):
        script = self._stage(name)
        return subprocess.run([BASH, str(script), *args], text=True, capture_output=True, timeout=5)

    def test_one_command_per_helper_call(self):
        self.run_queue.touch()
        self.tmp_queue.touch()
        for mode in ("quick", "deep", "stop"):
            with self.subTest(mode=mode):
                result = self._run("enerex-test", mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.run_queue.read_text(), f"cmd_test_battery_{mode}\n")
                self.assertEqual(self.tmp_queue.read_text(), "")
                self.assertNotIn("pkill", (LINUX / "enerex-test").read_text())

    def test_missing_queues_and_invalid_command_fail(self):
        for mode in ("quick", "unknown"):
            with self.subTest(mode=mode):
                result = self._run("enerex-test", mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("OK", result.stdout)
        self.assertFalse(self.run_queue.exists())
        self.assertFalse(self.tmp_queue.exists())

    def test_upscmd_routes_exact_command_to_one_helper(self):
        self.run_queue.touch()
        self._stage("enerex-test")
        result = self._run("upscmd", "myups", "test.battery.start.deep")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_queue.read_text(), "cmd_test_battery_deep\n")

    def test_native_driver_passes_through(self):
        self.conf.write_text("[myups]\ndriver = usbhid-ups\n")
        result = self._run("upscmd", "myups", "test.battery.start.quick")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("NATIVE:myups test.battery.start.quick", result.stdout)
        self.assertFalse(self.run_queue.exists())

    def test_remote_other_ups_and_option_forms_pass_through(self):
        self.run_queue.touch()
        self._stage("enerex-test")
        for args in (("other@remote", "test.battery.start.deep"),
                     ("other", "test.battery.start.deep"),
                     ("myups@localhost:9999", "test.battery.start.deep"),
                     ("-l", "myups", "test.battery.start.deep")):
            with self.subTest(args=args):
                result = self._run("upscmd", *args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("NATIVE:", result.stdout)
                self.assertEqual(self.run_queue.read_text(), "")

    def test_local_endpoint_and_configured_section_route_correctly(self):
        self.run_queue.touch()
        self._stage("enerex-test")
        self.conf.write_text("[other]\ndriver = usbhid-ups\n[myups]\ndriver = enerex\n")
        result = self._run("upscmd", "myups@localhost:3493", "test.battery.start.deep")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.run_queue.read_text(), "cmd_test_battery_deep\n")

    def test_install_and_update_use_same_helpers_and_boot_ipc(self):
        for name in ("install.sh", "update.sh"):
            text = (LINUX / name).read_text()
            self.assertIn('install -m 0755 "$SCRIPT_DIR/enerex-test" /usr/local/bin/enerex-test', text)
            self.assertIn('install -m 0755 "$SCRIPT_DIR/upscmd" /usr/local/bin/upscmd', text)
            self.assertIn("systemd-tmpfiles --create /etc/tmpfiles.d/enerex-ups.conf", text)
        conf = (LINUX / "enerex-ups.conf").read_text()
        self.assertIn("f /run/enerex_ups_cmd 0660 root ups-hid -", conf)
        self.assertIn("/etc/tmpfiles.d/enerex-ups.conf", (LINUX / "uninstall.sh").read_text())

    def test_native_driver_install_replaces_link_without_overwriting_dummy_binary(self):
        for name in ("install.sh", "update.sh"):
            with self.subTest(script=name):
                source=(LINUX/name).read_text()
                begin=source.find('# Install the native NUT adapter')
                self.assertGreaterEqual(begin,0,'native adapter migration is required')
                block=source[begin:source.index('# Native adapter installed',begin)]
                target_dir=self.root/name.replace('.','-')
                target_dir.mkdir()
                dummy=target_dir/'dummy-ups'
                dummy.write_text('original packaged dummy driver')
                destination=target_dir/'enerex'
                if os.name=='posix':destination.symlink_to(dummy)
                else:destination.write_text('old driver launcher')
                block=block.replace('/lib/nut',target_dir.as_posix())
                block=block.replace('"$SCRIPT_DIR/enerex-driver"','"'+(LINUX/'enerex-driver').as_posix()+'"')
                result=subprocess.run([BASH,'-c',block],text=True,capture_output=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(dummy.read_text(),'original packaged dummy driver')
                self.assertFalse(destination.is_symlink())
                self.assertEqual(destination.read_bytes(),(LINUX/'enerex-driver').read_bytes())

    def test_uninstall_restores_disabled_or_enabled_monitor_without_changing_other_units(self):
        source=(LINUX/'uninstall.sh').read_text()
        start=source.index('# Restore only the enablement state')
        block=source[start:source.index('# Original monitor enablement restored',start)]
        marker=self.root/'original-enablement'
        block=block.replace('/etc/nut/.enerex-monitor-original-enablement',marker.as_posix())
        for state,expected in (('disabled','disable nut-monitor.service'),('enabled','enable nut-monitor.service')):
            with self.subTest(state=state):
                marker.write_text(state)
                fake='systemctl() { echo "$*"; }; original_monitor='+state+'\n'
                result=subprocess.run([BASH,'-c',fake+block],text=True,capture_output=True,timeout=5)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.strip(),expected)
                self.assertFalse(marker.exists())

    @unittest.skipUnless(os.name == "posix" and shutil.which("systemd-tmpfiles"),
                         "Requires Linux systemd-tmpfiles")
    def test_tmpfiles_recreates_boot_queue_with_restricted_mode_in_sandbox(self):
        config = (LINUX / "enerex-ups.conf").read_text()
        config = config.replace("/run/enerex_ups_cmd", self.run_queue.as_posix())
        config = config.replace("/tmp/enerex_ups_cmd", self.tmp_queue.as_posix())
        config = config.replace("/run/enerex-ups", (self.root/'runtime').as_posix())
        config = config.replace("root ups-hid", f"{os.getuid()} {os.getgid()}")
        config = config.replace("root nut", f"{os.getuid()} {os.getgid()}")
        self.assertNotIn("/run/enerex_ups_cmd", config)
        self.assertNotIn("/tmp/enerex_ups_cmd", config)
        path = self.root / "enerex-ups.conf"
        path.write_text(config)
        for boot in range(2):
            if boot:
                self.run_queue.unlink()  # /run is cleared at boot.
            result = subprocess.run([shutil.which("systemd-tmpfiles"), "--create", str(path)],
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            for queue in (self.run_queue, self.tmp_queue):
                info = queue.stat()
                self.assertEqual(stat.S_IMODE(info.st_mode), 0o660)
                self.assertEqual((info.st_uid, info.st_gid), (os.getuid(), os.getgid()))

    def _update_health(self, failed=False, monitor_failed=False):
        text = (LINUX / "update.sh").read_text()
        block = text[text.index("# Health checks"):]
        self.assertNotIn("systemctl stop", block)
        block = block.replace("/etc/nut/myups.dev", (self.root / "state").as_posix())
        fake_services = 'systemctl() { case "$*" in is-failed*) return ' + ("0" if failed else "1") + ' ;; *nut-monitor*) return ' + ('1' if monitor_failed else '0') + ' ;; *nut-driver*) return 1 ;; *) return 0 ;; esac; };\n'
        return subprocess.run([BASH, "-c", fake_services + block], text=True, capture_output=True, timeout=5)

    def test_update_does_not_call_missing_driver_healthy_when_state_exists(self):
        (self.root / "state").write_text("ups.status: OL\n")
        result = self._update_health()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("[OK] Update Complete", result.stdout)

    def test_update_allows_standby_without_state_file(self):
        result = self._update_health()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("standby", result.stdout)

    def test_notification_monitor_failure_fails_update_health(self):
        result=self._update_health(monitor_failed=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('nut-monitor',result.stdout)

    def test_failed_driver_is_not_healthy_even_before_first_snapshot(self):
        for state in (None, "ups.status: WAIT\n"):
            if state is not None:
                (self.root / "state").write_text(state)
            result = self._update_health(failed=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("No UPS connected", result.stdout)

    def _capture_mode(self, rc=0, active=True, recovery=True, async_run=False, publish_on_stop=False):
        def bash_path(path):
            text = path.as_posix()
            return "/" + text[0].lower() + text[2:] if os.name == "nt" else text
        fake_bin = self.root / "bin"
        fake_bin.mkdir(exist_ok=True)
        self.trace = self.root / "capture.trace"
        self.trace.touch()
        scripts = {
            "systemctl": '''#!/bin/bash
printf 'service:%s\\n' "$*" >> "$TRACE"
if [ "$1" = is-active ]; then exit "$ACTIVE_RC"; fi
if [ "$1" = stop ] && [ "$STOP_PUBLISH" = 1 ]; then
    sleep 0.05
    printf 'ups.status: OL\\n' > "$SNAPSHOT"
fi
if [ "$1" = start ]; then
    # A real bridge publishes after process startup. Separate the fake write
    # from mktemp's coarse timestamp tick before asserting freshness.
    sleep 0.05
    if [ "$STOP_PUBLISH" != 1 ]; then printf 'ups.status: OL\\n' > "$SNAPSHOT"; fi
fi
''',
            "python3": '''#!/bin/bash
printf 'capture\\n' >> "$TRACE"
if [ "$CAPTURE_RC" = hang ]; then sleep 60; fi
if [ "$CAPTURE_RC" = hold ]; then sleep 2; CAPTURE_RC=0; fi
[ "$CAPTURE_RC" = 0 ] || exit "$CAPTURE_RC"
printf '{"report_74_raw":[116,9,0]}\\n' > "$3"
''',
            "upsc": '''#!/bin/bash
if [ "$RECOVERY" = 0 ] && grep -q 'service:start' "$TRACE"; then exit 1; fi
printf 'device.model: fixture\\nups.status: OL\\n'
''',
        }
        if os.name == "nt":
            scripts["flock"] = "#!/bin/bash\nexit 0\n"
        for name, text in scripts.items():
            path = fake_bin / name
            path.write_text(text, newline="\n")
            path.chmod(0o755)
        (self.root / "ups_module").mkdir(exist_ok=True)
        (self.root / "ups_module/capture_ratings.py").touch()
        text = (LINUX / "update.sh").read_text().replace('if [ "$EUID" -ne 0 ]; then', 'if false; then', 1)
        text = text.replace("/run/enerex-ups-maintenance.lock", bash_path(self.root / "maintenance.lock"))
        text = text.replace("/etc/nut/ups.conf", bash_path(self.conf))
        text = text.replace("/etc/nut/myups.dev", bash_path(self.root / "state"))
        script = self.root / "update.sh"
        script.write_text(text, newline="\n")
        output = self.root / "rating.json"
        env = dict(os.environ, PATH=bash_path(fake_bin) + ":/usr/bin:/bin",
                   TRACE=bash_path(self.trace), CAPTURE_RC=str(rc), ACTIVE_RC="0" if active else "3",
                   SNAPSHOT=bash_path(self.root / "state"), RECOVERY="1" if recovery else "0",
                   STOP_PUBLISH="1" if publish_on_stop else "0")
        self.capture_command = [BASH, bash_path(script), "--capture-ratings", bash_path(output)]
        self.capture_env = env
        if async_run:
            return subprocess.Popen(self.capture_command, env=env, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE), output
        result = subprocess.run(self.capture_command, env=env, text=True, capture_output=True, timeout=45)
        return result, output, self.trace.read_text()

    def test_capture_mode_stops_before_read_and_restores_bridge(self):
        result, output, trace = self._capture_mode()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(), '{"report_74_raw":[116,9,0]}\n')
        events = [line for line in trace.splitlines() if not line.startswith("deadline:")]
        # Recovery may check service readiness more than once; compare its ordered prefix.
        events = events[:5]
        self.assertEqual(events, [
            "service:is-active --quiet enerex-ups-bridge.service",
            "service:is-active --quiet nut-driver.service",
            "service:stop enerex-ups-bridge.service nut-driver.service",
            "capture", "service:start enerex-ups-bridge.service",
        ])

    def test_capture_real_deadline_restores_bridge(self):
        started = time.monotonic()
        result, output, trace = self._capture_mode(rc="hang")
        self.assertEqual(result.returncode, 124)
        self.assertLess(time.monotonic() - started, 23)
        self.assertFalse(output.exists())
        self.assertIn("service:start enerex-ups-bridge.service", trace)

    def test_capture_failure_and_deadline_restore_bridge(self):
        for rc in (7, 124):
            with self.subTest(rc=rc):
                result, output, trace = self._capture_mode(rc=rc)
                self.assertEqual(result.returncode, rc)
                self.assertFalse(output.exists())
                self.assertIn("service:start enerex-ups-bridge.service", trace)

    def test_capture_refuses_to_change_inactive_bridge(self):
        result, output, trace = self._capture_mode(active=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        self.assertEqual(trace.strip(), "service:is-active --quiet enerex-ups-bridge.service")

    def test_capture_rejects_native_driver_before_changing_services(self):
        self.conf.write_text("[myups]\ndriver = usbhid-ups\n")
        result, output, trace = self._capture_mode()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        self.assertNotIn("service:stop", trace)
        self.assertNotIn("service:start", trace)

    def test_capture_fails_if_previous_healthy_monitoring_does_not_recover(self):
        result, output, trace = self._capture_mode(recovery=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(output.exists())
        self.assertIn("Failed to restore healthy NUT", result.stderr)

    def test_shutdown_snapshot_cannot_substitute_for_a_new_bridge_publish(self):
        result, output, trace = self._capture_mode(publish_on_stop=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(output.exists())
        self.assertIn("Failed to restore healthy NUT", result.stderr)

    @unittest.skipUnless(os.name == "posix", "Requires native flock")
    def test_concurrent_capture_cannot_restart_another_usb_owner(self):
        first, output = self._capture_mode(rc="hold", async_run=True)
        try:
            deadline = time.monotonic() + 4
            while "capture\n" not in self.trace.read_text() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertIn("capture\n", self.trace.read_text())
            second = subprocess.run(self.capture_command, env=self.capture_env,
                                    text=True, capture_output=True, timeout=4)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("maintenance", second.stderr)
            first.communicate(timeout=8)
            self.assertEqual(first.returncode, 0)
            trace = self.trace.read_text()
            self.assertEqual(trace.count("service:stop"), 1)
            self.assertEqual(trace.count("service:start"), 1)
        finally:
            if first.poll() is None:
                first.terminate()
                first.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
