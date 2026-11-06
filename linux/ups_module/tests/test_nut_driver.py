"""NUT driver protocol tests use real temporary sockets and recorded telemetry."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest


@unittest.skipUnless(os.name == "posix", "Native NUT Unix-socket protocol")
class TestNutDriver(unittest.TestCase):
    def setUp(self):
        from ups_module.nut_driver import DriverServer
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = self.root/'state.dev'
        self.snapshot.write_text('ups.status: OL\ndevice.model: UPS "quoted" \\ unit\ninput.voltage: 230\ncmd.test.battery.stop: 1\n')
        self.effects = []
        def command_sender(path, command):
            self.effects.append(command)
            return {'ok': True, 'message': 'fake hardware transport accepted'}
        self.server = DriverServer(self.root/'enerex-myups', self.snapshot, self.root/'commands.sock',
                                   command_sender=command_sender)
        self.server.start()
        self.addCleanup(self.server.close)
        self.client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.client.settimeout(.3)
        self.client.connect(str(self.root/'enerex-myups'))
        self.addCleanup(self.client.close)
        self.server.step(0)

    def exchange(self, payload):
        self.client.sendall(payload)
        self.server.step(.01)
        try:
            return self.client.recv(65536).decode()
        except socket.timeout:
            return ''

    def test_complete_dump_escaping_capability_and_ping(self):
        response = self.exchange(b'DUMPALL\n')
        self.assertIn('SETINFO device.model "UPS \\"quoted\\" \\\\ unit"\n', response)
        self.assertIn('ADDCMD test.battery.stop\n', response)
        self.assertNotIn('ADDCMD load.off', response)
        self.assertTrue(response.endswith('DATAOK\nDUMPDONE\n'), response)
        self.assertEqual(self.exchange(b'PING\n'), 'PONG\n')

    def test_internal_version_remains_numeric_for_existing_web_database(self):
        from ups_module.nut_driver import read_snapshot
        self.assertEqual(float(read_snapshot(self.snapshot)['driver.version.internal']), 1.0)

    def test_removed_variables_and_stale_data_revoke_commands(self):
        self.exchange(b'DUMPALL\n')
        self.snapshot.write_text('ups.status: OL\ncmd.test.battery.stop: 1\n')
        self.server.refresh()
        output = self.client.recv(65536).decode()
        self.assertIn('DELINFO input.voltage\n', output)
        os.utime(self.snapshot, (time.time()-10, time.time()-10))
        self.server.refresh()
        output = self.client.recv(65536).decode()
        self.assertIn('DATASTALE\n', output)
        self.assertIn('DELCMD test.battery.stop\n', output)
        self.exchange(b'INSTCMD test.battery.stop\n')
        self.assertEqual(self.effects, [])

    def test_only_registered_exact_commands_are_dispatched(self):
        self.exchange(b'DUMPALL\n')
        self.exchange(b'INSTCMD load.off\nINSTCMD test.battery.stop extra\nSET ups.status OB\n')
        self.assertEqual(self.effects, [])
        self.exchange(b'INSTCMD test.battery.stop\n')
        deadline = time.monotonic()+1
        while not self.effects and time.monotonic()<deadline:
            time.sleep(.01)
        self.assertEqual(self.effects, ['test.battery.stop'])

    def test_partial_command_and_oversized_client_do_not_block_polling(self):
        self.client.sendall(b'PI')
        self.server.step(.01)
        self.assertEqual(self.exchange(b'NG\n'), 'PONG\n')
        self.client.sendall(b'x'*8193)
        self.server.step(.01)
        self.assertEqual(self.client.recv(1), b'')

    def test_duplicate_start_does_not_unlink_live_socket(self):
        from ups_module.nut_driver import DriverServer
        inode = (self.root/'enerex-myups').stat().st_ino
        other = DriverServer(self.root/'enerex-myups', self.snapshot, self.root/'commands.sock')
        self.addCleanup(other.close)
        with self.assertRaises((BlockingIOError, RuntimeError)):
            other.start()
        self.assertEqual((self.root/'enerex-myups').stat().st_ino, inode)
        self.assertEqual(self.exchange(b'PING\n'), 'PONG\n')

    def cli(self, *args):
        import pwd
        return subprocess.run([sys.executable, '-m', 'ups_module.nut_driver', '-a', 'qa',
                               '--state-dir', str(self.root/'runtime'), '--snapshot', str(self.snapshot),
                               '-u', pwd.getpwuid(os.getuid()).pw_name, *args],
                              text=True, capture_output=True, timeout=7,
                              env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2])))

    def test_cli_killpower_is_explicitly_unsupported_without_side_effects(self):
        result = self.cli('-k')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unsupported', result.stderr.lower())
        self.assertFalse((self.root/'runtime').exists())

    def test_daemon_ready_duplicate_refused_and_sigterm_cleans_socket(self):
        import signal
        result = self.cli()
        self.assertEqual(result.returncode, 0, result.stderr+result.stdout)
        pidfile = self.root/'runtime/enerex-qa.pid'
        self.assertTrue(pidfile.exists(), 'successful daemon startup must publish PID before returning')
        pid = int(pidfile.read_text())
        self.addCleanup(lambda: os.kill(pid, signal.SIGTERM) if pidfile.exists() else None)
        path = self.root/'runtime/enerex-qa'
        inode = path.stat().st_ino
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.stat().st_ino, inode)
        self.assertEqual(int(pidfile.read_text()), pid)
        os.kill(pid, signal.SIGTERM)
        deadline=time.monotonic()+2
        while path.exists() and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(path.exists())
