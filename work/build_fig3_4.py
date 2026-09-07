"""Figures 3 and 4 from saved study outputs; no extraction or frozen-code edits."""
from pathlib import Path
from collections import Counter
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
from figure_style import configure, export_figure, BLUE, RED, INK, GREY, LINE

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'work'
OUT = ROOT / 'figures'
OUT.mkdir(exist_ok=True)
configure()


def rows(relative):
    return [json.loads(line) for line in (WORK / relative).open(encoding='utf-8') if line.strip()]


def style(ax):
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(labelsize=8.5)
    ax.grid(axis='y', color=LINE, linewidth=.5, alpha=.7, zorder=0)
    ax.set_axisbelow(True)


def save(fig, number):
    name = f'P2_Fig{number}'
    export_figure(fig, OUT, name)
    plt.close(fig)


# FIGURE 3. Counts use the saved output-mutant decisions. The curves reconstruct
# those two explicit mutations from the saved native values and input counts.
mutants = rows('development_final/output_mutants.jsonl')
summary3 = json.loads((WORK / 'development_final/output_mutants_summary.json').read_text())
native = {engine: {r['job_id']: r for r in rows(f'development_final/{engine}.jsonl')}
          for engine in ('pyradiomics', 'mirp')}
cases = {r['job_id']: r for r in rows('development_final/cases.jsonl')}
for s in summary3:
    subset = [r for r in mutants if all(r[k] == s[k] for k in ('engine', 'mutation', 'transform'))]
    assert len(subset) == s['cases']
    assert sum(r['relation'] == 'violated' for r in subset) == s['relation_violations']
    assert sum(r['anchors'] == 'violated' for r in subset) == s['anchor_violations']

families = ('discard_voxel_volume_units', 'multiply_volume_by_1_02')
volume_key = {'pyradiomics': 'original_shape_VoxelVolume', 'mirp': 'morph_vol_approx'}
scales = np.array([.5, 1., 2.])
names = ('scale_half', 'reference', 'scale_double')
fig3_data = {'source': 'development_final', 'per_seed_curves': [], 'scale_decisions': []}
fig, axes = plt.subplots(1, 2, figsize=(6.5, 4.6), sharey=True)
fig.subplots_adjust(left=.13, right=.975, top=.8, bottom=.305, wspace=.24)
titles = ['Discard voxel-volume units', 'Multiply volume by 1.02']
for ax, family, title, panel in zip(axes, families, titles, ['a', 'b']):
    style(ax)
    panel_left = ax.get_position().x0
    fig.text(panel_left-.085,.95,panel,fontsize=10.5,fontweight='bold')
    fig.text(panel_left,.95,title,fontsize=9)
    ax.set_xscale('log', base=2); ax.set_yscale('log', base=2)
    xx = np.geomspace(.45, 2.2, 100)
    ax.plot(xx, xx**3, color=GREY, linestyle='--', linewidth=1.25, zorder=1)
    for engine, color, marker in [('pyradiomics', BLUE, 'o'), ('mirp', RED, 'x')]:
        curves = []
        for seed in range(12):
            values = []
            for name in names:
                key = f'{seed}_{name}'
                value = (float(cases[key]['anchors']['n_voxels'])
                         if family == families[0]
                         else 1.02 * native[engine][key]['features'][volume_key[engine]])
                values.append(value)
            ratios = np.asarray(values) / values[1]
            curves.append(ratios)
            fig3_data['per_seed_curves'].append({'engine': engine, 'mutation': family,
                                               'seed': seed, 'scales': scales.tolist(),
                                               'reported_volume': values,
                                               'ratio_to_unscaled': ratios.tolist()})
            marker_colors = {'facecolors': 'none', 'edgecolors': color} if marker == 'o' else {'color': color}
            ax.scatter(scales, ratios, s=34 if marker == 'o' else 24, marker=marker,
                       linewidths=1.0, zorder=4 if marker == 'x' else 3, **marker_colors)
        ax.plot(scales, np.median(curves, axis=0), color=color, linewidth=.8, alpha=.45, zorder=2)
        subset = [r for r in mutants if r['engine'] == engine and r['mutation'] == family
                  and r['transform'] == 'scale']
        fig3_data['scale_decisions'].append({'engine': engine, 'mutation': family,
            'cases': len(subset), 'relation_alerts': sum(r['relation'] == 'violated' for r in subset),
            'anchor_alerts': sum(r['anchors'] == 'violated' for r in subset)})
    ax.set(xlim=(.43, 2.3), ylim=(.08, 13.), xticks=scales,
           yticks=[.125, 1., 8.], xlabel='Spatial scale λ')
    ax.set_xticklabels(['0.5', '1', '2']); ax.set_yticklabels(['1/8', '1', '8'])
    ax.minorticks_off()
