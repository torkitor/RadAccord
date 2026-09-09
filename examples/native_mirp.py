"""Run a small synthetic native MIRP extraction and print only its evidence."""
import json
import numpy as np

from radaccord.mirp import audit_mirp


def main():
    # MIRP-native in-memory arrays use ZYX order and LPS geometry in millimetres.
    from mirp._images.generic_image import GenericImage
    from mirp._masks.base_mask import BaseMask
    z, y, x = np.indices((9, 11, 13), dtype=float)
    values = 20 + .3*z + .12*y*y + np.sin(.7*x)
    roi = (z-4)**2/9 + (y-5)**2/16 + (x-6)**2/20 < 1
    geometry = dict(image_origin=(0., 0., 0.), image_orientation=np.eye(3),
                    image_spacing=(1.5, 1.1, .9), image_dimensions=values.shape,
                    image_modality='mr', sample_name='synthetic_example')
    image = GenericImage(image_data=values, **geometry)
    mask = BaseMask(roi_name='synthetic_roi', image_data=roi, **geometry)
    result = audit_mirp(image, mask, config={
        'base_feature_families': ['statistical'], 'new_spacing': 1.3})
    print(json.dumps(result['report'], indent=2, allow_nan=False))
    # result['features'] is the native pandas DataFrame, without modified values.


if __name__ == '__main__':
    main()
