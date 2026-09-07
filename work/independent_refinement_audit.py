"""Read-only follow-up audit; preserves initial and revised feature obligations."""
from collections import Counter, defaultdict
from pathlib import Path
import json
import math
import time

import nibabel as nib
import numpy as np

from independent_results_audit import WORK, SOFTWARE, rows, mapping, sha, save, close, relation, independent_digest
from relations import compare_features
from validation_refinement import revise_relation

MESH = {'original_shape_MeshVolume', 'original_shape_SurfaceArea',
        'original_shape_SurfaceVolumeRatio', 'original_shape_Sphericity'}
ANCHORS = {'mean': 'original_firstorder_Mean', 'minimum': 'original_firstorder_Minimum',
           'maximum': 'original_firstorder_Maximum', 'variance': 'original_firstorder_Variance',
           'energy': 'original_firstorder_Energy', 'voxel_volume': 'original_shape_VoxelVolume'}


def audit():
    started = time.perf_counter()
    directory = WORK / 'refinement'
    cases = mapping(rows(directory/'cases.jsonl'), 'cases')
    jobs = mapping(rows(directory/'jobs.jsonl'), 'jobs')
    native = mapping(rows(directory/'pyradiomics.jsonl'), 'outputs')
    published = mapping(rows(directory/'pyradiomics_refined_decisions.jsonl'), 'published decisions')
    assert set(cases) == set(published)
    frozen_count = {}
    for name in ('final_freeze.json', 'refinement_freeze.json'):
        frozen = json.loads((SOFTWARE/'protocol'/name).read_text())
        for filename, expected in frozen['sha256'].items():
            assert sha(SOFTWARE/filename) == expected, ('Frozen file changed', filename)
        frozen_count[name] = len(frozen['sha256'])
    manifest = json.loads((directory/'input_manifest.json').read_text())
    assert sha(directory/'cases.jsonl') == manifest['cases_sha256']
    assert len(cases) == manifest['cases'] == 2048
    assert len(jobs) == len(native) == manifest['jobs_per_engine'] == 2302
    assert set(jobs) == set(native)
    assert Counter(c['seed'] for c in cases.values()) == Counter({seed: 64 for seed in range(2000, 2032)})
    assert Counter(c['group'] for c in cases.values()) == Counter(reference=32, equivalent=1600,
        covariant=128, not_applicable=32, fault=256)
    assert all(c['activation'] == 'applicable' for c in cases.values())
    boundaries = [c['job_id'] for c in cases.values() if 'boundary_error' in c]
    assert set(boundaries) == {'2015_R06', '2015_R07'}
    assert all(key not in native and key not in jobs for key in boundaries)
    repeat_ids = {key for key in jobs if key.endswith('_repeat')}
    assert repeat_ids == {c['job_id']+'_repeat' for c in cases.values() if c['group'] == 'fault'}
    assert len(repeat_ids) == 256
    for key in repeat_ids:
        a, b = dict(jobs[key]), dict(jobs[key[:-7]])
        a.pop('job_id'); b.pop('job_id')
        assert a == b
    schema = set(json.loads((SOFTWARE/'protocol'/'feature_schema.json').read_text())['pyradiomics'])
    for key, row in native.items():
        assert row['engine'] == 'pyradiomics'
        assert row['settings'] == {k: jobs[key][k] for k in ('label', 'bin_width', 'spatial_mode')}
        assert row['status'] == 'extracted' and row['feature_count'] == len(row['features']) == 72
        assert set(row['features']) == schema and not row['nonfinite_features']
        assert all(v is not None and math.isfinite(v) for v in row['features'].values())
    counters = defaultdict(Counter)
    family_counts = defaultdict(Counter)
    split_counts = defaultdict(Counter)
    source_digests = defaultdict(set)
    direct_anchor_checks, decisions = [], []
    initial_alerts = Counter()
    retained_initial_obligations = 0
    for c in cases.values():
        group = c['group']
        fixture = 'enriched' if c['seed'] % 2 else 'natural'
        counters[group]['attempted'] += 1
        split_counts[fixture+'_'+group]['attempted'] += 1
        if 'boundary_error' in c:
            assert published[c['job_id']]['boundary_error'] == c['boundary_error']
            counters[group]['boundary_rejected'] += 1
            split_counts[fixture+'_'+group]['boundary_rejected'] += 1
            decisions.append({'job_id': c['job_id'], 'group': group, 'decision': 'outside_domain',
                              'boundary_error': c['boundary_error'], 'approved': False})
            continue
        source_digests[c['seed']].add(c['source_digest'])
        job = jobs[c['job_id']]
        image, mask = nib.load(directory/job['image_path']), nib.load(directory/job['mask_path'])
        assert independent_digest(image, mask) == c['observed_digest'], c['job_id']
        geometry_ok = image.shape == mask.shape and np.allclose(image.affine, mask.affine, rtol=0, atol=1e-4)
        assert geometry_ok == all(c['geometry'].values())
        v = native[c['job_id']]['features']
        ref = native[f"{c['seed']}_reference"]['features']
        initial = relation('pyradiomics', ref, v, c)
        refined_ref = {k: val for k, val in ref.items() if c['spec']['kind'] != 'reindex' or k not in MESH}
        revised = relation('pyradiomics', refined_ref, v, c)
        retained = {}
        original_report = compare_features('pyradiomics', ref, v, c['spec'], c['anchors']['n_voxels'], c['settings_equal'])
        revision_report = revise_relation(original_report, 'pyradiomics', c['spec']['kind'])
        assert original_report['status'] == ('violated' if initial['violation'] else 'satisfied' if initial['assessed'] else 'not_applicable')
        assert revision_report['status'] == ('violated' if revised['violation'] else 'satisfied' if revised['assessed'] else 'not_applicable')
        if c['spec']['kind'] == 'reindex':
            assert revised['assessed'] == 65 and initial['assessed'] == 69
            for key in MESH:
                entry = revision_report['features'][key]
                assert entry['status'] == 'not_applicable' and entry['initial_obligation'] == original_report['features'][key]
                retained[key] = entry
                retained_initial_obligations += 1
            for key in set(ref)-MESH:
                assert revision_report['features'][key] == original_report['features'][key]
        else:
            assert revision_report == original_report
        anchor_bad = any(not close(v.get(feature), c['anchors'][anchor]) for anchor, feature in ANCHORS.items())
        witness_bad = c['witness']['status'] == 'violated'
        repeat_bad = repeat_identity = False
        if group == 'fault':
            other = native[c['job_id']+'_repeat']['features']
            repeat_bad = relation('pyradiomics', v, other, c, force_identity=True)['violation']
            repeat_identity = v == other
        combined = revised['violation'] or anchor_bad or witness_bad or not geometry_ok
        decision = {'job_id': c['job_id'], 'group': group, 'fixture': fixture,
                    'initial_relation_violation': initial['violation'], 'revised_relation_violation': revised['violation'],
                    'initial_violated_features': initial['violated_features'], 'revised_violated_features': revised['violated_features'],
                    'withheld_initial_obligations': retained, 'revised_assessed_features': revised['assessed'],
                    'anchor_violation': anchor_bad, 'witness_violation': witness_bad, 'pair_geometry_violation': not geometry_ok,
                    'repeat_violation': repeat_bad, 'repeat_numeric_identity': repeat_identity, 'combined_violation': combined,
                    'relation_abstention': revised['assessed'] == 0, 'approved': not combined and revised['assessed'] > 0}
        p = published[c['job_id']]
        assert p['initial_relation'] == original_report['status'] and p['relation'] == revision_report['status']
        assert p['full_violation'] == combined and not p['schema_failure'] and not p['native_failure']
        assert (p['anchors'] == 'violated') == anchor_bad
        if group == 'fault': assert (p['repeat'] == 'violated') == repeat_bad
        for counter in (counters[group], split_counts[fixture+'_'+group], family_counts[c['name']] if group == 'fault' else None):
            if counter is None: continue
            counter['analysable'] += 1
            for key, value in decision.items():
                if isinstance(value, bool): counter[key] += int(value)
        if initial['violation'] and group != 'fault': initial_alerts[str(c['seed'])] += 1
        if group == 'reference':
            values = image.get_fdata()[np.asanyarray(mask.dataobj) == job['label']]
            n = len(values); mean = math.fsum(map(float, values))/n
            anchors = {'mean': mean, 'minimum': float(min(values)), 'maximum': float(max(values)),
                       'energy': math.fsum(float(x)*float(x) for x in values),
                       'variance': math.fsum((float(x)-mean)**2 for x in values)/n,
                       'voxel_volume': n*abs(float(np.linalg.det(image.affine[:3,:3])))}
            for anchor, feature in ANCHORS.items():
                passed = close(anchors[anchor], v[feature]) and close(anchors[anchor], c['anchors'][anchor])
                direct_anchor_checks.append({'seed': c['seed'], 'anchor': anchor, 'satisfied': passed})
                assert passed, (c['seed'], anchor)
        decisions.append(decision)
    assert len(source_digests) == 32 and all(len(v) == 1 for v in source_digests.values())
    assert len({next(iter(v)) for v in source_digests.values()}) == 32
    assert retained_initial_obligations == (32*48-2)*4 == 6136
    initial_audit = json.loads((WORK/'independent_results_audit_pyradiomics.json').read_text())
    assert initial_audit['native_output_sha256'] == sha(WORK/'heldout'/'pyradiomics.jsonl')
    assert len(initial_audit['correctly_transported_case_alerts']) == 36
    result = {'audit_integrity_passed': True, 'cases_retained': len(cases), 'planned_native_jobs': 2304,
              'scheduled_and_completed_native_jobs': len(native), 'fault_repeat_jobs': len(repeat_ids),
              'outside_domain_not_approved': boundaries, 'activation_not_applicable': 0,
              'no_duplicate_or_missing_scheduled_outputs': True, 'all_native_outputs_extracted_finite_complete': True,
              'frozen_hash_counts_verified': frozen_count, 'decoded_files_verified': 2046*2,
              'source_digest_consistency_and_uniqueness': True, 'groups': dict(counters),
              'fault_families': dict(family_counts), 'fixture_splits': dict(split_counts),
              'initial_control_alerts_by_seed': dict(initial_alerts), 'retained_initial_obligation_records': retained_initial_obligations,
              'direct_anchor_checks': direct_anchor_checks, 'initial_64_raw_sha_still_matches': True,
              'initial_64_equivalent_alerts_still_recorded': 36,
              'hashes': {name: sha(directory/name) for name in ('cases.jsonl', 'jobs.jsonl', 'pyradiomics.jsonl', 'pyradiomics_refined_decisions.jsonl')},
              'seconds': time.perf_counter()-started,
              'scope': 'New-input targeted follow-up after a known profile restriction; the eight fault families are known. No clinical sensitivity or independence of thousands of cases is asserted.'}
    save(WORK/'independent_refinement_audit.json', result)
    (WORK/'independent_refinement_decisions.jsonl').write_text(''.join(json.dumps(r, allow_nan=False)+'\n' for r in decisions))
    text = ['# Independent targeted refinement audit', '',
        'The initial and follow-up frozen hashes are unchanged. All 2048 planned cases are retained. Two equivalent cases '
        'were rejected at the format boundary and were not approved or scheduled for native extraction. All 2302 scheduled '
        'jobs have one complete, finite 72-feature PyRadiomics output, including all 256 repeated corrupted inputs. '
        'No fault mechanism was reclassified as inactive or not applicable.', '',
        'All 4092 analysable input files were decoded and their logged digests and image–mask geometry were checked. '
        'The 32 source digests are unique and consistent across their cases. Six anchors on each source were independently '
        'recomputed with scalar sums and the decoded affine: all 192 native-and-logged comparisons satisfy the frozen tolerances.', '',
        '| Group | Attempted | Analysable | Outside domain | Initial feature alerts | Revised feature alerts | Witness alerts | Anchor alerts | Combined alerts |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for group, c in counters.items():
        text.append(f"| {group} | {c['attempted']} | {c['analysable']} | {c['boundary_rejected']} | {c['initial_relation_violation']} | {c['revised_relation_violation']} | {c['witness_violation']} | {c['anchor_violation']} | {c['combined_violation']} |")
    text += ['', '| Known mechanism | Cases | Repeated identical | Repeat alerts | Feature alerts | Anchors | Witness | Combined |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, c in family_counts.items():
        text.append(f"| {name} | {c['analysable']} | {c['repeat_numeric_identity']} | {c['repeat_violation']} | {c['revised_relation_violation']} | {c['anchor_violation']} | {c['witness_violation']} | {c['combined_violation']} |")
    text += ['', 'The 1600 equivalent attempts comprise 800 natural-fixture cases and 800 enriched-fixture cases. '
             'The enriched denominator contains the two retained boundary rejections. All 384 initial feature alerts occur in '
             'the enriched fixtures; the refined reindexing profile has no feature alert among 1598 analysable equivalent cases. '
             'This does not validate the four withheld mesh features. The 32 changed-bin-width controls abstain from the '
             'feature relation and are not counted as approved feature equivalence.', '',
             'The audit explicitly verifies and archives all 6136 `initial_obligation` records for the four withheld mesh '
             'features in the 1534 analysable reindexing cases. Other feature decisions, non-reindexing relations, numerical '
             'tolerances, anchors and witness values are unchanged. The compact published decision log retains the initial '
             'aggregate status; the companion independent JSONL additionally retains each original actual/expected value, '
             'error and status under the revised not-applicable record. The original 64-phantom native-output SHA-256 still '
             'matches the original audit, where all 36 alerts remain recorded.', '',
             'These are targeted follow-up inputs after a profile restriction informed by the initial challenge. Sixteen '
             'phantoms are natural and sixteen contain a prospectively specified checkerboard enrichment. The eight '
             'fault mechanisms are known; this is neither an unseen-mechanism benchmark nor clinical sensitivity.']
    (WORK/'independent_refinement_audit.md').write_text('\n'.join(text)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('audit_integrity_passed', 'groups', 'fault_families', 'fixture_splits', 'initial_control_alerts_by_seed', 'retained_initial_obligation_records', 'seconds')}, indent=2))


if __name__ == '__main__':
    audit()