axes[0].set_ylabel('Reported volume /\nits unscaled value', fontsize=9)

legend = [Line2D([], [], marker='o', color=BLUE, markerfacecolor='none', linestyle='none', label='PyRadiomics adapter'),
          Line2D([], [], marker='x', color=RED, linestyle='none', label='MIRP adapter'),
          Line2D([], [], color=GREY, linestyle='--', label='Prescribed λ³ response')]
fig.legend(handles=legend, loc='center', bbox_to_anchor=(.525, .877), ncol=3,
           frameon=False, fontsize=8.5, handlelength=1.5, columnspacing=1.1)
for ax, family in zip(axes, families):
    x = ax.get_position().x0 + ax.get_position().width / 2
    records = [r for r in fig3_data['scale_decisions'] if r['mutation'] == family]
    assert len(records) == 2 and all(r['cases'] == 24 for r in records)
    assert records[0]['relation_alerts'] == records[1]['relation_alerts']
    assert records[0]['anchor_alerts'] == records[1]['anchor_alerts']
    fig.text(x, .155, f"Scale-law alerts: {records[0]['relation_alerts']}/24", ha='center', fontsize=9)
    fig.text(x, .11, f"Absolute-anchor alerts: {records[0]['anchor_alerts']}/24", ha='center', fontsize=9,
             color=INK)
fig.text(.525, .045, 'Counts per engine: 12 phantoms × 2 nonidentity spatial scales',
         ha='center', fontsize=8.5, color=GREY)
save(fig, 3)
(WORK / 'fig3_source_data.json').write_text(json.dumps(fig3_data, indent=2), encoding='utf-8')


# FIGURE 4. Raw source and 48 orbit values are preserved. Rounding is used only
# to identify visible groups far above floating-point arithmetic differences.
held = {r['job_id']: r for r in rows('heldout/pyradiomics.jsonl') if r['job_id'].startswith('1026_')}
key = 'original_shape_MeshVolume'
reference = held['1026_reference']['features'][key]
ids = [f'1026_R{i:02d}' for i in range(48)]
orbit_cases = [r for r in rows('heldout/cases.jsonl') if r['job_id'] in ids]
assert len(orbit_cases) == 48
assert all(r['witness']['status'] == 'satisfied' and all(r['geometry'].values()) for r in orbit_cases)
volumes = np.array([held[k]['features'][key] for k in ids])
relative = 100 * (volumes / reference - 1)
groups = Counter(np.round(volumes, 3))
assert len(groups) == 4 and sorted(groups.values()) == [12, 12, 12, 12]
max_error = float(np.max(np.abs(relative)))

refined = rows('refinement/pyradiomics_refined_decisions.jsonl')
summary4 = json.loads((WORK / 'refinement/pyradiomics_refined_summary.json').read_text())['equivalent']
eq = [r for r in refined if r['group'] == 'equivalent']
usable = [r for r in eq if 'full_violation' in r]
initial = sum(r['initial_relation'] == 'violated' for r in usable)
revised = sum(r['relation'] == 'violated' for r in usable)
assert (len(eq), len(usable), initial, revised) == (
    summary4['attempted'], summary4['analysable'],
    summary4['initial_relation_violations'], summary4['revised_relation_violations'])
