"""Create small synthetic NIfTI examples and audit a linked preprocessing plan.

No radiomics engine or clinical input is needed. All images are generated here.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'software'))
from physical_contracts import Frame, write_frame
from radaccord_sampling import audit_plan, render_html


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('Choose an empty output directory to preserve existing reports.')
    x, y, z = np.indices((17, 17, 17))
    data = (3*x + 2*y - z - 40.25).astype(float)
    mask = np.zeros(data.shape, np.int16)
    mask[5:12, 5:12, 5:12] = 1
    source = Frame(data, mask, np.diag([1., 2., 3., 1.]))
    crop_map = np.eye(4)
    crop_map[:3, 3] = 2
    cropped = Frame(data[2:-2, 2:-2, 2:-2].copy(), mask[2:-2, 2:-2, 2:-2].copy(),
                    source.affine @ crop_map)
    scale = np.diag([2., 2., 2., 1.])
    coarse = Frame(cropped.data[::2, ::2, ::2].copy(), cropped.mask[::2, ::2, ::2].copy(),
                   cropped.affine @ scale)
    shifted_affine = coarse.affine.copy()
    shifted_affine[0, 3] += 11.
    shifted = Frame(coarse.data, coarse.mask, shifted_affine)
    references = {}
    for name, frame in [('source', source), ('crop', cropped), ('coarse', coarse), ('shifted', shifted)]:
        paths = write_frame(frame, output, name)
        references[name] = dict(zip(('image', 'mask'), [p.name for p in paths]))
    def spec(b, shape, interpolation='nearest'):
        return {'index_map': b.tolist(), 'candidate_shape': list(shape),
                'interpolation': interpolation, 'outside_value': 0.,
                'position_atol_mm': 1e-4, 'intensity_atol': 1e-4, 'index_boundary_atol': 1e-9}
    stages = [
        {'source': references['source'], 'candidate': references['crop'],
         'sampling': spec(crop_map, cropped.data.shape)},
        {'source': references['crop'], 'candidate': references['coarse'],
         'sampling': spec(scale, coarse.data.shape, 'linear')},
        {'source': references['coarse'], 'candidate': references['shifted'],
         'sampling': spec(np.eye(4), coarse.data.shape)},
    ]
    reports = {}
    for name, steps in [('crop_preserved', stages[:1]), ('resample_reextract', stages[:2]),
                        ('shared_origin_fault', stages)]:
        plan = {'schema_version': '1.0', 'steps': steps}
        report = audit_plan(plan, output)
        for suffix, item in [('plan', plan), ('report', report)]:
            (output / f'{name}_{suffix}.json').write_text(json.dumps(item, indent=2) + '\n',
                                                        encoding='utf-8', newline='\n')
        (output / f'{name}.html').write_text(render_html(report), encoding='utf-8', newline='\n')
        reports[name] = report
    assert reports['crop_preserved']['feature_reuse'] == 'input_roi_preserved'
    assert reports['resample_reextract']['feature_reuse'] == 'requires_reextraction'
    assert reports['shared_origin_fault']['first_failed_checkpoint'] == 3
    assert reports['shared_origin_fault']['feature_reuse'] == 'blocked'
    print(json.dumps({name: report['feature_reuse'] for name, report in reports.items()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'outputs' / 'sampling_demo')
    build(parser.parse_args().output)
