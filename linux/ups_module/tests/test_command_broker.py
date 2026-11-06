"""Native commands use real isolated Unix sockets and fake hardware effects."""
import concurrent.futures
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest


@unittest.skipUnless(os.name == "posix", "Linux Unix-socket command broker")
class TestCommandBroker(unittest.TestCase):
    def setUp(self):
        from ups_module.command_broker import CommandBroker, submit_command
        self.submit = submit_command
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name)/"commands.sock")
        self.broker = CommandBroker(self.path, owner_group=None)
        self.broker.start()
        self.addCleanup(self.broker.close)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        self.addCleanup(self.pool.shutdown)

    def wait_pending(self, count=1):
        deadline = time.monotonic()+2
        while self.broker.pending_count < count and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertEqual(self.broker.pending_count, count)

    def test_unknown_and_disconnected_commands_never_reach_executor(self):
        self.assertFalse(self.submit(self.path, "load.off")["ok"])
        self.assertFalse(self.submit(self.path, "test.battery.start.quick")["ok"])
        self.assertEqual(self.broker.pending_count, 0)

    def test_two_simultaneous_commands_are_executed_once_without_overwrite(self):
        self.broker.set_connected(True)
        first = self.pool.submit(self.submit, self.path, "test.battery.start.quick")
        second = self.pool.submit(self.submit, self.path, "test.battery.stop")
        self.wait_pending(2)
        effects = []
        def execute(command):
            effects.append(command)
            return True, "transport accepted"
        self.broker.execute_pending(execute)
        self.assertTrue(first.result(timeout=2)["ok"])
        self.assertTrue(second.result(timeout=2)["ok"])
        self.assertCountEqual(effects, ["test.battery.start.quick", "test.battery.stop"])
        self.broker.execute_pending(execute)
        self.assertEqual(len(effects), 2)

    def test_expired_request_and_disconnected_queue_are_not_replayed(self):
        self.broker.set_connected(True)
        expired = self.pool.submit(self.submit, self.path, "test.battery.stop", timeout=.08)
        self.wait_pending()
        self.assertFalse(expired.result(timeout=2)["ok"])
        effects = []
        self.broker.execute_pending(lambda command: effects.append(command))
        self.assertEqual(effects, [])
        pending = self.pool.submit(self.submit, self.path, "test.battery.stop")
        self.wait_pending()
        self.broker.set_connected(False)
        self.assertFalse(pending.result(timeout=2)["ok"])
        self.broker.set_connected(True)
        self.broker.execute_pending(lambda command: effects.append(command))
        self.assertEqual(effects, [])

    def test_oversized_request_rejected_and_socket_removed_on_stop(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(self.path)
            client.sendall(b'x'*4097+b'\n')
            result = json.loads(client.makefile('rb').readline())
            self.assertFalse(result["ok"])
        self.assertEqual(self.broker.pending_count, 0)
        self.broker.close()
        self.assertFalse(Path(self.path).exists())

    def test_peer_disconnect_before_dispatch_cancels_without_polling_grace(self):
        self.broker.set_connected(True)
        client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        client.connect(self.path)
        client.sendall(b'{"command":"test.battery.stop","timeout":5}\n')
        self.wait_pending()
        client.close()
        effects=[]
        self.broker.execute_pending(lambda command:(effects.append(command) or True,'fake USB write'))
        self.assertEqual(effects,[])