unavailable = [r for r in eq if 'full_violation' not in r]
assert len(unavailable) == summary4['unavailable']
protocol = json.loads((ROOT / 'software/protocol/refinement_protocol.json').read_text())
assert protocol['new_seeds']['count'] == 32
strata = []
for enriched in (False, True):
    group = [r for r in eq if bool(r['seed'] % 2) == enriched]
    strata.append({'enriched': enriched, 'attempted': len(group),
                   'analysable': sum('full_violation' in r for r in group),
                   'initial_alerts': sum(r.get('initial_relation') == 'violated' for r in group),
                   'revised_alerts': sum(r.get('relation') == 'violated' for r in group)})

fig = plt.figure(figsize=(6.5, 6.4))
ax = fig.add_axes([.14, .54, .825, .334])
style(ax)
fig.text(.04,.955,'a',fontsize=10.5,fontweight='bold')
fig.text(.105,.955,'Four MeshVolume levels across 48 equivalent files',fontsize=9)
ax.scatter(np.arange(48), relative, c=BLUE, s=18, edgecolors='white', linewidths=.3, zorder=3)
threshold = 100 * (1e-6 + 1e-5 * abs(reference)) / abs(reference)
ax.axhspan(-threshold, threshold, color=GREY, alpha=.17, zorder=1)
ax.axhline(0, color=GREY, linewidth=.65, zorder=2)
ax.set(xlim=(-1, 48), ylim=(-.157, .015), xticks=[0, 8, 16, 24, 32, 40, 47],
       yticks=[-.15, -.10, -.05, 0], xlabel='Signed-axis representation (0–47)',
       ylabel='MeshVolume difference (%)')
ax.set_yticklabels(['−0.15', '−0.10', '−0.05', '0'])
fig.text(.105, .913, f'PyRadiomics 3.0.1 · phantom 1026 · max. |difference| {max_error:.3f}%',
         fontsize=8.5, color=GREY)

ax2 = fig.add_axes([.255, .178, .71, .205])
style(ax2); ax2.grid(False); ax2.grid(axis='x', color=LINE, linewidth=.5, alpha=.7)
fig.text(.04,.425,'b',fontsize=10.5,fontweight='bold')
fig.text(.105, .425, 'Follow-up: 32 new phantoms, including 16 enriched',
         fontsize=9)
counts = [initial, revised]
for y, n, color in zip([1, 0], counts, [RED, BLUE]):
    value = 100 * n / len(usable)
    if n:
        ax2.barh(y, value, height=.32, color=color, zorder=3)
    else:
        ax2.plot([0], [y], marker='|', markersize=11, color=color, markeredgewidth=1.5, zorder=4)
    ax2.text(value + .7, y, f'{n:,}/{len(usable):,}', va='center', fontsize=9, color=INK)
ax2.set(xlim=(0, 32), ylim=(-.55, 1.55), yticks=[1, 0],
        xticks=[0, 10, 20, 30], xlabel='Equivalent representations with an alert (%)')
ax2.set_yticklabels(['Original\nprofile', 'Revised\nprofile'])
fig.text(.14, .085, f'Outside input domain: {len(unavailable)}/{len(eq):,} (qform–sform conflict)',
         fontsize=8.5, color=GREY)
fig.text(.14, .048, 'Four mesh obligations withheld for reindexing; values and tolerances unchanged.',
         fontsize=8.5, color=GREY)
save(fig, 4)

data4 = {'source_reference_mesh_volume_mm3': reference, 'job_ids': ids,
         'physical_witness_satisfied_for_all_48': True,
         'mesh_volume_mm3': volumes.tolist(), 'difference_percent': relative.tolist(),
         'display_groups_rounded_0_001_mm3': {str(k): v for k, v in groups.items()},
         'max_absolute_difference_percent': max_error, 'equivalent_followup': summary4,
         'strata': strata, 'outside_domain_cases': unavailable}
(WORK / 'fig4_source_data.json').write_text(json.dumps(data4, indent=2), encoding='utf-8')
print(json.dumps({'fig3_scale_counts': fig3_data['scale_decisions'],
                  'fig4_max_percent': max_error, 'fig4_groups': len(groups),
                  'fig4_followup': summary4, 'fig4_strata': strata}, indent=2))
