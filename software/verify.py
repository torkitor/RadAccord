"""Verify a declared radiomics input transformation at a file boundary.

Example: python verify.py --source-image source_image.nii.gz --source-mask
source_mask.nii.gz --candidate-image target_image.nii.gz --candidate-mask
target_mask.nii.gz --contract contract.json --engine pyradiomics
--engine-python /path/to/python --report report.json

The source and contract must be trusted. This command verifies declared input
correspondence and selected output obligations, not clinical validity or all
internal states of an extraction library. No patient data are transmitted.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import json
import subprocess
import sys
import time
import numpy as np
from physical_contracts import read_frame,transport_witness,analytic_anchors,Frame
from relations import compare_features,check_anchors,schema_check
from benchmark import dump,jsonl,read_jsonl


def verify(source_image,source_mask,candidate_image,candidate_mask,contract,engine,engine_python):
    started=time.perf_counter();spec=contract['transformation']
    source,source_geometry=read_frame(source_image,source_mask,contract.get('source_label',1))
    observed,geometry=read_frame(candidate_image,candidate_mask,contract.get('candidate_label',1))
    witness=transport_witness(source,observed,spec)
    settings=contract.get('settings',{'bin_width':25.,'spatial_mode':'3d'})
    candidate_settings=contract.get('candidate_settings',settings)
    # Analytic anchors do not need a materialized transformed grid: bijective
    # reindexing/relabeling leaves the ROI multiset and count unchanged.
    world=np.asarray(spec['world_map'],float)
    expected=Frame(source.data*spec['intensity_gain']+spec['intensity_offset'],source.mask,
                   world@source.affine,source.label).validate()
    anchors=analytic_anchors(expected)
    with TemporaryDirectory(prefix='radiomics_contract_') as temporary:
        temp=Path(temporary);jobs=[]
        for name,ip,mp,label,configuration in (
          ('source',source_image,source_mask,source.label,settings),
          ('candidate',candidate_image,candidate_mask,observed.label,candidate_settings)):
            jobs.append({'job_id':name,'image_path':str(Path(ip).resolve()),'mask_path':str(Path(mp).resolve()),
                         'label':label,**configuration})
        jsonl(temp/'jobs.jsonl',jobs)
        with (temp/'worker.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([str(engine_python),str(Path(__file__).with_name('adapters.py')),
                '--engine',engine,'--jobs',str(temp/'jobs.jsonl'),'--output',str(temp/'outputs.jsonl')],
                stdout=log,stderr=log)
        if result.returncode:raise RuntimeError('The native feature worker failed; no verification result is available.')
        rows={r['job_id']:r for r in read_jsonl(temp/'outputs.jsonl')}
    ref=rows['source'];candidate=rows['candidate']
    relation=compare_features(engine,ref.get('features',{}),candidate.get('features',{}),spec,
                              anchors['n_voxels'],settings==candidate_settings,analytic_anchors(source))
    anchor_result=check_anchors(engine,candidate.get('features',{}),anchors)
    schemas={key:schema_check(engine,row.get('features',{}),row['settings'].get('bin_width',25.)) for key,row in rows.items()}
    native_failure=any(r['status']!='extracted' or r.get('nonfinite_features') for r in rows.values())
    violation=native_failure or any(x['status']=='violated' for x in schemas.values()) or not all(source_geometry.values()) or not all(geometry.values()) or any(
        r['status']=='violated' for r in (witness,relation,anchor_result))
    outside=witness['status']=='not_applicable' or relation['status']=='not_applicable' or any(x['status']=='unavailable' for x in schemas.values())
    decision='violated' if violation else ('not_applicable' if outside else 'applicable_obligations_satisfied')
    return {'schema_version':'1.0','engine':engine,'decision':decision,
        'source_geometry':source_geometry,'candidate_geometry':geometry,'witness':witness,
        'relations':relation,'anchors':anchor_result,'schemas':schemas,'native':rows,'seconds':time.perf_counter()-started,
        'scope':'Trusted source and manifest; orthogonal millimetre NIfTI; unfiltered native 3D extraction. '
                'Unassigned relations are abstentions, not passed checks. Internal extractor states and clinical validity are not certified.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source-image','source-mask','candidate-image','candidate-mask','contract','engine-python','report'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--engine',choices=('pyradiomics','mirp'),required=True);a=p.parse_args()
    try:
        report=verify(a.source_image,a.source_mask,a.candidate_image,a.candidate_mask,
                      json.loads(a.contract.read_text(encoding='utf-8')),a.engine,a.engine_python)
        dump(a.report,report);print(report['decision']);sys.exit(1 if report['decision']=='violated' else 2 if report['decision']=='not_applicable' else 0)
    except Exception as error:
        # Do not publish exception text: parsers may include private input paths.
        dump(a.report,{'decision':'unavailable','error_type':type(error).__name__,
                      'reason':'Input or contract is outside the supported domain, or extraction was unavailable.'})
        print('unavailable');sys.exit(2)
