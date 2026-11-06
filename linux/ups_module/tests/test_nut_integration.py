"""Isolated real upsd clients, private sockets, and a fake hardware executor."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest


def _isolated_daemon(executable, root, role):
    # NUT2.7 ignores PID-path env overrides, but derives PID names from argv[0].
    source=Path(executable).resolve()
    if source.read_bytes()[:4]!=b'\x7fELF':
        candidates=(source.parent.parent/'lib/nut'/source.name,
                    Path('/lib/nut')/source.name,Path('/usr/lib/nut')/source.name)
        source=next((p for p in candidates if p.is_file() and p.read_bytes()[:4]==b'\x7fELF'),None)
        if source is None:
            raise unittest.SkipTest('No standalone NUT daemon binary for safe PID isolation')
    target=root/('enerex-qa-'+role+'-'+root.name)
    shutil.copyfile(source,target)
    target.chmod(0o700)
    return str(target)


def _remove_qa_pid(executable, pid):
    name=Path(executable).name
    if not name.startswith('enerex-qa-'):
        raise AssertionError('Refusing non-QA PID cleanup')
    for directory in ('/run','/run/nut','/var/run','/var/run/nut'):
        path=Path(directory)/(name+'.pid')
        try:
            if path.read_text().strip()==str(pid):path.unlink()
        except FileNotFoundError:
            pass


@unittest.skipUnless(os.name == 'posix', 'Real NUT integration requires Linux')
class TestNativeNutIntegration(unittest.TestCase):
    def test_qa_copy_does_not_follow_a_distribution_wrapper_back_to_live_pid_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'sbin').mkdir();(root/'lib/nut').mkdir(parents=True)
            wrapper=root/'sbin/upsd'
            wrapper.write_text('#!/bin/sh\nexec /lib/nut/upsd "$@"\n')
            executable=root/'lib/nut/upsd'
            executable.write_bytes(b'\x7fELFfake-native-test-fixture')
            copied=Path(_isolated_daemon(wrapper,root,'server'))
            self.assertEqual(copied.read_bytes(),executable.read_bytes())

    def test_notification_policy_stays_running_on_low_battery_without_shutdown(self):
        from ups_module.nut_config import configure_notification_monitor
        from ups_module.nut_driver import DriverServer
        upsd=os.environ.get('ENEREX_QA_UPSD') or shutil.which('upsd')
        upsmon=os.environ.get('ENEREX_QA_UPSMON') or shutil.which('upsmon')
        if not upsd or not upsmon:self.skipTest('Isolated upsd/upsmon executables unavailable')
        import pwd
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);conf=root/'etc/nut';conf.mkdir(parents=True)
            upsd=_isolated_daemon(upsd,root,'server')
            upsmon=_isolated_daemon(upsmon,root,'monitor')
            with socket.socket() as reserve:
                reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
            (conf/'upsd.conf').write_text(f'LISTEN 127.0.0.1 {port}\nSTATEPATH {root}\n')
            (conf/'ups.conf').write_text(f'[qa]\ndriver = enerex\nport = {root}/state.dev\n')
            (conf/'upsd.users').write_text('')
            (conf/'upsmon.conf').write_text('MINSUPPLIES 1\nSHUTDOWNCMD "/bin/false"\n')
            configure_notification_monitor(root,'qa',owner_group=None)
            monitor=(conf/'upsmon.conf').read_text()
            marker=root/'unexpected-shutdown'
            # A policy failure can only create a temporary marker, never shut down the host.
            monitor=monitor.replace('qa@localhost',f'qa@127.0.0.1:{port}')
            monitor=monitor.replace('SHUTDOWNCMD "/bin/false"',f'SHUTDOWNCMD "/usr/bin/touch {marker}"')
            monitor+='POLLFREQ 1\nPOLLFREQALERT 1\nDEADTIME 5\n'
            for event in ('ONLINE','ONBATT','LOWBATT','FSD','COMMOK','COMMBAD','SHUTDOWN','NOCOMM'):
                monitor+=f'NOTIFYFLAG {event} IGNORE\n'
            (conf/'upsmon.conf').write_text(monitor)
            state=root/'state.dev';state.write_text('ups.status: OL\n')
            driver=DriverServer(root/'enerex-qa',state,root/'fake.sock')
            driver.start();stopped=threading.Event()
            def serve():
                while not stopped.is_set():driver.step(.02)
            thread=threading.Thread(target=serve,daemon=True);thread.start()
            env=dict(os.environ,NUT_CONFPATH=str(conf),NUT_STATEPATH=str(root),NUT_ALTPIDPATH=str(root),NUT_PIDPATH=str(root))
            user=pwd.getpwuid(os.getuid()).pw_name
            server=monitor_process=None
            log=(root/'upsmon.log').open('w+')
            serverlog=(root/'upsd.log').open('w+')
            try:
                server=subprocess.Popen([upsd,'-D','-u',user],env=env,stdout=serverlog,stderr=subprocess.STDOUT)
                deadline=time.monotonic()+5
                while True:
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                    except OSError:
                        if time.monotonic()>deadline:self.fail('Isolated upsd did not listen')
                        time.sleep(.05)
                monitor_process=subprocess.Popen([upsmon,'-D','-p','-u',user],env=env,stdout=log,stderr=subprocess.STDOUT)
                deadline=time.monotonic()+5
                while True:
                    with socket.create_connection(('127.0.0.1',port),timeout=1) as client:
                        client.sendall(b'GET NUMLOGINS qa\n');response=client.recv(4096)
                    if b'NUMLOGINS qa 1' in response:break
                    if monitor_process.poll() is not None or time.monotonic()>deadline:
                        log.flush();log.seek(0);self.fail('Notify monitor did not login: '+log.read())
                    time.sleep(.1)
                state.write_text('ups.status: OB LB\n')
                for _ in range(15):
                    time.sleep(.2)
                    os.utime(state,None)
                    self.assertIsNone(monitor_process.poll())
                    self.assertFalse(marker.exists(),'Independently powered monitor attempted shutdown')
            finally:
                for process in (monitor_process,server):
                    if process is None:continue
                    process.terminate()
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
                if monitor_process is not None:_remove_qa_pid(upsmon,monitor_process.pid)
                if server is not None:_remove_qa_pid(upsd,server.pid)
                stopped.set();thread.join(timeout=1);driver.close();log.close();serverlog.close()

    def test_native_clients_read_list_authenticate_and_route_to_fake_hardware(self):
        from ups_module.nut_driver import DriverServer
        from ups_module.command_broker import CommandBroker
        upsd = os.environ.get('ENEREX_QA_UPSD') or shutil.which('upsd')
        upsc = os.environ.get('ENEREX_QA_UPSC') or shutil.which('upsc')
        upscmd = os.environ.get('ENEREX_QA_UPSCMD') or shutil.which('upscmd')
        if not all((upsd, upsc, upscmd)):
            self.skipTest('Isolated upsd/upsc/upscmd executables unavailable')
        import pwd
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            upsd=_isolated_daemon(upsd,root,'server')
            with socket.socket() as reserve:
                reserve.bind(('127.0.0.1',0))
                port = reserve.getsockname()[1]
            (root/'ups.conf').write_text('[qa]\ndriver = enerex\nport = '+str(root/'state.dev')+'\n')
            (root/'upsd.conf').write_text(f'LISTEN 127.0.0.1 {port}\nSTATEPATH {root}\n')
            (root/'upsd.users').write_text('[qa-command]\npassword = fixture-secret\ninstcmds = test.battery.stop\n')
            state = root/'state.dev'
            state.write_text('ups.status: OL\ninput.voltage: 230\ncmd.test.battery.stop: 1\n')
            effects = []
            def execute(command):
                effects.append(command)
                return True, 'fake USB write'
            broker=CommandBroker(root/'commands.sock',owner_group=None)
            broker.start();broker.set_connected(True)
            driver = DriverServer(root/'enerex-qa',state,root/'commands.sock')
            driver.start()
            stopped = threading.Event()
            def serve():
                while not stopped.is_set():
                    driver.step(.02)
                    broker.execute_pending(execute)
            thread = threading.Thread(target=serve,daemon=True)
            thread.start()
            env=dict(os.environ,NUT_CONFPATH=str(root),NUT_STATEPATH=str(root),
                     NUT_ALTPIDPATH=str(root),NUT_PIDPATH=str(root))
            endpoint=f'qa@127.0.0.1:{port}'
            log = (root/'upsd.log').open('w+')
            server = None
            try:
                server = subprocess.Popen([upsd,'-D','-u',pwd.getpwuid(os.getuid()).pw_name],env=env,
                                          stdout=log,stderr=subprocess.STDOUT)
                deadline=time.monotonic()+6
                while True:
                    read=subprocess.run([upsc,endpoint],env=env,text=True,capture_output=True,timeout=2)
                    if read.returncode==0:break
                    if time.monotonic()>=deadline:
                        log.flush();log.seek(0)
                        self.fail(read.stderr+'\n'+log.read())
                    time.sleep(.1)
                self.assertIn('ups.status: OL',read.stdout)
                self.assertIn('input.voltage: 230',read.stdout)
                listed=subprocess.run([upscmd,'-l',endpoint],env=env,text=True,capture_output=True,timeout=3)
                self.assertEqual(listed.returncode,0,listed.stderr)
                self.assertIn('test.battery.stop',listed.stdout)
                denied=subprocess.run([upscmd,'-u','qa-command','-p','wrong',endpoint,'test.battery.stop'],env=env,text=True,capture_output=True,timeout=3)
                self.assertNotEqual(denied.returncode,0)
                self.assertEqual(effects,[])
                accepted=subprocess.run([upscmd,'-u','qa-command','-p','fixture-secret',endpoint,'test.battery.stop'],env=env,text=True,capture_output=True,timeout=3)
                self.assertEqual(accepted.returncode,0,accepted.stderr)
                deadline=time.monotonic()+2
                while not effects and time.monotonic()<deadline:time.sleep(.02)
                self.assertEqual(effects,['test.battery.stop'])
                os.utime(state,(time.time()-10,time.time()-10))
                deadline=time.monotonic()+2
                while True:
                    stale=subprocess.run([upsc,endpoint],env=env,text=True,capture_output=True,timeout=2)
                    if stale.returncode!=0:break
                    if time.monotonic()>=deadline:self.fail('Stale snapshot still served as fresh')
                    time.sleep(.05)
                self.assertIn('stale',stale.stderr.lower())
            finally:
                if server is not None:
                    server.terminate()
                    try:server.wait(timeout=3)
                    except subprocess.TimeoutExpired:server.kill();server.wait(timeout=3)
                    _remove_qa_pid(upsd,server.pid)
                stopped.set();thread.join(timeout=1);driver.close();broker.close();log.close()
