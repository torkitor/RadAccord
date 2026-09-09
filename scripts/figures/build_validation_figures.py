"""Draw prospective-validation figures from a completed, provenance-bound aggregate.

No extraction, acceptance decisions, or tolerance changes occur here. Pairwise
timing arithmetic is verified by build_prospective_plans.py; this renderer checks
the retained volume summaries and independently recomputes their median/range.
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Patch, Rectangle

ROOT = Path(__file__).resolve().parents[2]
STYLE_PATH = ROOT / 'work' / 'figure_style.py'
_style_spec = importlib.util.spec_from_file_location('validation_figure_style', STYLE_PATH)
style = importlib.util.module_from_spec(_style_spec)
_style_spec.loader.exec_module(style)
BLUE, CORAL, GREY, INK, LINE, PALE = (
    style.BLUE, style.RED, style.GREY, style.INK, style.LINE, style.PALE)
COLLECTIONS = {'Task02_Heart': ('Heart MRI', 'mr'), 'Task06_Lung': ('Lung CT', 'ct')}
ENGINES = {'pyradiomics': 'PyRadiomics', 'mirp': 'MIRP'}
STATES = ('satisfied', 'violated', 'indeterminate', 'unavailable')
COLORS = (BLUE, CORAL, '#D8DDEA', '#A9A9A9', 'white')
STATE_LABELS = ('Satisfied', 'Violated', 'Indeterminate', 'Unavailable', 'No completed pair')
METRICS = ('baseline_seconds', 'audited_seconds', 'absolute_overhead_seconds',
           'paired_log_ratio', 'pair_lifetime_peak_bytes')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key.')
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON value.')))


def count(value):
    require(type(value) is int and value >= 0, 'Counts must be non-negative integers.')
    return value


def _hash(value):
    require(isinstance(value, str) and len(value) == 64 and
            all(c in '0123456789abcdef' for c in value), 'Invalid provenance digest.')


def median_range(values):
    require(all(type(x) in (int, float) and math.isfinite(x) for x in values), 'Invalid timing value.')
    return {'n': len(values), 'median': statistics.median(values) if values else None,
            'minimum': min(values) if values else None, 'maximum': max(values) if values else None}


def _same_number(a, b):
    return a is b if a is None or b is None else math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


def validate_aggregate(aggregate):
    require(aggregate.get('schema_version') == 'prospective-aggregate-1', 'Unexpected aggregate schema.')
    require(set(aggregate['plan_sha256']) == {'coverage', 'timing'}, 'Both study plans are required.')
    for value in aggregate['plan_sha256'].values():
        _hash(value)
    provenance = aggregate['run_provenance']
    require(len(provenance) == 4 and {(p['mode'], p['engine']) for p in provenance} ==
            {(mode, engine) for mode in ('coverage', 'timing') for engine in ENGINES},
            'The four native run ledgers are required; absent runs are not final results.')
    for row in provenance:
        for field in ('plan_sha256', 'freeze_sha256', 'records_sha256', 'attempt_starts_sha256'):
            _hash(row[field])
        require(row['plan_sha256'] == aggregate['plan_sha256'][row['mode']], 'Run/plan binding differs.')
    expected = {(mode, collection, engine, operation + '_' + modality)
                for collection, (_, modality) in COLLECTIONS.items() for engine in ENGINES
                for mode in ('coverage', 'timing')
                for operation in (('identity', 'linear_1p5', 'cubic_2') if mode == 'coverage'
                                  else ('identity', 'cubic_2'))}
    groups = {}
    for row in aggregate['groups']:
        key = tuple(row[name] for name in ('mode', 'collection', 'engine', 'workflow'))
        require(key not in groups and key in expected, 'Unexpected or duplicate study group.')
        groups[key] = row
        selected, repeats = (12, 1) if row['mode'] == 'coverage' else (4, 4)
        require(row['selected_volume_slots'] == selected and
                row['intention_to_evaluate_pairs'] == selected * repeats, 'Selected denominator changed.')
        fields = ('source_eligible_volume_slots', 'prepared_volume_slots', 'native_planned_pairs',
                  'not_native_planned_pairs', 'attempted_pairs', 'recorded_pairs', 'completed_pairs',
                  'exact_preservation_pairs', 'failed_recorded_pairs', 'started_without_record_pairs',
                  'unstarted_pairs', 'checkpoint_count')
        for field in fields:
            count(row[field])
        require(0 <= row['prepared_volume_slots'] <= row['source_eligible_volume_slots'] <= selected,
                'Invalid source/preparation accounting.')
        require(row['native_planned_pairs'] == repeats * row['prepared_volume_slots'] and
                row['native_planned_pairs'] + row['not_native_planned_pairs'] == selected * repeats and
                row['recorded_pairs'] == row['completed_pairs'] + row['failed_recorded_pairs'] and
                row['attempted_pairs'] == row['recorded_pairs'] + row['started_without_record_pairs'] and
                row['native_planned_pairs'] == row['attempted_pairs'] + row['unstarted_pairs'] and
                row['exact_preservation_pairs'] <= row['completed_pairs'], 'Pair ledger does not balance.')
        require(sum(count(n) for n in row['source_or_preparation_outcomes'].values()) == selected,
                'Selected source/preparation ledger does not balance.')
        for field, denominator in (('relationship_outcomes', 'completed_pairs'),
                                   ('checkpoint_outcomes', 'checkpoint_count')):
            require(set(row[field]) == set(STATES) and
                    sum(count(n) for n in row[field].values()) == row[denominator], 'State ledger does not balance.')
        if row['mode'] == 'timing':
            require(0 <= count(row['warmup_exact_preservation_pairs']) <=
                    count(row['warmup_pairs_completed']) <= row['recorded_pairs'], 'Invalid warmup ledger.')
    require(set(groups) == expected, 'Incomplete collection/engine/workflow groups.')
    require(sum(r['intention_to_evaluate_pairs'] for r in groups.values() if r['mode'] == 'coverage') == 144
            and sum(r['intention_to_evaluate_pairs'] for r in groups.values() if r['mode'] == 'timing') == 128,
            'The 144/128 selected-pair denominators changed.')

    volumes_by_group = {key: [] for key in expected}
    seen = set()
    for row in aggregate['volume_summaries']:
        key = tuple(row[name] for name in ('mode', 'collection', 'engine', 'workflow'))
        identity = (*key, row['input_id'])
        require(key in groups and identity not in seen, 'Unexpected or duplicate volume summary.')
        seen.add(identity)
        repeats = 1 if row['mode'] == 'coverage' else 4
        require(count(row['unchanged']) <= count(row['completed']) <= count(row['planned']) <= repeats,
                'Invalid volume-level pair counts.')
        require(sum(count(n) for n in row['orders'].values()) == row['planned'], 'Volume order counts differ.')
        require(set(row['relationship_outcomes']) == set(STATES) and
                sum(count(n) for n in row['relationship_outcomes'].values()) == row['completed'],
                'Volume outcome counts differ.')
        if row['mode'] == 'timing':
            for metric in METRICS:
                summary = row[metric]
                require(count(summary['n']) <= row['completed'], 'Volume metric has excess observations.')
                if metric != 'pair_lifetime_peak_bytes':
                    require(summary['n'] == row['completed'], 'A completed pair lacks a timing metric.')
                require((summary['median'] is None) == (summary['n'] == 0), 'Invalid empty metric summary.')
                if summary['n']:
                    require(all(type(summary[name]) in (int, float) and math.isfinite(summary[name])
                                for name in ('q1', 'median', 'q3')) and
                            summary['q1'] <= summary['median'] <= summary['q3'], 'Invalid volume distribution.')
        volumes_by_group[key].append(row)

    for key, row in groups.items():
        volumes = volumes_by_group[key]
        require(len(volumes) <= row['selected_volume_slots'] and
                sum(v['planned'] for v in volumes) == row['recorded_pairs'] and
                sum(v['completed'] for v in volumes) == row['completed_pairs'] and
                sum(v['unchanged'] for v in volumes) == row['exact_preservation_pairs'],
                'Group and retained volume counts differ.')
        for state in STATES:
            require(sum(v['relationship_outcomes'][state] for v in volumes) == row['relationship_outcomes'][state],
                    'Volume and group outcomes differ.')
        if row['mode'] == 'timing':
            for metric in METRICS:
                calculated = median_range([v[metric]['median'] for v in volumes if v[metric]['n']])
                stored = row['volume_medians'][metric]
                require(all(_same_number(calculated[name], stored.get(name)) for name in calculated),
                        'A group median or range differs from its retained volume medians.')
    return groups, volumes_by_group


def figure_values(aggregate_path, historical_path):
    aggregate = read_json(aggregate_path)
    groups, volumes = validate_aggregate(aggregate)
    bars, timings = [], []
    for collection in COLLECTIONS:
        for engine in ENGINES:
            selected = [r for key, r in groups.items() if key[:3] == ('coverage', collection, engine)]
            outcomes = {state: sum(r['relationship_outcomes'][state] for r in selected) for state in STATES}
            outcomes['no_completed_pair'] = sum(r['intention_to_evaluate_pairs'] - r['completed_pairs'] for r in selected)
            require(sum(outcomes.values()) == 36, 'A coverage bar must retain all 36 selected pairs.')
            missing = {name: sum(r[name] for r in selected) for name in
                       ('not_native_planned_pairs', 'failed_recorded_pairs', 'started_without_record_pairs', 'unstarted_pairs')}
            require(sum(missing.values()) == outcomes['no_completed_pair'], 'Incomplete-pair accounting differs.')
            bars.append({'collection': collection, 'engine': engine, 'selected_pairs': 36,
                         'completed_pairs': sum(r['completed_pairs'] for r in selected),
                         'exact_preservation_pairs': sum(r['exact_preservation_pairs'] for r in selected),
                         'outcomes': outcomes, 'incomplete_pair_breakdown': missing})
            for operation in ('identity', 'cubic_2'):
                workflow = operation + '_' + COLLECTIONS[collection][1]
                key = ('timing', collection, engine, workflow)
                volume_points = [{'input_id': v['input_id'], 'completed_repeats': v['completed'],
                                  'overhead_seconds': v['absolute_overhead_seconds']['median']}
                                 for v in sorted(volumes[key], key=lambda v: v['input_id'])
                                 if v['absolute_overhead_seconds']['n']]
                timings.append({'collection': collection, 'engine': engine, 'workflow': workflow,
                                'selected_volume_slots': 4, 'selected_pairs': 16,
                                'completed_pairs': groups[key]['completed_pairs'], 'volume_points': volume_points,
                                'overhead_seconds': median_range([p['overhead_seconds'] for p in volume_points])})
    historical = [json.loads(line) for line in Path(historical_path).read_text(encoding='utf-8').splitlines() if line.strip()]
    active = [r for r in historical if r['kind'] == 'own_wrapper_mutation' and r['mutation']['active']]
    legacy = {'retained_cases': len(historical), 'source_volumes': len({(r['dataset'], r['volume_id']) for r in historical}),
              'active_constructed_faults': len(active), 'violated_active_faults': sum(r['sampling']['status'] == 'violated' for r in active)}
    require(legacy == {'retained_cases': 4214, 'source_volumes': 301, 'active_constructed_faults': 1605,
                       'violated_active_faults': 1605}, 'Historical sampling evidence differs from the cited study.')
    totals = {mode: {field: sum(r[field] for r in groups.values() if r['mode'] == mode)
                     for field in ('intention_to_evaluate_pairs', 'completed_pairs', 'exact_preservation_pairs')}
              for mode in ('coverage', 'timing')}
    return {'schema_version': 'prospective-figure-values-1', 'provenance': {
                'aggregate_sha256': digest(aggregate_path), 'historical_sampling_records_sha256': digest(historical_path),
                'renderer_sha256': digest(__file__), 'style_sha256': digest(STYLE_PATH),
                'plan_sha256': aggregate['plan_sha256'], 'native_runs': aggregate['run_provenance']},
            'selected_source_volumes': 24, 'coverage_bars': bars, 'timing_groups': timings,
            'totals': totals, 'historical_sampling': legacy,
            'timing_definition': 'Each point is the median of available paired audited-minus-native times within one source volume; horizontal range and diamond summarize those volume medians. Selected denominator remains four volumes and sixteen pairs per group. No confidence interval.',
            'scope': aggregate['scope']}


def _number(value):
    return 'NA' if value is None else f'{value:.3g}'


def draw_figure4(values, output):
    fig = plt.figure(figsize=(6.5, 6.6))
    fig.text(.035, .965, 'a', fontsize=11, weight='bold')
    fig.text(.080, .965, 'Native relationship outcomes on newly selected inputs', fontsize=9.5)
    ax = fig.add_axes([.265, .664, .50, .242])
    for y, row in enumerate(values['coverage_bars']):
        left = 0
        for index, n in enumerate(row['outcomes'].values()):
            ax.barh(y, n, left=left, height=.58, color=COLORS[index],
                    edgecolor=GREY if index == 4 else 'white', linewidth=.6,
                    hatch='///' if index == 4 else None)
            if n >= 3:
                ax.text(left + n/2, y, str(n), ha='center', va='center', fontsize=8.5,
                        color='white' if index == 0 else INK)
            left += n
        ax.text(1.035, y, ' / '.join(str(n) for n in row['outcomes'].values()),
                transform=ax.get_yaxis_transform(), va='center', fontsize=7.4)
    ax.set(xlim=(0, 36), ylim=(3.65, -.65), xticks=[0, 12, 24, 36],
           yticks=range(4), yticklabels=[f"{COLLECTIONS[r['collection']][0]}\n{ENGINES[r['engine']]}" for r in values['coverage_bars']])
    ax.tick_params(axis='y', length=0, pad=7, labelsize=8.3)
    ax.tick_params(axis='x', labelsize=8)
    ax.spines['left'].set_visible(False)
    ax.set_xlabel('Selected pairs (36 per collection and engine)', fontsize=8)
    ax.text(1.035, 1.07, 'S / V / I / U / NC', transform=ax.transAxes, fontsize=7.4)
    handles = [Patch(facecolor=c, edgecolor=GREY if i == 4 else 'white',
                     hatch='///' if i == 4 else None, label=label)
               for i, (c, label) in enumerate(zip(COLORS, STATE_LABELS))]
    fig.legend(handles=handles, loc='center', bbox_to_anchor=(.51, .582), ncol=3,
               frameon=False, fontsize=7.8, handlelength=1.5, columnspacing=1.5)
    fig.text(.035, .550, 'NC includes selected exclusions, failed or interrupted attempts, and unstarted pairs.', fontsize=7.3, color=GREY)
    fig.add_artist(plt.Line2D([.035, .97], [.529, .529], transform=fig.transFigure, color=LINE, lw=.7))
    fig.text(.035, .501, 'b', fontsize=11, weight='bold')
    fig.text(.080, .501, 'Paired additional runtime: volume medians and their range', fontsize=9.5)
    bx = fig.add_axes([.305, .137, .467, .325])
    all_points = [p['overhead_seconds'] for r in values['timing_groups'] for p in r['volume_points']]
    lo, hi = (min([0, *all_points]), max([0, *all_points])) if all_points else (0, 1)
    span = hi - lo or max(abs(hi), 1)
    for y, row in enumerate(values['timing_groups']):
        distribution = row['overhead_seconds']
        points = row['volume_points']
        if points:
            bx.plot([distribution['minimum'], distribution['maximum']], [y, y], color=GREY, lw=.8, zorder=1)
            for index, point in enumerate(points):
                offset = (index - (len(points)-1)/2) * .085
                bx.scatter(point['overhead_seconds'], y+offset, s=15, facecolor='white',
                           edgecolor=BLUE, linewidth=.8, zorder=3)
            bx.scatter(distribution['median'], y, marker='D', s=22, color=BLUE, zorder=4)
        label = f"{_number(distribution['median'])} [{_number(distribution['minimum'])}, {_number(distribution['maximum'])}]"
        bx.text(1.04, y, label, transform=bx.get_yaxis_transform(), va='center', fontsize=7.5)
        if len(points) != 4:
            bx.text(.02, y+.33, f'{len(points)}/4 volumes with timings', transform=bx.get_yaxis_transform(), fontsize=7, color=GREY)
    labels = [f"{COLLECTIONS[r['collection']][0]} · {ENGINES[r['engine']]}\n"
              + ('Identity' if r['workflow'].startswith('identity') else 'Cubic · 2 mm') for r in values['timing_groups']]
    bx.set(xlim=(lo-.045*span, hi+.08*span), ylim=(7.65, -.65), yticks=range(8), yticklabels=labels)
    bx.axvline(0, color=LINE, lw=.65, zorder=0)
    bx.tick_params(axis='y', length=0, pad=7, labelsize=7.8)
    bx.tick_params(axis='x', labelsize=8)
    bx.spines['left'].set_visible(False)
    bx.set_xlabel('Audited − native runtime (seconds)', fontsize=8.5)
    bx.text(1.04, 1.04, 'Median [minimum, maximum]', transform=bx.transAxes, fontsize=7.2)
    fig.text(.035, .057, 'Four selected volumes per group · Four measured repeats per volume · Balanced execution order', fontsize=7.3, color=GREY)
    fig.text(.035, .030, 'Descriptive timing on retained crops; repeated pairs are not independent volumes.', fontsize=7.3, color=GREY)
    style.export_figure(fig, output, 'P2_Fig4')
    plt.close(fig)


def draw_graphical_abstract(values, output):
    fig = plt.figure(figsize=(6.5, 4.2))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis('off')
    def text(x, y, value, size=9, color=INK, weight='normal', ha='left'):
        ax.text(x, y, value, fontsize=size, color=color, weight=weight, ha=ha, va='center')
    text(.045, .935, 'RadAccord', 18, BLUE, 'bold')
    text(.955, .935, 'RESEARCH SOFTWARE', 8, GREY, ha='right')
    text(.045, .860, 'Physical consistency before radiomic feature reuse', 11)
    steps = [(.045, 'Source and declaration', ('Retain image + ROI', 'Declare native configuration', 'Specify the expected sampling')),
             (.375, 'Independent checks', ('Observe feature inputs', 'Position · intensity · ROI', 'Keep unresolved checks explicit')),
             (.705, 'Native outputs retained', ('Measure output preservation', 'Report ROI coverage separately', 'New sampling: extract again'))]
    for x, title, lines in steps:
        ax.add_patch(Rectangle((x, .475), .25, .29, facecolor=PALE, edgecolor=BLUE, lw=.7))
        text(x+.125, .713, title, 9, BLUE, 'bold', 'center')
        for index, line in enumerate(lines):
            text(x+.125, .640-index*.056, line, 7.8, ha='center')
    for start, end in ((.30, .368), (.63, .698)):
        ax.add_patch(FancyArrowPatch((start, .62), (end, .62), arrowstyle='-|>', mutation_scale=8, color=GREY, lw=.7))
    coverage = values['totals']['coverage']
    timing = values['totals']['timing']
    outcomes = {state: sum(r['outcomes'][state] for r in values['coverage_bars']) for state in STATES}
    text(.045, .421, 'Prospectively frozen evaluation · 24 newly selected Heart MRI / Lung CT volumes', 8.7, weight='bold')
    metrics = [(.045, f"{coverage['completed_pairs']} / 144", 'native pairs completed', 'Selected denominator retained'),
               (.375, f"{coverage['exact_preservation_pairs']} / {coverage['completed_pairs']}", 'completed outputs unchanged', 'Against direct native execution'),
               (.705, f"{timing['completed_pairs']} / 128", 'measured timing pairs completed', 'Eight volumes · paired repeats')]
    for x, number, label, note in metrics:
        text(x, .343, number, 16, BLUE, 'bold')
        text(x, .286, label, 7.9)
        text(x, .241, note, 7.2, GREY)
    text(.045, .186, f"Relationship outcomes: {outcomes['satisfied']} satisfied · {outcomes['violated']} violated · "
         f"{outcomes['indeterminate']} indeterminate · {outcomes['unavailable']} unavailable", 7.9)
    ax.plot([.045, .955], [.146, .146], color=LINE, lw=.7)
    legacy = values['historical_sampling']
    text(.045, .111, f"Earlier sampling study: {legacy['retained_cases']:,} cases; "
         f"{legacy['violated_active_faults']:,}/{legacy['active_constructed_faults']:,} active constructed faults detected.", 8, GREY)
    text(.045, .060, 'Author-run computational evaluation · Input fidelity does not establish clinical validity.', 7.5, GREY)
    text(.045, .024, 'Uncertainty blocks acceptance; correct resampling does not establish feature invariance.', 7.5, GREY)
    style.export_figure(fig, output, 'P2_Graphical_abstract')
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aggregate', type=Path, default=ROOT/'results/prospective_aggregate.json')
    parser.add_argument('--historical-records', type=Path, default=ROOT/'results/sampling_clinical/cases.jsonl')
    parser.add_argument('--output', type=Path, default=ROOT/'docs/figures/validation')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    values = figure_values(args.aggregate, args.historical_records)
    if not args.validate_only:
        style.configure()
        draw_figure4(values, args.output)
        draw_graphical_abstract(values, args.output)
        (args.output/'validation_figure_values.json').write_text(
            json.dumps(values, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({'status': 'validated' if args.validate_only else 'rendered',
                      'coverage_selected_pairs': 144, 'timing_selected_pairs': 128,
                      'aggregate_sha256': values['provenance']['aggregate_sha256']}, sort_keys=True))


if __name__ == '__main__':
    main()
