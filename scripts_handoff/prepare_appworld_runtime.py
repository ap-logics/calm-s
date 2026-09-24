"""Prepare an AppWorld Docker context without API credentials or experiment traces."""
import shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
target=ROOT/'calms_data/appworld-runtime'
shutil.copytree(ROOT/'calms_data/external-sources/appworld',target/'appworld',dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('.git','__pycache__','*.pyc','.env'))
shutil.copy2(ROOT/'docker/calms-appworld.Dockerfile',target/'Dockerfile')
shutil.copy2(ROOT/'docker/appworld_smoke.py',target/'appworld_smoke.py')
print(target)
