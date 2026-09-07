"""Two explicit mutations of our output adapter, never of native engines.

Development demonstrations isolate feature-law and absolute-anchor blind spots.
They are not counted among the eight locked held-out input fault families.
"""
from pathlib import Path
import argparse
import json
from adapters import INTENSITY_LAWS
from benchmark import read_jsonl,identity_spec,dump,jsonl
from relations import compare_features,check_anchors


def mutate(engine,features,anchors,kind):
    result=dict(features);key=INTENSITY_LAWS[engine]['voxel_volume']
    if kind=='discard_voxel_volume_units':result[key]=float(anchors['n_voxels'])
    elif kind=='multiply_volume_by_1_02':result[key]*=1.02
    else:raise ValueError('Unknown owned output mutation')
    return result


def evaluate(directory):
    directory=Path(directory);cases=read_jsonl(directory/'cases.jsonl');records=[]
    if any(c['seed']>=1000 for c in cases):raise ValueError('These are development demonstrations only.')
    for engine in ('pyradiomics','mirp'):
        native={r['job_id']:r for r in read_jsonl(directory/(engine+'.jsonl'))}
        for kind in ('discard_voxel_volume_units','multiply_volume_by_1_02'):
            for case in cases:
                if case['group'] not in ('reference','equivalent','covariant'):continue
                refcase=next(c for c in cases if c['seed']==case['seed'] and c['group']=='reference')
                reference=mutate(engine,native[refcase['job_id']]['features'],refcase['anchors'],kind)
                observed=mutate(engine,native[case['job_id']]['features'],case['anchors'],kind)
                relation=compare_features(engine,reference,observed,case['spec'],case['anchors']['n_voxels'],domain=refcase['anchors'])
                anchor=check_anchors(engine,observed,case['anchors'])
                records.append({'seed':case['seed'],'job_id':case['job_id'],'engine':engine,'mutation':kind,
                    'group':case['group'],'transform':case['spec']['kind'],'relation':relation['status'],
                    'anchors':anchor['status'],'witness':case['witness']['status']})
    jsonl(directory/'output_mutants.jsonl',records)
    summary=[]
    for engine in ('pyradiomics','mirp'):
        for kind in ('discard_voxel_volume_units','multiply_volume_by_1_02'):
            for transform in ('reindex','encoding','label','scale','intensity','identity'):
                rows=[r for r in records if r['engine']==engine and r['mutation']==kind and r['transform']==transform]
                summary.append({'engine':engine,'mutation':kind,'transform':transform,'cases':len(rows),
                    'relation_violations':sum(r['relation']=='violated' for r in rows),
                    'anchor_violations':sum(r['anchors']=='violated' for r in rows)})
    dump(directory/'output_mutants_summary.json',summary);return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
    print(json.dumps(evaluate(a.directory),indent=2))
