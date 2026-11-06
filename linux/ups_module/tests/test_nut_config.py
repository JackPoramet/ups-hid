"""Monitor provisioning operates only on temporary NUT configuration."""
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))


class TestNutConfig(unittest.TestCase):
    def setUp(self):
        from ups_module.nut_config import configure_notification_monitor, remove_notification_monitor
        self.configure = configure_notification_monitor
        self.remove = remove_notification_monitor
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.conf = self.root/'etc/nut'
        self.conf.mkdir(parents=True)
        self.original_monitor = '# keep comment\nMINSUPPLIES 1\nSHUTDOWNCMD "/sbin/shutdown -h now"\nPOWERDOWNFLAG /etc/killpower\n'
        self.original_users = '[other]\npassword = fixture-other\ninstcmds = ALL\n'
        (self.conf/'upsmon.conf').write_text(self.original_monitor)
        (self.conf/'upsd.users').write_text(self.original_users)

    def test_notify_only_values_preserve_users_and_secret_across_rerun(self):
        self.assertTrue(self.configure(self.root,'myups',owner_group=None))
        monitor=(self.conf/'upsmon.conf').read_text()
        users=(self.conf/'upsd.users').read_text()
        active=[s.strip() for s in monitor.splitlines() if s.strip() and not s.lstrip().startswith('#')]
        self.assertIn('MINSUPPLIES 0',active)
        self.assertIn('SHUTDOWNCMD "/bin/false"',active)
        self.assertFalse(any(s.startswith('POWERDOWNFLAG') for s in active))
        line=next(s for s in active if s.startswith('MONITOR '))
        self.assertEqual(line.split()[:4],['MONITOR','myups@localhost','0','enerex-monitor'])
        self.assertEqual(line.split()[-1],'slave')
        secret=line.split()[4]
        self.assertGreaterEqual(len(secret),32)
        self.assertIn('password = '+secret,users)
        self.assertTrue(users.startswith(self.original_users))
        self.assertFalse(self.configure(self.root,'myups',owner_group=None))
        self.assertEqual((self.conf/'upsmon.conf').read_text(),monitor)
        self.assertEqual((self.conf/'upsd.users').read_text(),users)

    def test_foreign_monitor_or_user_rejected_before_either_file_changes(self):
        for foreign in ('MONITOR other@host 1 foreign fixture master\n',''):
            with self.subTest(foreign=bool(foreign)):
                (self.conf/'upsmon.conf').write_text(self.original_monitor+foreign)
                (self.conf/'upsd.users').write_text(self.original_users+('' if foreign else '[enerex-monitor]\npassword = foreign\n'))
                before={p.name:p.read_bytes() for p in self.conf.iterdir()}
                with self.assertRaises(ValueError):self.configure(self.root,'myups',owner_group=None)
                self.assertEqual({p.name:p.read_bytes() for p in self.conf.iterdir()},before)

    def test_commented_or_quoted_existing_monitor_account_is_not_overwritten(self):
        for header in ('[enerex-monitor] # site account','["enerex-monitor"]'):
            with self.subTest(header=header):
                users=self.original_users+header+'\npassword = fixture-existing\n'
                (self.conf/'upsd.users').write_text(users)
                with self.assertRaises(ValueError):self.configure(self.root,'myups',owner_group=None)
                self.assertEqual((self.conf/'upsd.users').read_text(),users)
                self.assertEqual((self.conf/'upsmon.conf').read_text(),self.original_monitor)

    def test_remove_owned_monitor_restores_original_directives_and_preserves_new_user(self):
        self.configure(self.root,'myups',owner_group=None)
        with (self.conf/'upsd.users').open('a') as stream:stream.write('[later]\npassword = fixture-later\n')
        self.remove(self.root,owner_group=None)
        self.assertEqual((self.conf/'upsmon.conf').read_text(),self.original_monitor)
        self.assertEqual((self.conf/'upsd.users').read_text(),self.original_users+'[later]\npassword = fixture-later\n')

    def test_preflight_rejects_native_multiple_and_wrong_snapshot_without_changes(self):
        from ups_module.nut_config import bridge_ups_name
        config=self.conf/'ups.conf'
        for text in ('[one]\ndriver=usbhid-ups\nport=auto\n',
                     '[one]\ndriver=dummy-ups\nport=/etc/nut/myups.dev\n',
                     '[one]\ndriver=enerex\nport=/etc/nut/myups.dev\n[two]\ndriver=enerex\n',
                     '[one]\ndriver=enerex\nport=/unrelated.dev\n'):
            with self.subTest(text=text):
                config.write_text(text)
                with self.assertRaises(ValueError):bridge_ups_name(self.root)
        config.write_text('[myups]\ndriver=enerex\nport=/etc/nut/myups.dev\n')
        self.assertEqual(bridge_ups_name(self.root),'myups')

    def test_original_service_enablement_is_recorded_once_for_uninstall(self):
        from ups_module.nut_config import record_monitor_service_state, original_monitor_service_state
        record_monitor_service_state(self.root,'disabled')
        record_monitor_service_state(self.root,'enabled')
        self.assertEqual(original_monitor_service_state(self.root),'disabled')
        with self.assertRaises(ValueError):record_monitor_service_state(self.root,'masked')

    def test_existing_executable_notification_hooks_require_explicit_review(self):
        path=self.conf/'upsmon.conf'
        text=self.original_monitor+'NOTIFYCMD /custom/power-handler\nNOTIFYFLAG LOWBATT SYSLOG+EXEC\n'
        path.write_text(text)
        with self.assertRaises(ValueError):self.configure(self.root,'myups',owner_group=None)
        self.assertEqual(path.read_text(),text)
        self.assertEqual((self.conf/'upsd.users').read_text(),self.original_users)
