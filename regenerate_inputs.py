"""Explicitly reconstruct omitted synthetic inputs without replacing archived evidence."""
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'software'))
from benchmark import prepare
from validation_refinement import prepare as prepare_refinement

for run in ('development_final','heldout','refinement'):
    target=ROOT/'work'/run/'inputs'
    if target.exists(): raise FileExistsError('Existing inputs will not be overwritten: '+run)
for run in ('development_final','heldout','refinement'):
    with tempfile.TemporaryDirectory(prefix='regenerate_',dir=ROOT/'work') as scratch:
        generated=Path(scratch)/'run'
        if run=='development_final': prepare(generated,range(12),False)
        elif run=='heldout': prepare(generated,range(1000,1064),True)
        else: prepare_refinement(generated)
        (generated/'inputs').rename(ROOT/'work'/run/'inputs')
    print('Regenerated synthetic inputs: '+run,flush=True)
