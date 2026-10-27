import os
from pathlib import Path
import subprocess
import sys


def test_core_runs_from_other_working_directory(tmp_path):
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=str(root))
    code='from services.analysis import load_contract; from reports.render import FONT; from domain.models import KST; assert FONT.is_file(); assert str(KST)=="Asia/Seoul"; print("independent imports OK")'
    run=subprocess.run([sys.executable,'-c',code],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr
    assert 'independent imports OK' in run.stdout
