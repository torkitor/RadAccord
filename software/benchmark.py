"""Generate synthetic inputs, run isolated native extractors, and audit contracts.

The core interpreter needs NumPy and NiBabel. Engine executables are explicit
arguments; neither engine is installed or changed by this program. Output is
JSON/JSONL, suitable for CI and readable without proprietary software.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import numpy as np
from physical_contracts import (Frame,phantom,orbit,transform,write_frame,read_frame,
    transport_witness,analytic_anchors,frame_digest)
from relations import compare_features,check_anchors,schema_check
from adapters import INTENSITY_LAWS


def dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')


def jsonl(path,rows):
    Path(path).write_text(''.join(json.dumps(x,allow_nan=False)+'\n' for x in rows),encoding='utf-8')


def read_jsonl(path):
    return [json.loads(x) for x in Path(path).read_text(encoding='utf-8').splitlines() if x.strip()]


def identity_spec():
    return {'kind':'identity','index_map':np.eye(4).tolist(),'world_map':np.eye(4).tolist(),
            'intensity_gain':1.,'intensity_offset':0.,'parameters':{}}


def prepare(directory,seeds,heldout=False):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if (directory/'cases.jsonl').exists():raise FileExistsError('An existing case manifest will not be overwritten.')
    seeds=list(seeds)
    if heldout:
        if seeds!=list(range(1000,1064)):raise ValueError('The locked held-out protocol requires seeds 1000 through 1063.')
        frozen=json.loads(Path(__file__).with_name('protocol').joinpath('final_freeze.json').read_text(encoding='utf-8'))
        for filename,expected_hash in frozen['sha256'].items():
            actual=hashlib.sha256(Path(__file__).parent.joinpath(filename).read_bytes()).hexdigest()
            if actual!=expected_hash:raise ValueError('The locked protocol or implementation has changed: '+filename)
    cases=[];jobs=[]
    for seed in seeds:
        source=phantom(seed)
        variants=[('reference',source,identity_spec(),'reference',25.)]
        for idx,(perm,signs) in enumerate(orbit()):
            target,spec=transform(source,'reindex',perm=perm,signs=signs)
            variants.append((f'R{idx:02d}',target,spec,'equivalent',25.))
        for name,kind,kwargs in [('encoding','encoding',{'slope':2.,'intercept':-8.}),
               ('label7','label',{'label':7}),('scale_half','scale',{'scale':.5}),
               ('scale_double','scale',{'scale':2.}),
               ('intensity_a','intensity',{'gain':1.5,'offset':7.}),
               ('intensity_b','intensity',{'gain':.5,'offset':-3.})]:
            target,spec=transform(source,kind,**kwargs)
            group='equivalent' if kind in ('encoding','label') else 'covariant'
            variants.append((name,target,spec,group,25.))
        variants.append(('different_bin_width',source,identity_spec(),'not_applicable',50.))
        if heldout:
            from faultinjectors import FAULT_IDS,transform_frame,FaultNotApplicable
            for fault_id in FAULT_IDS:
                intended=replace(source,slope=2.,intercept=-8.)
                try:bad=Frame(**transform_frame(intended.payload(),fault_id))
                except FaultNotApplicable as error:
                    cases.append({'job_id':f'{seed}_{fault_id}','seed':seed,'name':fault_id,'group':'fault',
                                  'activation':'not_applicable','reason':str(error)})
                    continue
                variants.append((fault_id,bad,identity_spec(),'fault',25.))
        for name,frame,spec,group,bw in variants:
            job_id=f'{seed}_{name}'
            started=time.perf_counter()
            try:
                ip,mp=write_frame(frame,directory/'inputs',job_id)
                observed,geometry=read_frame(ip,mp,frame.label)
                witness=transport_witness(source,observed,spec)
            except (ValueError,TypeError,OverflowError) as error:
                cases.append({'job_id':job_id,'seed':seed,'name':name,'group':group,'activation':'applicable',
                              'boundary_error':type(error).__name__,'reason':str(error)})
                continue
            witness_seconds=time.perf_counter()-started
            expected=source if group=='fault' else frame
            case={'job_id':job_id,'seed':seed,'name':name,'group':group,'activation':'applicable',
                'source_digest':frame_digest(source),'observed_digest':frame_digest(observed),
                'changed':not np.array_equal(frame.data,source.data) or not np.array_equal(frame.mask,source.mask)
                    or not np.array_equal(frame.affine,source.affine),
                'spec':spec,'geometry':geometry,'witness':witness,'io_and_witness_seconds':witness_seconds,
                'anchors':analytic_anchors(expected),'settings_equal':bw==25.}
            cases.append(case)
            job={'job_id':job_id,'image_path':ip.relative_to(directory).as_posix(),
                 'mask_path':mp.relative_to(directory).as_posix(),'label':int(frame.label),'bin_width':bw,'spatial_mode':'3d'}
            jobs.append(job)
            if group=='fault':jobs.append(dict(job,job_id=job_id+'_repeat'))
    jsonl(directory/'cases.jsonl',cases);jsonl(directory/'jobs.jsonl',jobs)
    dump(directory/'input_manifest.json',{'seeds':list(seeds),'heldout':heldout,'cases':len(cases),
        'jobs_per_engine':len(jobs),'cases_sha256':hashlib.sha256((directory/'cases.jsonl').read_bytes()).hexdigest()})
    return len(jobs)


def run_engine(directory,engine,executable,workers):
    directory=Path(directory).resolve();jobs=read_jsonl(directory/'jobs.jsonl')
    final=directory/(engine+'.jsonl')
    if final.exists():raise FileExistsError('Existing native outputs will not be overwritten.')
    executable=str(Path(executable).resolve())
    adapter=Path(__file__).with_name('adapters.py')
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',
             ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS='1',NUMBA_NUM_THREADS='1')
    manifest=subprocess.run([executable,str(adapter),'--environment'],capture_output=True,text=True,check=True,env=env)
    dump(directory/(engine+'_environment.json'),json.loads(manifest.stdout))
    tasks=[]
    for i in range(workers):
        shard=directory/f'{engine}_jobs_{i}.jsonl';output=directory/f'{engine}_output_{i}.jsonl'
        jsonl(shard,jobs[i::workers]);tasks.append((shard,output))
    def execute(task):
        shard,output=task
        with (shard.with_suffix('.log')).open('w',encoding='utf-8') as log:
            proc=subprocess.run([executable,str(adapter),'--engine',engine,'--jobs',str(shard),'--output',str(output)],
                                stdout=log,stderr=log,env=env)
        if proc.returncode:raise RuntimeError(f'Worker failed with code {proc.returncode}; inspect private worker log.')
        return read_jsonl(output)
    started=time.perf_counter();rows=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(execute,task) for task in tasks]):
            result=future.result();rows.extend(result)
            print(json.dumps({'engine':engine,'completed':len(rows),'total':len(jobs)}),flush=True)
    if len(rows)!=len(jobs) or len({r['job_id'] for r in rows})!=len(jobs):raise RuntimeError('Incomplete or duplicated output.')
    jsonl(final,sorted(rows,key=lambda x:x['job_id']))
    dump(directory/(engine+'_run.json'),{'wall_seconds':time.perf_counter()-started,'workers':workers,'jobs':len(jobs)})


def evaluate(directory):
    directory=Path(directory);cases=read_jsonl(directory/'cases.jsonl');results=[];diagnostics=[]
    for engine in ('pyradiomics','mirp'):
        native={x['job_id']:x for x in read_jsonl(directory/(engine+'.jsonl'))}
        source_domains={c['seed']:c['anchors'] for c in cases if c['group']=='reference' and 'anchors' in c}
        for case in cases:
            if case['activation']!='applicable':
                results.append({'engine':engine,**case});continue
            if 'boundary_error' in case:
                results.append({'engine':engine,**case,'full_violation':True,'full_decision':'violated'});continue
            row=native[case['job_id']];ref=native[f"{case['seed']}_reference"]
            features=row.get('features',{});reference=ref.get('features',{})
            candidate_schema=schema_check(engine,features,row['settings'].get('bin_width',25.));reference_schema=schema_check(engine,reference)
            domain=source_domains[case['seed']]
            relation=compare_features(engine,reference,features,case['spec'],case['anchors']['n_voxels'],case['settings_equal'],domain)
            anchors=check_anchors(engine,features,case['anchors'])
            # Align the same feature's name for the intentionally unconditional
            # comparator; MIRP encodes bin width in native texture column names.
            naive_features={k.replace('_fbs_w50.0','_fbs_w25.0'):v for k,v in features.items()} if not case['settings_equal'] and engine=='mirp' else features
            naive=compare_features(engine,reference,naive_features,identity_spec(),case['anchors']['n_voxels'],domain=domain)
            repeated=None
            if case['group']=='fault':
                repeat=native[case['job_id']+'_repeat']
                repeated=compare_features(engine,features,repeat.get('features',{}),identity_spec(),case['anchors']['n_voxels'],domain=domain)
            fail=row['status']!='extracted' or bool(row.get('nonfinite_features'))
            reference_failure=ref['status']!='extracted' or bool(ref.get('nonfinite_features'))
            schema_failure=candidate_schema['status']!='satisfied' or reference_schema['status']!='satisfied'
            result={k:case[k] for k in ('job_id','seed','name','group','activation','changed','witness','geometry','io_and_witness_seconds')}
            result.update(engine=engine,native_failure=fail,reference_failure=reference_failure,schema_failure=schema_failure,native_seconds=row['seconds'],
                warning_count=len(row['warnings']),relation=relation['status'],relation_counts=relation['counts'],
                anchors=anchors['status'],naive_invariance=naive['status'],repeat=None if repeated is None else repeated['status'],
                full_violation=fail or reference_failure or schema_failure or not all(case['geometry'].values()) or case['witness']['status']=='violated'
                    or relation['status']=='violated' or anchors['status']=='violated')
            result['full_decision']='violated' if result['full_violation'] else (
                'no_violations_with_abstentions' if relation['counts'].get('not_applicable',0) else 'satisfied')
            if reference_failure or reference_schema['status']!='satisfied':
                result.update(full_decision='unavailable',full_violation=None,relation='not_applicable',
                              naive_invariance='not_applicable',reason='usable reference extraction is unavailable')
            results.append(result)
            diagnostics.append({'job_id':case['job_id'],'engine':engine,'relation':relation,'anchors':anchors,
                                'naive':naive,'repeat':repeated,'candidate_schema':candidate_schema,'reference_schema':reference_schema})
    jsonl(directory/'decisions.jsonl',results);jsonl(directory/'feature_diagnostics.jsonl',diagnostics)
    summary={}
    for engine in ('pyradiomics','mirp'):
        selected=[r for r in results if r['engine']==engine]
        summary[engine]={}
        for group in sorted({r['group'] for r in selected}):
            attempted=[r for r in selected if r['group']==group]
            active=[r for r in attempted if r['activation']=='applicable']
            rows=[r for r in active if 'boundary_error' not in r]
            summary[engine][group]={'attempted':len(attempted),'applicable':len(active),
                'not_applicable':len(attempted)-len(active),'boundary_errors':len(active)-len(rows),
                'cases':len(rows),'native_failures':sum(r['native_failure'] for r in rows),
                'reference_unavailable':sum(r['full_decision']=='unavailable' for r in rows),
                'schema_failures':sum(r['schema_failure'] for r in rows),
                'witness_violations':sum(r['witness']['status']=='violated' for r in rows),
                'relation_violations':sum(r['relation']=='violated' for r in rows),
                'anchor_violations':sum(r['anchors']=='violated' for r in rows),
                'naive_invariance_violations':sum(r['naive_invariance']=='violated' for r in rows),
                'full_violations':sum(bool(r['full_violation']) for r in rows)+len(active)-len(rows)}
    dump(directory/'summary.json',summary);return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('directory',type=Path);prep.add_argument('--first',type=int,default=0)
    prep.add_argument('--count',type=int,default=12);prep.add_argument('--heldout',action='store_true')
    run=sub.add_parser('run');run.add_argument('directory',type=Path);run.add_argument('--engine',required=True,choices=['pyradiomics','mirp'])
    run.add_argument('--python',required=True,type=Path);run.add_argument('--workers',type=int,default=6)
    ev=sub.add_parser('evaluate');ev.add_argument('directory',type=Path)
    a=p.parse_args()
    if a.command=='prepare':print(prepare(a.directory,range(a.first,a.first+a.count),a.heldout))
    elif a.command=='run':run_engine(a.directory,a.engine,a.python,a.workers)
    else:print(json.dumps(evaluate(a.directory),indent=2))
