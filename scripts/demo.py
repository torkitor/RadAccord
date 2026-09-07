"""Run the physical correspondence check on the bundled synthetic examples."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'software'))
from physical_contracts import read_frame, transport_witness


def main():
    examples = ROOT / 'software' / 'examples'
    results = []
    for name, expected in (('valid_reindex', 'satisfied'), ('origin_fault', 'violated')):
        contract = json.loads((examples / f'{name}_contract.json').read_text(encoding='utf-8'))
        source, source_geometry = read_frame(examples / 'source_image.nii.gz',
                                            examples / 'source_mask.nii.gz', contract['source_label'])
        candidate, candidate_geometry = read_frame(examples / f'{name}_image.nii.gz',
                                                  examples / f'{name}_mask.nii.gz', contract['candidate_label'])
        witness = transport_witness(source, candidate, contract['transformation'])
        if not all(source_geometry.values()) or not all(candidate_geometry.values()):
            raise AssertionError(f'Unexpected image-mask disagreement in {name}.')
        expected_checks = {'position': name == 'valid_reindex', 'intensity': True, 'roi': True}
        if witness['status'] != expected or witness.get('checks') != expected_checks:
            raise AssertionError(f'Unexpected physical correspondence result in {name}.')
        results.append({'example': name, 'source_geometry': source_geometry,
                        'candidate_geometry': candidate_geometry, 'witness': witness})
    print(json.dumps({
        'demo_checks_passed': True,
        'results': results,
        'scope': 'Real bundled NIfTI inputs and declared transformations. No radiomic feature '
                 'extraction or feature-law evaluation is performed; clinical validity is not assessed.',
    }, indent=2))


if __name__ == '__main__':
    main()
