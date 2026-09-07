"""Prospectively fixed follow-up of the original profile's mesh alerts.

Original software, frozen protocol, measurements and decisions are retained.
The revised profile withholds four PyRadiomics mesh-derived reindexing laws;
it does not change values, tolerances, anchors or physical correspondence.
"""
from dataclasses import replace
from pathlib import Path
from copy import deepcopy
import argparse,hashlib,json,time
import numpy as np
from physical_contracts import (Frame,phantom,orbit,transform,write_frame,read_frame,
    transport_witness,analytic_anchors,frame_digest)
from benchmark import identity_spec,jsonl,read_jsonl,dump
from relations import compare_features,check_anchors,schema_check,summarize
from faultinjectors import FAULT_IDS,transform_frame,FaultNotApplicable

WITHHELD_MESH=('original_shape_MeshVolume','original_shape_SurfaceArea',
              'original_shape_SurfaceVolumeRatio','original_shape_Sphericity')


def revise_relation(relation,engine,kind):
    revised=deepcopy(relation)
    if engine=='pyradiomics' and kind=='reindex':
        for key in WITHHELD_MESH:
            if key in revised['features']:
                old=revised['features'][key]
                revised['features'][key]={'status':'not_applicable',
                    'reason':'mesh-derived equivalence is not assigned in the revised reindexing profile',
                    'initial_obligation':old}
        revised=summarize(revised['features'])
    return revised


def revised_report(report,kind):
    r=deepcopy(report);r['initial_relations']=r['relations']
    r['relations']=revise_relation(r['relations'],r['engine'],kind);r['profile']='revised_mesh_scope'
    native_bad=any(x['status']!='extracted' or x.get('nonfinite_features') for x in r['native'].values())
    violation=native_bad or any(x['status']=='violated' for x in r['schemas'].values()) or not all(r['source_geometry'].values()) or not all(r['candidate_geometry'].values()) or any(x['status']=='violated' for x in (r['witness'],r['relations'],r['anchors']))
    outside=any(x['status']=='unavailable' for x in r['schemas'].values()) or r['witness']['status']=='not_applicable' or r['relations']['status']=='not_applicable'
    r['decision']='violated' if violation else 'not_applicable' if outside else 'applicable_obligations_satisfied'
    return r


def refinement_phantom(seed):
    f=phantom(seed)
    if seed%2:
        # Enriched stress fixtures, fixed before the follow-up outcomes:
        # two diagonal selected samples on a background 2x2 face.
        mask=f.mask.copy()
        if np.any(mask[1:3,1:3,1:3]):raise ValueError('The declared enrichment patch is not background.')
        mask[1,1,1]=1;mask[2,2,1]=1
        f=replace(f,mask=mask)
    return f.validate()


