from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from figure_style import configure, export_figure, INK, BLUE, GREY, PALE
W=Path(__file__).resolve().parent; D=W.parent
configure()
labels=['Image slice reversal','Buffer order reinterpretation','One-voxel ROI shift','Mask averaging and truncation','Direction matrix transposition','Corner–centre origin confusion','Calibration order reversal','Premature integer storage']
keys=['native_failure','geometry_violation','repeat_violation','conditional_violation','anchor_violation','witness_violation']
columns=['Native\nfailure','Paired\ngeometry','Repeat\nchange','Feature\nlaws','Absolute\nanchors','Physical\nwitness']
fig=plt.figure(figsize=(6.5,6.0))
axs=[fig.add_axes([.425,bottom,.55,.325]) for bottom in (.54,.075)]
cmap=LinearSegmentedColormap.from_list('checks',[PALE,BLUE])
for ax,engine,panel,heading_y in zip(axs,['pyradiomics','mirp'],['a','b'],[.955,.49]):
    data=json.loads((W/f'independent_results_audit_{engine}.json').read_text())
    families=sorted(data['fault_families'])
    a=np.array([[data['fault_families'][f][k] for k in keys] for f in families])
    assert all(data['fault_families'][f]['cases']==64 for f in families)
    ax.pcolormesh(np.arange(7)-.5,np.arange(9)-.5,a,vmin=0,vmax=64,
                  cmap=cmap,shading='flat',edgecolors='white',linewidth=1)
    ax.set(xlim=(-.5,5.5),ylim=(7.5,-.5))
    for i in range(8):
        for j in range(6):ax.text(j,i,str(a[i,j]),ha='center',va='center',color='white' if a[i,j]>32 else INK,fontsize=9)
    ax.set_yticks(range(8),[f'H{i+1:02d}  '+s for i,s in enumerate(labels)],fontsize=8.5,color=INK)
    ax.set_xticks(range(6),columns,fontsize=8.5,color=INK)
    ax.xaxis.tick_top()
    ax.tick_params(which='both',length=0,pad=5)
    fig.text(.04,heading_y,panel,fontsize=10.5,fontweight='bold',color=INK)
    fig.text(.105,heading_y,'PyRadiomics 3.0.1' if engine=='pyradiomics' else 'MIRP 2.5.0',fontsize=9,color=INK)
    fig.text(.975,heading_y,'Detected cases / 64',ha='right',fontsize=8.5,color=GREY)
    for s in ax.spines.values():s.set_visible(False)
export_figure(fig,D/'figures','P2_Fig2')
plt.close(fig)
(W/'fig2_caption.md').write_text('Fig. 2. Complementary detection of the eight owned-adapter fault families. Each cell is the number of detected declared transport violations among 64 synthetic phantoms for PyRadiomics (a) or MIRP (b). Native failure means an unusable extraction, paired geometry compares image and mask shape/affine, and repeat change compares two extractions of the same saved corrupted input. Feature laws use the initial conditional profile. The physical witness checks the observed input against the trusted source and declared transformation. Direction and origin faults may leave invariant scalar measurements correct while violating physical correspondence; they are not evidence of scalar measurement error. Counts are constructed test coverage, not clinical sensitivity. ROI, region of interest.',encoding='utf-8')
print('Figure 2 complete')
