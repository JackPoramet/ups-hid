"""Check terminal colors and clean logs without touching installed services."""
import os
import pty
import subprocess
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[2] / 'terminal-output.sh'

class TerminalOutputTests(unittest.TestCase):
    def run_helper(self, message, *, tty=False, no_color=False, term='xterm'):
        env = dict(os.environ, TERM=term)
        env.pop('NO_COLOR', None)
        if no_color: env['NO_COLOR'] = '1'
        cmd=['bash','-c','source "$1"; '+message,'test',str(HELPER)]
        if not tty:
            return subprocess.run(cmd, env=env, capture_output=True)
        master,slave=pty.openpty()
        try:
            proc=subprocess.Popen(cmd, env=env, stdout=slave, stderr=slave)
            os.close(slave); slave=None
            out=b''
            while True:
                try: chunk=os.read(master,4096)
                except OSError: break
                if not chunk: break
                out+=chunk
            return subprocess.CompletedProcess(cmd,proc.wait(),out,b'')
        finally:
            os.close(master)
            if slave is not None: os.close(slave)

    def test_color_on_terminal(self):
        r=self.run_helper('ui_ok "ready"',tty=True)
        self.assertEqual(r.returncode,0)
        self.assertIn(b'\x1b[32m',r.stdout)
        self.assertIn(b'[OK] ready',r.stdout)

    def test_no_escape_codes_when_redirected(self):
        r=self.run_helper('ui_ok "ready"; ui_error "failed"')
        self.assertEqual(r.returncode,0)
        self.assertNotIn(b'\x1b[',r.stdout+r.stderr)
        self.assertIn(b'[OK] ready',r.stdout)
        self.assertIn(b'[ERROR] failed',r.stderr)

    def test_no_color_environment_and_dumb_terminal(self):
        for options in ({'no_color':True},{'term':'dumb'}):
            with self.subTest(**options):
                r=self.run_helper('ui_warn "waiting"',tty=True,**options)
                self.assertEqual(r.returncode,0)
                self.assertNotIn(b'\x1b[',r.stdout)
                self.assertIn(b'[WARN] waiting',r.stdout)

if __name__ == '__main__': unittest.main()
