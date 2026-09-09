"""Draw the sampling graphical abstract from archived anatomical case records."""
from pathlib import Path
import json
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'work'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from figure_style import configure, export_figure, BLUE, RED, GREY, LINE, INK

configure()
source = ROOT / 'results' / 'sampling_clinical' / 'cases.jsonl'
rows = [json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line]
volumes = {(row['dataset'], row['volume_id']) for row in rows}
controls = [row for row in rows if row['kind'] == 'valid_control']
active = [row for row in rows if row['kind'] == 'own_wrapper_mutation' and row['mutation']['active']]
detected = sum(row['sampling']['status'] == 'violated' for row in active)
paired = sum(row['paired_QA']['status'] == 'violated' for row in active)
geometry = sum(row['source_aware_geometry']['status'] == 'violated' for row in active)
indeterminate = [row for row in controls if row['sampling']['status'] == 'indeterminate_boundary']
satisfied = sum(row['sampling']['status'] == 'satisfied' for row in controls)
mri = sum(dataset == 'Task04_Hippocampus' for dataset, _ in volumes)
ct = sum(dataset == 'Task09_Spleen' for dataset, _ in volumes)
assert len(rows) == 14 * len(volumes) and len(controls) == 7 * len(volumes)
assert all(row['dataset'] == 'Task09_Spleen' for row in indeterminate)
assert satisfied + len(indeterminate) == len(controls)

fig = plt.figure(figsize=(6.5, 3.7), facecolor='white')
ax = fig.add_axes([0, 0, 1, 1])
ax.set(xlim=(0, 1), ylim=(0, 1))
ax.axis('off')


def text(x, y, value, size=9, color=INK, weight='normal', ha='left'):
    ax.text(x, y, value, fontsize=size, color=color, weight=weight,
            ha=ha, va='center')


text(.05, .923, 'RadAccord', size=18, color=BLUE, weight='bold')
text(.95, .923, 'RESEARCH SOFTWARE', size=8, color=GREY, ha='right')
text(.05, .836, 'Physical consistency before radiomic extraction', size=12)
ax.plot([.05, .95], [.777, .777], color=LINE, linewidth=.7)

steps = [
    (.05, '1  Declare', 'Retain the source',
     ['Specify grid and sampling', 'Crop · pad · orient · resample']),
    (.38, '2  Check', 'Compare independently',
     ['Position · intensity · region', 'Sampling and coverage']),
    (.71, '3  Decide', 'Report the next step',
     ['Preserved input: apply profile', 'New sampling: extract again',
      'Ambiguous boundary: review']),
]
for x, label, heading, lines in steps:
    text(x, .700, label, size=11, color=BLUE, weight='bold')
    text(x, .609, heading, size=9.5, weight='bold')
    for index, line in enumerate(lines):
        text(x, .540 - index * .065, line, size=8.5, color=GREY)
for first, last in [(.318, .36), (.648, .69)]:
    ax.add_patch(FancyArrowPatch((first, .607), (last, .607), arrowstyle='-|>',
                                mutation_scale=8, color=GREY, linewidth=.7))

ax.plot([.05, .95], [.335, .335], color=LINE, linewidth=.7)
metrics = [
    (.05, str(len(volumes)), 'public MRI/CT volumes', f'{mri} MRI · {ct} CT'),
    (.38, f'{detected} / {len(active)}', 'active test faults detected',
     f'Paired checks: {paired}; geometry: {geometry}'),
    (.71, str(len(indeterminate)), 'CT resamplings indeterminate',
     f'{satisfied} / {len(controls)} controls satisfied'),
]
for x, number, label, note in metrics:
    text(x, .264, number, size=18, color=BLUE, weight='bold')
    text(x, .187, label, size=8.5)
    text(x, .125, note, size=7.7, color=GREY)
ax.plot([.71, .95], [.316, .316], color=RED, linewidth=1.3)
text(.05, .045, 'Own-wrapper perturbations. Indeterminate cases are not approvals. Research preprocessing only.',
     size=7.2, color=GREY)

export_figure(fig, ROOT / 'docs' / 'figures' / 'sampling', 'P2_Graphical_abstract')
plt.close(fig)
print('Graphical abstract created from archived case records.')
