"""Draw a bounded graphical abstract from retained sampling and writer records."""
import argparse
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'work'))
from figure_style import configure, export_figure, BLUE, RED, GREY, LINE, INK


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/figures/native')
    args = parser.parse_args()
    configure()
    records = [json.loads(line) for line in (ROOT/'results/sampling_clinical/cases.jsonl').read_text(encoding='utf-8').splitlines()]
    volumes = {(row['dataset'], row['volume_id']) for row in records}
    active = [row for row in records if row['kind'] == 'own_wrapper_mutation' and row['mutation']['active']]
    detected = sum(row['sampling']['status'] == 'violated' for row in active)
    historical = json.loads((ROOT/'results/mirp_nifti_regression/2.4.1.json').read_text(encoding='utf-8'))['cases']
    assert all(row['paired_export_geometry_agrees'] and row['array_exact'] and row['mask_exact'] for row in historical)
    oblique = [row for row in historical if row['case_id'] != 'axis_aligned']
    historical_detected = sum(row['verification']['status'] == 'violated' for row in oblique)
    native = json.loads((ROOT/'results/native_refinement/summary/summary.json').read_text(encoding='utf-8'))
    native_rows = [row for row in native['pair_counts'] if row['grouping'] == 'engine']
    counts = {key: sum(row[key] for row in native_rows) for key in
              ('planned', 'completed', 'exact_native_values', 'satisfied', 'violated', 'indeterminate', 'unavailable')}
    assert counts['completed'] == counts['planned'] and counts['violated'] == 0
    fig = plt.figure(figsize=(6.5, 3.7), facecolor='white')
    ax = fig.add_axes([0, 0, 1, 1]); ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')
    def text(x, y, value, size=9, color=INK, weight='normal', ha='left'):
        ax.text(x, y, value, fontsize=size, color=color, weight=weight, ha=ha, va='center')
    text(.05, .923, 'RadAccord', 18, BLUE, 'bold')
    text(.95, .923, 'RESEARCH SOFTWARE', 8, GREY, ha='right')
    text(.05, .836, 'Physical consistency before radiomic feature reuse', 11.5)
    ax.plot([.05, .95], [.777, .777], color=LINE, linewidth=.7)
    steps = [
        (.05, '1  Declare', 'Retain the source', ['Specify grid and sampling', 'Keep native configuration']),
        (.38, '2  Observe', 'Compare independently', ['Position · intensity · region', 'Actual recorded boundaries']),
        (.71, '3  Document', 'Keep execution evidence', ['Input fidelity and coverage', 'Reextraction or review', 'Unresolved checks explicit']),
    ]
    for x, label, heading, lines in steps:
        text(x, .700, label, 11, BLUE, 'bold')
        text(x, .609, heading, 9.3, weight='bold')
        for index, line in enumerate(lines):
            text(x, .540-index*.065, line, 8.1, GREY)
    for first, last in [(.318, .36), (.648, .69)]:
        ax.add_patch(FancyArrowPatch((first, .607), (last, .607), arrowstyle='-|>',
                                    mutation_scale=8, color=GREY, linewidth=.7))
    ax.plot([.05, .95], [.335, .335], color=LINE, linewidth=.7)
    metrics = [
        (.05, str(len(volumes)), 'public MRI/CT volumes', f'{len(records):,} retained sampling cases'),
        (.38, f'{detected} / {len(active)}', 'active test faults detected', 'Controlled wrapper perturbations'),
        (.71, f'{historical_detected} / {len(oblique)}', 'historical oblique errors', 'Paired alignment missed both'),
    ]
    for x, number, label, note in metrics:
        text(x, .264, number, 18, BLUE, 'bold')
        text(x, .187, label, 8.2)
        text(x, .125, note, 7.2, GREY)
    ax.plot([.71, .95], [.316, .316], color=RED, linewidth=1.3)
    text(.05, .052, f'Native reevaluation: {counts["exact_native_values"]}/{counts["planned"]} outputs unchanged; '
         f'{counts["satisfied"]} satisfied, {counts["indeterminate"]} indeterminate, {counts["unavailable"]} unavailable.', 7.1, GREY)
    text(.05, .020, 'Reused development inputs · Evidence follows extraction · No clinical validity inferred.', 6.6, GREY)
    export_figure(fig, args.output, 'P2_Graphical_abstract')
    plt.close(fig)


if __name__ == '__main__':
    main()
