"""Separate source worktrees can share explicit local artifact roots without copies."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

class SharedStorageTests(unittest.TestCase):
    def test_explicit_runs_root_reaches_scoring_and_saved_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=dict(os.environ,CW_RUNS_DIR=tmp)
            code="from cancer_workbench.common.paths import RUNS_DIR; from cancer_workbench.experiments import explore; from cancer_workbench.research import runtime; import json; print(json.dumps([str(RUNS_DIR),str(explore.RUNS_DIR),str(runtime.RESULTS)]))"
            result=subprocess.run([sys.executable,'-B','-c',code],env=env,capture_output=True,text=True,check=True)
            paths=json.loads(result.stdout)
            self.assertEqual(paths,[str(Path(tmp)),str(Path(tmp)),str(Path(tmp)/'observations')])
    def test_default_runs_root_remains_project_local(self):
        env=dict(os.environ);env.pop('CW_RUNS_DIR',None)
        code="from cancer_workbench.common.paths import RUNS_DIR,PROJECT_ROOT; assert RUNS_DIR == PROJECT_ROOT/'runs'"
        subprocess.run([sys.executable,'-B','-c',code],env=env,check=True,capture_output=True,text=True)
if __name__=='__main__':unittest.main()
