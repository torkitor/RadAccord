"""Synthetic PyRadiomics execution with separate, portable evidence artifacts."""
import argparse
import json
from pathlib import Path

import numpy as np
import SimpleITK as sitk

from radaccord.pyradiomics import audit_pyradiomics
from radaccord.reporting import methods_text, render_html


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New directory for JSON, HTML and methods artifacts.')
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('The output directory must be new.')
    z, y, x = np.indices((11, 15, 13), dtype=float)
    values = (100 + 7*np.sin(.4*x) + y*z/13).astype(np.float32)
    membership = ((x-6)**2/16 + (y-7)**2/25 + (z-5)**2/9 < 1).astype(np.uint8)
    image = sitk.GetImageFromArray(values)
    mask = sitk.GetImageFromArray(membership)
    image.SetSpacing((.9, 1.3, 2.1))
    image.SetOrigin((-31.2, 15.4, 26.1))
    c, s = np.cos(.2), np.sin(.2)
    image.SetDirection((c, -s, 0., s, c, 0., 0., 0., 1.))
    mask.CopyInformation(image)
    result = audit_pyradiomics(image, mask, config={
        'setting': {'binWidth': 25., 'resampledPixelSpacing': [1.1]*3},
        'imageType': {'Original': {}},
        'featureClass': {'shape': ['VoxelVolume'], 'firstorder': ['Mean', 'Variance']},
    })
    report = result['report']
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output/'evidence.json').write_text(
            json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
        (args.output/'evidence.html').write_text(render_html(report), encoding='utf-8')
        (args.output/'methods.txt').write_text(methods_text(report)+'\n', encoding='utf-8')
    print(json.dumps({'status': report['status'],
                      'checkpoints': [{'checkpoint': item['checkpoint'], 'status': item['status'],
                                       'coverage': item.get('coverage', {}).get('status')}
                                      for item in report['checkpoints']]}, indent=2))
    # Scientific values are untouched in result['features']; raw native
    # diagnostics remain separate and are not written by this example.


if __name__ == '__main__':
    main()
