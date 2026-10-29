import os
from pathlib import Path
import subprocess
import sys


def test_core_runs_from_other_working_directory(tmp_path):
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,PYTHONPATH=str(root))
    code='from services.analysis import load_contract; from reports.render import FONT; from domain.models import KST; from config.airport_codes import icao_to_iata; from config.airline_codes import parse_icao_codes, flight_label; assert parse_icao_codes("zzz")==("ZZZ",); assert flight_label("XUM001F")=="XU001F"; assert icao_to_iata("ZSJN")=="TNA"; assert FONT.is_file(); assert str(KST)=="Asia/Seoul"; print("independent imports OK")'
    run=subprocess.run([sys.executable,'-c',code],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=30)
    assert run.returncode==0,run.stderr
    assert 'independent imports OK' in run.stdout
