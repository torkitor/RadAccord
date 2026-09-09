"""Publication figures from the preserved first evaluation and native records."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'work'))
from figure_style import configure, export_figure, BLUE, RED, GREY, PALE, INK, LINE
configure()
OUT = BASE / 'docs' / 'figures' / 'sampling'
def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
source = BASE / 'results' / 'sampling_clinical' / 'cases.jsonl'
checkpoint_source = source.with_name('checkpoint_demo.jsonl')
native_source = BASE / 'results' / 'native_feature_subset' / 'native_comparisons.jsonl'
rows, native = read(source), read(native_source)
datasets = [('Task04_Hippocampus', 'MRI', 260), ('Task09_Spleen', 'CT', 41)]
families = [('stale_crop_origin', 'Stale crop origin'), ('shared_origin_shift', 'Shared origin shift'),
            ('half_voxel_sampling_displacement', 'Half-voxel sampling shift'),
            ('wrong_image_kernel', 'Wrong image interpolator'),
            ('linear_mask_threshold', 'Linear mask + threshold'),
            ('premature_integer_storage', 'Premature integer storage')]
comparators = [('paired_QA', 'Paired\nchecks'), ('source_aware_geometry', 'Source-aware\ngeometry'),
               ('legacy_full_grid', 'Original\nfull-grid'), ('sampling', 'Declared\nsampling')]
cmap = LinearSegmentedColormap.from_list('accord', [PALE, BLUE])
values = {'input_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, native_source, checkpoint_source)},
          'figure2': [], 'figure3': [], 'figure4': []}

fig = plt.figure(figsize=(6.5, 6.0))
for panel, (dataset, short, total) in enumerate(datasets):
    ax = fig.add_axes([.365, .58-panel*.45, .60, .30])
    matrix = np.zeros((6, 4))
    labels = {}
    inactive = 0
    for i, (family, title) in enumerate(families):
        cases = [r for r in rows if r['dataset']==dataset and r['case']==family]
        active = [r for r in cases if r['mutation']['active']]
        inactive += len(cases)-len(active)
        for j, (comparator, name) in enumerate(comparators):
            rejected = sum(r[comparator]['status']=='violated' for r in active)
            unavailable = sum(r[comparator]['status'] in ('not_applicable','not_available') for r in active)
            unresolved = sum(r[comparator]['status']=='indeterminate_boundary' for r in active)
            matrix[i,j] = rejected/len(active) if active else 0
            labels[i,j] = 'N/A' if unavailable==len(active) and active else f'{rejected}/{len(active)}'
            values['figure2'].append({'dataset':dataset,'case':family,'comparator':comparator,
                                     'active':len(active),'violated':rejected,'unavailable':unavailable,'indeterminate':unresolved})
    ax.imshow(matrix, vmin=0, vmax=1, cmap=cmap, aspect='auto')
    for (i,j), label in labels.items():
        ax.text(j,i,label,ha='center',va='center',fontsize=8.5,
                color='white' if matrix[i,j]>.6 else GREY if label=='N/A' else INK)
    ax.set_yticks(range(6), [label for _,label in families], fontsize=8.5)
    ax.set_xticks(range(4), [label for _,label in comparators], fontsize=8)
    ax.xaxis.tick_top()
    ax.tick_params(axis='both', which='both',length=0,pad=7)
    ax.set_xticks(np.arange(-.5,4,1),minor=True); ax.set_yticks(np.arange(-.5,6,1),minor=True)
    ax.grid(which='minor',color='white',linewidth=1)
    for spine in ax.spines.values(): spine.set_visible(False)
    fig.text(.025,.954-panel*.45,chr(97+panel),weight='bold',fontsize=11)
    fig.text(.065,.954-panel*.45,f'{short} · {total} released volumes',fontsize=9)
    fig.text(.965,.954-panel*.45,'Detected / active constructed faults',ha='right',fontsize=8,color=GREY)
    fig.text(.365,.538-panel*.45,f'Inactive perturbations retained: {inactive}' + (' (stale crop origin)' if inactive else ''),fontsize=8,color=GREY)
fig.text(.025,.026,'N/A: outside the original full-grid domain. Engineered faults; counts are not clinical sensitivity.',fontsize=8,color=GREY)
export_figure(fig,OUT,'P2_Fig2');plt.close(fig)

roles = [('isotropic_0p8mm','0.8 mm'),('isotropic_1mm','1 mm'),('isotropic_2mm','2 mm'),('wrong_image_kernel','Wrong kernel')]
identifiers = [(d, v) for d,_,_ in datasets for v in sorted({r['volume_id'] for r in native if r['dataset']==d})]
fig = plt.figure(figsize=(6.5,6.4))
ax = fig.add_axes([.28,.59,.67,.29])
matrix=np.zeros((6,4))
for i,(dataset,identifier) in enumerate(identifiers):
    for j,(role,_) in enumerate(roles):
        record=next(r for r in native if (r['dataset'],r['volume_id'],r['candidate_role'])==(dataset,identifier,role))
        assert record['comparable_features']==72
        matrix[i,j]=record['beyond_tolerance']
        values['figure3'].append({'dataset':dataset,'volume_id':identifier,'role':role,
                                 'changed':record['beyond_tolerance'],'comparable':record['comparable_features']})
ax.imshow(matrix,vmin=0,vmax=72,cmap=cmap,aspect='auto')
for i in range(6):
    for j in range(4): ax.text(j,i,f'{int(matrix[i,j])}/72',ha='center',va='center',fontsize=8.5,color='white' if matrix[i,j]>40 else INK)
ax.set_yticks(range(6),[v.replace('hippocampus_','MRI ').replace('spleen_','CT ') for _,v in identifiers])
ax.set_xticks(range(4),[label for _,label in roles]);ax.xaxis.tick_top();ax.tick_params(length=0,pad=7)
ax.axhline(2.5,color='white',lw=3); ax.axvline(2.5,color='white',lw=3)
ax.set_xticks(np.arange(-.5,4,1),minor=True);ax.set_yticks(np.arange(-.5,6,1),minor=True);ax.grid(which='minor',color='white',lw=1);ax.tick_params(which='minor',length=0)
for sp in ax.spines.values():sp.set_visible(False)
fig.text(.025,.957,'a',weight='bold',fontsize=11)
fig.text(.065,.957,'Native features beyond the fixed numerical tolerance',fontsize=9)
fig.text(.28,.557,'Correct grids vs source',fontsize=8,color=GREY)
fig.text(.95,.557,'Wrong kernel vs correct 0.8 mm',fontsize=8,color=GREY,ha='right')
fig.text(.025,.475,'b',weight='bold',fontsize=11)
fig.text(.065,.475,'Wrong interpolator: unchanged volume can conceal intensity changes',fontsize=9)
ax=fig.add_axes([.14,.15,.80,.27])
landmarks=[('original_shape_VoxelVolume','Volume'),('original_firstorder_Mean','Mean'),('original_firstorder_Variance','Variance')]
for group,(dataset,short,_) in enumerate(datasets):
    selected=[r for r in native if r['dataset']==dataset and r['candidate_role']=='wrong_image_kernel']
    for j,(key,_) in enumerate(landmarks):
        vals=[100*r['landmarks'][key]['relative_absolute_difference'] for r in selected]
        x=group*4+j
        ax.scatter(np.array([x-.12,x,x+.12]),vals,s=29,color=BLUE if group==0 else RED,zorder=3,edgecolor='white',linewidth=.5)
        ax.plot([x-.21,x+.21],[np.median(vals)]*2,color=INK,lw=1)
ax.set_xticks([0,1,2,4,5,6],[label for _ in datasets for _,label in landmarks])
ax.set_ylabel('Absolute relative change (%)',fontsize=8.5)
ax.set_ylim(-1.5,31);ax.set_yticks([0,10,20,30]);ax.set_xlim(-.6,6.6);ax.grid(axis='y',color=LINE,lw=.5)
fig.text(.34,.075,'MRI',ha='center',color=BLUE,weight='bold',fontsize=9)
fig.text(.785,.075,'CT',ha='center',color=GREY,weight='bold',fontsize=9)
fig.text(.025,.027,'Dots: prespecified volumes; bars: medians. Six-volume descriptive subset; no population inference.',fontsize=8,color=GREY)
export_figure(fig,OUT,'P2_Fig3');plt.close(fig)

fig=plt.figure(figsize=(6.5,5.7))
fig.text(.025,.953,'a',weight='bold',fontsize=11)
fig.text(.065,.953,'Correct CT resampling: ambiguity remains explicit',fontsize=9)
ax=fig.add_axes([.22,.59,.70,.26])
for y,(role,label) in enumerate(roles[:3]):
    selected=[r for r in rows if r['dataset']=='Task09_Spleen' and r['case']==role]
    counts={status:sum(r['sampling']['status']==status for r in selected) for status in ['satisfied','indeterminate_boundary','violated']}
    values['figure4'].append({'case':role,**counts})
    ax.barh(y,counts['satisfied'],color=BLUE,height=.52)
    ax.barh(y,counts['indeterminate_boundary'],left=counts['satisfied'],color='#B7BDC9',height=.52)
    ax.text(counts['satisfied']/2,y,str(counts['satisfied']),ha='center',va='center',color='white',fontsize=9)
    if counts['indeterminate_boundary']:ax.text(counts['satisfied']+counts['indeterminate_boundary']/2,y,str(counts['indeterminate_boundary']),ha='center',va='center',fontsize=9)
ax.set_yticks(range(3),[label for _,label in roles[:3]]);ax.invert_yaxis();ax.set_xlim(0,41);ax.set_xticks([0,10,20,30,41]);ax.set_xlabel('Released CT volumes',fontsize=8.5)
ax.legend(handles=[Patch(color=BLUE,label='Satisfied'),Patch(color='#B7BDC9',label='Indeterminate')],frameon=False,ncol=2,loc='lower center',bbox_to_anchor=(.5,1.03),fontsize=8)
fig.text(.025,.46,'b',weight='bold',fontsize=11)
fig.text(.065,.46,'A correct endpoint does not erase a recorded intermediate error',fontsize=9)
ax=fig.add_axes([.19,.15,.68,.25])
checkpoint_records=read(checkpoint_source)
curves={}
for record in checkpoint_records:
    curve=[0.]+[stage['sampling']['max_corner_error_mm'] for stage in record['stages']]
    if record['case'] in curves:assert curve==curves[record['case']]
    curves[record['case']]=curve
    values['figure4'].append({'dataset':record['dataset'],'volume_id':record['volume_id'],
                             'case':record['case'],'corner_errors_mm':curve})
compensated=next(value for name,value in curves.items() if name!='identity_checkpoints')
ax.plot([0,1,2],compensated,'-o',color=RED,lw=1.2,ms=5,label='Compensated origin error')
ax.plot([0,1,2],curves['identity_checkpoints'],'--o',color=BLUE,lw=1,ms=4,mfc='white',label='Identity control')
ax.set_xticks([0,1,2],['Source','Intermediate','Endpoint']);ax.set_ylim(-.7,13.5);ax.set_yticks([0,5,11]);ax.set_xlim(-.2,2.2)
ax.set_ylabel('Position discrepancy (mm)',fontsize=8.5);ax.grid(axis='y',color=LINE,lw=.5)
ax.text(1.08,10.8,'11 mm violation',fontsize=8,color=GREY)
ax.legend(frameon=False,fontsize=8,ncol=2,loc='upper center',bbox_to_anchor=(.5,-.23))
fig.text(.025,.025,'Constructed checkpoint examples on the first MRI and CT IDs; both produced the same pattern.',fontsize=8,color=GREY)
export_figure(fig,OUT,'P2_Fig4');plt.close(fig)
(OUT/'figure_values.json').write_text(json.dumps(values,indent=2)+'\n',encoding='utf-8',newline='\n')
print('Figures 2–4 generated from preserved study records.')