def prepare(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if (directory/'cases.jsonl').exists():raise FileExistsError('Existing follow-up inputs will not be overwritten.')
    frozen=json.loads(Path(__file__).with_name('protocol').joinpath('refinement_freeze.json').read_text())
    for name,value in frozen['sha256'].items():
        if hashlib.sha256(Path(__file__).parent.joinpath(name).read_bytes()).hexdigest()!=value:
            raise ValueError('Follow-up protocol or implementation changed: '+name)
    cases=[];jobs=[]
    for seed in range(2000,2032):
        source=refinement_phantom(seed)
        variants=[('reference',source,identity_spec(),'reference',25.)]
        for idx,(perm,signs) in enumerate(orbit()):
            f,spec=transform(source,'reindex',perm=perm,signs=signs)
            variants.append((f'R{idx:02d}',f,spec,'equivalent',25.))
        for name,kind,kw in [('encoding','encoding',{'slope':2.,'intercept':-8.}),('label7','label',{'label':7}),
             ('scale_half','scale',{'scale':.5}),('scale_double','scale',{'scale':2.}),
             ('intensity_a','intensity',{'gain':1.5,'offset':7.}),('intensity_b','intensity',{'gain':.5,'offset':-3.})]:
            f,spec=transform(source,kind,**kw)
            variants.append((name,f,spec,'equivalent' if kind in ('encoding','label') else 'covariant',25.))
        variants.append(('different_bin_width',source,identity_spec(),'not_applicable',50.))
        for fault in FAULT_IDS:
            try:bad=Frame(**transform_frame(replace(source,slope=2.,intercept=-8.).payload(),fault))
            except FaultNotApplicable as e:
                cases.append({'job_id':f'{seed}_{fault}','seed':seed,'name':fault,'group':'fault','activation':'not_applicable','reason':str(e)});continue
            variants.append((fault,bad,identity_spec(),'fault',25.))
        for name,f,spec,group,bw in variants:
            job_id=f'{seed}_{name}';started=time.perf_counter()
            try:
                ip,mp=write_frame(f,directory/'inputs',job_id);observed,geometry=read_frame(ip,mp,f.label)
                witness=transport_witness(source,observed,spec)
            except (ValueError,TypeError,OverflowError) as e:
                cases.append({'job_id':job_id,'seed':seed,'name':name,'group':group,'activation':'applicable','boundary_error':type(e).__name__,'reason':str(e)});continue
            cases.append({'job_id':job_id,'seed':seed,'name':name,'group':group,'activation':'applicable',
                'enriched_checkerboard':bool(seed%2),'source_digest':frame_digest(source),'observed_digest':frame_digest(observed),
                'spec':spec,'geometry':geometry,'witness':witness,'io_and_witness_seconds':time.perf_counter()-started,
                'anchors':analytic_anchors(source if group=='fault' else f),'settings_equal':bw==25.})
            job={'job_id':job_id,'image_path':ip.relative_to(directory).as_posix(),'mask_path':mp.relative_to(directory).as_posix(),
                 'label':f.label,'bin_width':bw,'spatial_mode':'3d'}
            jobs.append(job)
            if group=='fault':jobs.append(dict(job,job_id=job_id+'_repeat'))
    jsonl(directory/'cases.jsonl',cases);jsonl(directory/'jobs.jsonl',jobs)
    dump(directory/'input_manifest.json',{'seeds':list(range(2000,2032)),'cases':len(cases),'jobs_per_engine':len(jobs),
        'engine_for_profile_followup':'pyradiomics','enriched_checkerboard_seeds':16,
        'cases_sha256':hashlib.sha256((directory/'cases.jsonl').read_bytes()).hexdigest()})
    return len(jobs)


def evaluate(directory,engine='pyradiomics'):
    directory=Path(directory);cases=read_jsonl(directory/'cases.jsonl');native={x['job_id']:x for x in read_jsonl(directory/(engine+'.jsonl'))}
    sources={c['seed']:c['anchors'] for c in cases if c['group']=='reference' and 'anchors' in c};out=[]
    for c in cases:
        r={k:c[k] for k in ('job_id','seed','name','group','activation')};r['engine']=engine
        if c['activation']!='applicable' or 'boundary_error' in c:r.update(c);out.append(r);continue
        ref=native[f"{c['seed']}_reference"];v=native[c['job_id']];domain=sources[c['seed']]
        initial=compare_features(engine,ref.get('features',{}),v.get('features',{}),c['spec'],domain['n_voxels'],c['settings_equal'],domain)
        revised=revise_relation(initial,engine,c['spec']['kind']);anchors=check_anchors(engine,v.get('features',{}),c['anchors'])
        failed=v['status']!='extracted' or bool(v.get('nonfinite_features'))
        schema=schema_check(engine,v.get('features',{}),v['settings'].get('bin_width',25.))
        repeat=None
        if c['group']=='fault':repeat=compare_features(engine,v.get('features',{}),native[c['job_id']+'_repeat'].get('features',{}),identity_spec(),domain['n_voxels'],domain=domain)['status']
        r.update(initial_relation=initial['status'],relation=revised['status'],relation_counts=revised['counts'],
          anchors=anchors['status'],witness=c['witness'],geometry=c['geometry'],native_failure=failed,
          schema_failure=schema['status']!='satisfied',repeat=repeat,native_seconds=v['seconds'],io_and_witness_seconds=c['io_and_witness_seconds'],
          full_violation=failed or schema['status']!='satisfied' or not all(c['geometry'].values()) or
             any(x['status']=='violated' for x in (revised,anchors,c['witness'])))
        out.append(r)
    jsonl(directory/(engine+'_refined_decisions.jsonl'),out)
    summary={}
    for group in sorted({c['group'] for c in out}):
        attempted=[c for c in out if c['group']==group];usable=[c for c in attempted if 'full_violation' in c]
        summary[group]={'attempted':len(attempted),'analysable':len(usable),'unavailable':len(attempted)-len(usable),
          'initial_relation_violations':sum(c['initial_relation']=='violated' for c in usable),
          'revised_relation_violations':sum(c['relation']=='violated' for c in usable),
          'witness_violations':sum(c['witness']['status']=='violated' for c in usable),
          'anchor_violations':sum(c['anchors']=='violated' for c in usable),
          'full_violations':sum(c['full_violation'] for c in usable)}
    dump(directory/(engine+'_refined_summary.json'),summary);return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('prepare','evaluate'));p.add_argument('directory',type=Path)
    p.add_argument('--engine',choices=('pyradiomics','mirp'),default='pyradiomics');a=p.parse_args()
    print(json.dumps(prepare(a.directory) if a.command=='prepare' else evaluate(a.directory,a.engine),indent=2))
