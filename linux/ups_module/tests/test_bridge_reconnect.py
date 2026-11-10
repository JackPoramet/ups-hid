"""Reconnect after a USB read error without touching real hardware."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import enerex_ups_bridge as bridge

class ReconnectTests(unittest.TestCase):
    def test_bridge_cleans_up_old_session_and_scans_again(self):
        first=Mock(profile=None,device_info={"product_string":"fake"})
        first.get_vars.side_effect=[{"ups.status":"OL"},RuntimeError("USB removed")]
        second=Mock(profile=None,device_info={"product_string":"fake"})
        def recovered():
            bridge._running=False
            return {"ups.status":"OL"}
        second.get_vars.side_effect=recovered
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(bridge,'_running',True), patch.object(bridge,'DUMMY_FILE',str(Path(tmp)/'myups.dev')), patch.object(bridge,'acquire_single_instance_lock'), patch.object(bridge,'is_enerex_driver_active',return_value=True), patch.object(bridge,'HardwareSession',side_effect=[first,second]) as factory, patch.object(bridge,'check_and_execute_commands'), patch.object(bridge,'set_nut_driver_state'), patch.object(bridge.time,'sleep'), patch('subprocess.run',return_value=SimpleNamespace(returncode=0)):
                bridge.main()
                self.assertEqual(factory.call_count,2)
                first.disconnect.assert_called_once()
                second.connect.assert_called_once()

if __name__=='__main__':unittest.main()
