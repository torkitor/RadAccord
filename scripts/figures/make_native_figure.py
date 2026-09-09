"""Compare audited native calibration and post-development re-evaluation.

Reads completed descriptive summaries only; never runs either native extractor.
State counts are plotted per planned baseline/audited pair, not per feature.
No outcome count is embedded in this builder. The original interruption ledger
remains represented as absent completed pairs, separately from unavailable
relationships after a completed extraction.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
style_spec = importlib.util.spec_from_file_location('radaccord_publication_style', ROOT/'work/figure_style.py')
style = importlib.util.module_from_spec(style_spec)
style_spec.loader.exec_module(style)

ENGINES = ('pyradiomics', 'mirp')
ENGINE_LABELS = {'pyradiomics': 'PyRadiomics', 'mirp': 'MIRP'}
STATES = ('satisfied', 'violated', 'indeterminate', 'unavailable', 'no_completed_pair')
RAW_STATES = STATES[:4]+('not_completed', 'interrupted_unrecorded', 'not_reached')


def read_summary(path):
    path = Path(path)
    summary = json.loads(path.read_text(encoding='utf-8'))
    if summary['schema_version'] != 'native-descriptive-summary-1':
        raise ValueError('A validated native descriptive summary is required')
    if summary['provenance']['frozen_files_verified'] < 1:
        raise ValueError('The summary has no verified scientific freeze')
    rows = {row['engine']: row for row in summary['pair_counts'] if row['grouping'] == 'engine'}
    if set(rows) != set(ENGINES):
        raise ValueError('Both engine summaries must be complete before plotting')
    runs = {row['engine']: row for row in summary['provenance']['runs']}
    for engine, row in rows.items():
        for key in ('planned', 'completed', 'exact_native_values', 'numeric_digest_equal', *RAW_STATES):
            if type(row[key]) is not int or row[key] < 0:
                raise ValueError('Invalid nonnegative integer count: '+key)
        if sum(row[state] for state in RAW_STATES) != row['planned']:
            raise ValueError('Every planned pair must appear in exactly one outcome state')
        if sum(row[state] for state in STATES[:4]) != row['completed']:
            raise ValueError('Completed-pair and relationship denominators disagree')
        if not row['exact_native_values'] <= row['completed'] <= row['planned']:
            raise ValueError('Native-value/completion denominators disagree')
        if row['numeric_digest_equal'] != row['exact_native_values']:
            raise ValueError('Native-value preservation and numeric digests disagree')
        if runs[engine]['completed_pairs'] != row['completed']:
            raise ValueError('Run-summary and descriptive completion counts disagree')
    if sum(row['planned'] for row in rows.values()) != summary['units']['retained_pairs']:
        raise ValueError('Summary units do not account for the planned slots')
    return summary, rows


def caption(phases):
    chunks = []
    for name, _, rows in phases:
        totals = {key: sum(row[key] for row in rows.values())
                  for key in ('planned', 'completed', 'satisfied', 'violated', 'indeterminate', 'unavailable')}
        chunks.append(f"{name}: {totals['completed']}/{totals['planned']} pairs completed, "
                      f"with {totals['satisfied']} satisfied, {totals['violated']} violated, "
                      f"{totals['indeterminate']} indeterminate and {totals['unavailable']} unavailable "
                      "pair-level relationships.")
    initial = phases[0][2]
    missing = {k: sum(row[k] for row in initial.values())
               for k in ('not_completed', 'interrupted_unrecorded', 'not_reached')}
    return (
        'Fig. 4. Native integration calibration and post-development re-evaluation. '
        '(a) Pair-level relationship outcomes for each extractor. Each stacked bar accounts for '
        'every planned baseline-versus-audited pair; a completed extraction with an unavailable '
        'relationship remains distinct from a pair that did not complete. '+' '.join(chunks)+' '
        f"The initial phase retains {missing['not_completed']} recorded native extraction "
        f"{'failure' if missing['not_completed']==1 else 'failures'}, "
        f"{missing['interrupted_unrecorded']} interrupted "
        f"{'slot' if missing['interrupted_unrecorded']==1 else 'slots'} without a case record and "
        f"{missing['not_reached']} subsequent slots not reached. "
        '(b) Completed/planned pairs and exact native-value preservation/completed pairs. '
        'Preservation means that the adapter returned the producer values unchanged within each '
        'pair; it does not assert cross-engine feature equality, correctness, finiteness or '
        'clinical validity. The second phase reuses the study inputs after an explicitly recorded '
        'development amendment; it is not independent validation. Numerically compatible but '
        'unresolved relationships are indeterminate and block acceptance, including when the '
        'candidate agrees with the nominal reference. Absence of observed violations does not '
        'therefore imply acceptance of indeterminate or unavailable relationships.'
    )


def build(initial_path, refined_path, output):
    initial, initial_rows = read_summary(initial_path)
    refined, refined_rows = read_summary(refined_path)
    for engine in ENGINES:
        if initial_rows[engine]['planned'] != refined_rows[engine]['planned']:
            raise ValueError('This matched-plan graphic requires equal planned counts')
    if initial['provenance']['freeze_sha256'] == refined['provenance']['freeze_sha256']:
        raise ValueError('The two named study phases cannot share an unchanged freeze')
    phases = [('Initial calibration', initial, initial_rows),
              ('Post-development re-evaluation', refined, refined_rows)]
    style.configure()
    fig = plt.figure(figsize=(6.5, 5.5))
    fig.text(.035, .96, 'a', fontsize=11, weight='bold')
    fig.text(.080, .96, 'Relationship outcomes across all planned pairs', fontsize=9.5)
    fig.text(.035, .916, 'Initial calibration', fontsize=8.7, color=style.GREY)
    fig.text(.035, .723, 'Post-development re-evaluation', fontsize=8.7, color=style.GREY)

    chart = fig.add_axes([.22, .553, .70, .346])
    y_positions = [3.4, 2.5, 1.1, .2]
    colors = [style.BLUE, style.RED, '#D8DDEA', '#A9A9A9', 'white']
    labels = ['Satisfied', 'Violated', 'Indeterminate', 'Unavailable', 'No completed pair']
    planned = max(row['planned'] for _, _, rows in phases for row in rows.values())
    values = []
    for row_index, (phase_name, _, rows) in enumerate(phases):
        for engine_index, engine in enumerate(ENGINES):
            row = rows[engine]
            y = y_positions[row_index*2+engine_index]
            counts = {state: row[state] for state in STATES[:4]}
            counts['no_completed_pair'] = sum(row[state] for state in RAW_STATES[4:])
            left = 0
            for state, color in zip(STATES, colors):
                count = counts[state]
                chart.barh(y, count, left=left, height=.50, color=color,
                           edgecolor=style.GREY if state=='no_completed_pair' else 'white',
                           linewidth=.55, hatch='///' if state=='no_completed_pair' else None)
                if count >= 4:
                    chart.text(left+count/2, y, str(count), ha='center', va='center',
                               color='white' if state=='satisfied' else style.INK, fontsize=8.2)
                left += count
            # Small states retain their exact counts in a compact annotation.
            small = [labels[i]+': '+str(counts[state]) for i, state in enumerate(STATES)
                     if 0 < counts[state] < 4]
            if small:
                chart.text(0, y-.35, ' · '.join(small), fontsize=8., color=style.GREY,
                           ha='left', va='top')
            chart.text(row['planned']+.7, y, str(row['planned']), fontsize=8.2, va='center')
            values.append(dict(phase=phase_name, engine=engine, planned=row['planned'],
                               completed=row['completed'], exact_native_values=row['exact_native_values'],
                               numeric_digest_equal=row['numeric_digest_equal'], **counts,
                               **{key: row[key] for key in RAW_STATES[4:]}))
    chart.set_yticks(y_positions, [ENGINE_LABELS[engine] for _ in phases for engine in ENGINES], fontsize=8.6)
    chart.tick_params(axis='y', length=0, pad=8)
    chart.set_xlim(0, planned+4)
    chart.set_ylim(-.50, 3.95)
    chart.set_xticks([])
    chart.spines['left'].set_visible(False)
    chart.spines['bottom'].set_visible(False)
    chart.text(planned+.7, 3.88, 'Planned', fontsize=8., ha='center', color=style.GREY)
    legend = [Patch(facecolor=color, edgecolor=style.GREY if state=='no_completed_pair' else color,
                    linewidth=.6, hatch='///' if state=='no_completed_pair' else None, label=label)
              for state, color, label in zip(STATES, colors, labels)]
    fig.legend(handles=legend, loc='upper center', bbox_to_anchor=(.5, .525), frameon=False,
               ncol=3, fontsize=8.1, handlelength=1.5, columnspacing=1.5, handletextpad=.5)
    fig.add_artist(Line2D([.035, .965], [.433, .433], transform=fig.transFigure, color=style.LINE, lw=.7))
    fig.text(.035, .399, 'b', fontsize=11, weight='bold')
    fig.text(.080, .399, 'Completion and unchanged native values', fontsize=9.5)
    fig.text(.535, .354, 'Completed / planned', fontsize=8, ha='center', color=style.GREY)
    fig.text(.825, .354, 'Exact values / completed', fontsize=8, ha='center', color=style.GREY)
    table_y = [.315, .275, .215, .175]
    for i, row in enumerate(values):
        if i % 2 == 0:
            phase = 'Initial' if i == 0 else 'Re-evaluation'
            fig.text(.035, table_y[i], phase, fontsize=8.2, color=style.GREY)
        fig.text(.205, table_y[i], ENGINE_LABELS[row['engine']], fontsize=8.3)
        fig.text(.535, table_y[i], f"{row['completed']} / {row['planned']}", ha='center', fontsize=9, color=style.INK)
        fig.text(.825, table_y[i], f"{row['exact_native_values']} / {row['completed']}", ha='center', fontsize=9, color=style.BLUE)
    fig.text(.035, .113, 'Indeterminate relationships block acceptance; unchanged values do not establish correctness.',
             fontsize=8, color=style.GREY)
    fig.text(.035, .066, 'Same study inputs after development amendments · Post-extraction observation · Research software',
             fontsize=8, color=style.GREY)

    output = Path(output)
    style.export_figure(fig, output, 'P2_Fig4')
    plt.close(fig)
    audit = {
        'schema_version': 'native-figure-values-1',
        'source_sha256': {'initial_summary': hashlib.sha256(Path(initial_path).read_bytes()).hexdigest(),
                          'refined_summary': hashlib.sha256(Path(refined_path).read_bytes()).hexdigest()},
        'source_freeze_sha256': {'initial': initial['provenance']['freeze_sha256'],
                                 'refined': refined['provenance']['freeze_sha256']},
        'unit': 'planned baseline-versus-audited pair', 'values': values,
        'scope': 'Initial calibration and post-development re-evaluation; not independent validation.'}
    (output/'P2_Fig4_values.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    (output/'P2_Fig4_caption.md').write_text(caption(phases)+'\n', encoding='utf-8')
    return audit


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--initial-summary', type=Path,
                        default=ROOT/'results/native_integration/summary_first_development/summary.json')
    parser.add_argument('--refined-summary', type=Path,
                        default=ROOT/'results/native_refinement/summary/summary.json')
    parser.add_argument('--output', type=Path, default=ROOT/'docs/figures/native')
    args = parser.parse_args()
    build(args.initial_summary, args.refined_summary, args.output)
