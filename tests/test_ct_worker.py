"""Actual worker-lifetime subprocess checks, without loading any model."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


class CTWorkerLifetimeTests(unittest.TestCase):
    def test_independent_deadline_ends_a_busy_worker(self):
        code='from cancer_workbench.research.ct_worker import start_guard;import os,time;start_guard(os.getppid(),.3);time.sleep(20)'
        proc=subprocess.Popen([sys.executable,'-B','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            out,err=proc.communicate(timeout=8)
            self.assertEqual(proc.returncode,124,(out,err))
        finally:
            if proc.poll() is None:proc.kill();proc.wait()

    def test_owner_exit_ends_its_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready=Path(tmp)/'ready'
            child="from cancer_workbench.research.ct_worker import start_guard;import sys,time;from pathlib import Path;start_guard(int(sys.argv[1]),20);Path("+repr(str(ready))+").write_text('ready');time.sleep(30)"
            owner="import os,subprocess,sys,time;p=subprocess.Popen([sys.executable,'-B','-c',"+repr(child)+",str(os.getpid())]);time.sleep(30)"
            proc=subprocess.Popen([sys.executable,'-B','-c',owner],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+8
                while not ready.is_file() and time.monotonic()<deadline:time.sleep(.05)
                self.assertTrue(ready.is_file(),'worker did not establish its owner guard')
                proc.kill()
                # Inherited output handles close only when the owner and its child exit.
                proc.communicate(timeout=8)
            finally:
                if proc.poll() is None:proc.kill();proc.wait()


if __name__=='__main__':unittest.main()
