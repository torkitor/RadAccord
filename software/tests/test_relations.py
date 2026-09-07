"""Analytic contract tests; no extractor, phantom set, or held-out data is used."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from relations import check_anchors, compare_features


# Three selected voxels with intensities [1, 2, 4] and individual volume
# 2 x 3 x 4 = 24 mm^3. These exact expectations do not use production anchors.
ANCHORS = {
    'mean': 7 / 3, 'minimum': 1., 'maximum': 4., 'variance': 14 / 9,
    'energy': 21., 'voxel_volume': 72., 'n_voxels': 3,
}
# Separate domain fixture: four noncoplanar voxel centres (a tetrahedron), with
# intensities [1, 2, 4, 5]. Rank is supplied independently of reported axes.
REGULAR_DOMAIN = {'mean': 3., 'variance': 2.5, 'n_voxels': 4, 'full_rank_roi': True}
NATIVE = {
    'pyradiomics': {
        'mean': 'original_firstorder_Mean',
        'minimum': 'original_firstorder_Minimum',
        'maximum': 'original_firstorder_Maximum',
        'variance': 'original_firstorder_Variance',
        'energy': 'original_firstorder_Energy',
        'voxel_volume': 'original_shape_VoxelVolume',
    },
    'mirp': {
        'mean': 'stat_mean', 'minimum': 'stat_min', 'maximum': 'stat_max',
        'variance': 'stat_var', 'energy': 'stat_energy',
        'voxel_volume': 'morph_vol_approx',
    },
}
SCALE_TWO = {'kind': 'scale', 'parameters': {'scale': 2.}}
IDENTITY = {'kind': 'identity'}
CALIBRATE = {'kind': 'intensity', 'intensity_gain': 2., 'intensity_offset': 3.}


def native_features(engine, values=ANCHORS):
    return {native: values[quantity] for quantity, native in NATIVE[engine].items()}


class TestMathematicalRelations(unittest.TestCase):
    def test_volume_and_total_energy_have_cubic_spatial_response(self):
        # Each voxel becomes 4 x 6 x 8 = 192 mm^3: ROI volume is 576.
        for engine in NATIVE:
            key = NATIVE[engine]['voxel_volume']
            with self.subTest(engine=engine):
                result = compare_features(engine, {key: 72.}, {key: 576.}, SCALE_TWO, 3)
                self.assertEqual(result['status'], 'satisfied')
                unchanged = compare_features(engine, {key: 72.}, {key: 72.}, SCALE_TWO, 3)
                self.assertEqual(unchanged['status'], 'violated')

        # TotalEnergy is 21 * ONE voxel volume, not 21 * ROI volume.
        key = 'original_firstorder_TotalEnergy'
        result = compare_features('pyradiomics', {key: 504.}, {key: 4032.}, SCALE_TWO, 3)
        self.assertEqual(result['status'], 'satisfied')

    def test_consistent_two_percent_volume_bias_passes_law_but_fails_anchor(self):
        for engine in NATIVE:
            with self.subTest(engine=engine):
                volume = NATIVE[engine]['voxel_volume']
                biased = native_features(engine)
                biased[volume] = 73.44  # 72 * 1.02
                result = compare_features(engine, {volume: 73.44}, {volume: 587.52}, SCALE_TWO, 3)
                self.assertEqual(result['status'], 'satisfied')
                anchored = check_anchors(engine, biased, ANCHORS)
                self.assertEqual(anchored['status'], 'violated')
                self.assertEqual(anchored['features'][volume]['status'], 'violated')
                self.assertEqual(anchored['counts']['violated'], 1)
                self.assertEqual(anchored['counts']['satisfied'], 5)

    def test_intensity_calibration_matches_direct_transformed_voxels(self):
        # I' = 2I + 3 yields [5, 7, 11]: energy 25 + 49 + 121 = 195.
        # The nonzero offset makes omission of the mean cross-term detectable.
        transformed = {
            'mean': 23 / 3, 'minimum': 5., 'maximum': 11.,
            'variance': 56 / 9, 'energy': 195., 'voxel_volume': 72.,
        }
        for engine in NATIVE:
            with self.subTest(engine=engine):
                result = compare_features(engine, native_features(engine),
                                          native_features(engine, transformed), CALIBRATE, 3)
                self.assertEqual(result['status'], 'satisfied')
                self.assertEqual(result['counts']['satisfied'], 5)
                self.assertEqual(result['features'][NATIVE[engine]['energy']]['expected'], 195.)
                self.assertEqual(result['features'][NATIVE[engine]['voxel_volume']]['status'],
                                 'not_applicable')

    def test_energy_does_not_acquire_roi_volume_multiplier(self):
        for engine in NATIVE:
            mean, energy = NATIVE[engine]['mean'], NATIVE[engine]['energy']
            with self.subTest(engine=engine):
                result = compare_features(engine, {mean: 7 / 3, energy: 21.},
                                          {mean: 23 / 3, energy: 195. * 72.}, CALIBRATE, 3)
                self.assertEqual(result['features'][energy]['status'], 'violated')

    def test_changed_configuration_abstains_without_counting_success(self):
        for engine in NATIVE:
            with self.subTest(engine=engine):
                result = compare_features(engine, native_features(engine), {}, IDENTITY, 3,
                                          settings_equal=False)
                self.assertEqual(result['status'], 'not_applicable')
                self.assertEqual(result['counts'],
                                 {'satisfied': 0, 'violated': 0, 'not_applicable': 6})

    def test_zero_intensity_sum_makes_mirp_centre_of_mass_undefined(self):
        # All-zero ROI: no intensity-weighted centroid exists.
        reference = {'stat_mean': 0., 'morph_com': None}
        result = compare_features('mirp', reference, reference, IDENTITY, 4,
                                  domain=dict(REGULAR_DOMAIN, mean=0., variance=0.))
        self.assertEqual(result['features']['morph_com']['status'], 'not_applicable')
        self.assertEqual(result['counts']['satisfied'], 1)  # Mean only.

    def test_constant_roi_autocorrelation_is_not_a_successful_law_check(self):
        # An extractor may conventionally return 1 even though variance is zero.
        for n in (1, 3):
            with self.subTest(n=n):
                reference = {'stat_var': 0., 'morph_moran_i': 1., 'morph_geary_c': 1.}
                result = compare_features('mirp', reference, reference, IDENTITY, n,
                                          domain=dict(REGULAR_DOMAIN, variance=0., n_voxels=n,
                                                      full_rank_roi=False))
                for key in ('morph_moran_i', 'morph_geary_c'):
                    self.assertEqual(result['features'][key]['status'], 'not_applicable')
                self.assertEqual(result['counts']['satisfied'], 1)  # Variance only.

    def test_planar_roi_ellipsoid_densities_are_not_applicable(self):
        reference = {
            'morph_pca_maj_axis': 4., 'morph_pca_min_axis': 2., 'morph_pca_least_axis': 0.,
            'morph_vol_dens_aee': None, 'morph_area_dens_aee': None,
        }
        result = compare_features('mirp', reference, reference, IDENTITY, 4,
                                  domain=dict(REGULAR_DOMAIN, full_rank_roi=False))
        for key in ('morph_vol_dens_aee', 'morph_area_dens_aee'):
            self.assertEqual(result['features'][key]['status'], 'not_applicable')
        self.assertEqual(result['counts']['satisfied'], 3)  # Three lengths only.

    def test_regular_mirp_domains_are_checked_and_not_blanket_excluded(self):
        reference = {
            'stat_mean': 3., 'stat_var': 2.5,
            'morph_com': .25, 'morph_moran_i': .2, 'morph_geary_c': .8,
            'morph_pca_maj_axis': 4., 'morph_pca_min_axis': 2., 'morph_pca_least_axis': 1.,
            'morph_vol_dens_aee': .7, 'morph_area_dens_aee': 1.5,
        }
        observed = dict(reference, morph_com=.5, morph_pca_maj_axis=8.,
                        morph_pca_min_axis=4., morph_pca_least_axis=2.)
        result = compare_features('mirp', reference, observed, SCALE_TWO, 4,
                                  domain=REGULAR_DOMAIN)
        self.assertEqual(result['status'], 'satisfied')
        for key in ('morph_com', 'morph_moran_i', 'morph_geary_c',
                    'morph_vol_dens_aee', 'morph_area_dens_aee'):
            self.assertEqual(result['features'][key]['status'], 'satisfied')
        observed['morph_com'] = .25
        result = compare_features('mirp', reference, observed, SCALE_TWO, 4,
                                  domain=REGULAR_DOMAIN)
        self.assertEqual(result['features']['morph_com']['status'], 'violated')

    def test_mirp_domain_cannot_be_inferred_from_extractor_outputs(self):
        reference = {
            'stat_mean': 0., 'stat_var': 0.,
            'morph_pca_maj_axis': 0., 'morph_pca_min_axis': 0., 'morph_pca_least_axis': 0.,
            'morph_com': .25, 'morph_moran_i': .2, 'morph_geary_c': .8,
            'morph_vol_dens_aee': .7, 'morph_area_dens_aee': 1.5,
        }
        # Deliberately false reported statistics/axes must not turn failures of
        # otherwise applicable laws into abstentions. Anchors assess them too.
        observed = dict(reference, morph_moran_i=.4, morph_geary_c=.4,
                        morph_vol_dens_aee=1.4, morph_area_dens_aee=3.)
        result = compare_features('mirp', reference, observed, SCALE_TWO, 4,
                                  domain=REGULAR_DOMAIN)
        for key in ('morph_com', 'morph_moran_i', 'morph_geary_c',
                    'morph_vol_dens_aee', 'morph_area_dens_aee'):
            self.assertEqual(result['features'][key]['status'], 'violated')

    def test_missing_independent_mirp_domain_abstains(self):
        reference = {
            'morph_com': .25, 'morph_moran_i': .2, 'morph_geary_c': .8,
            'morph_vol_dens_aee': .7, 'morph_area_dens_aee': 1.5,
        }
        result = compare_features('mirp', reference, reference, IDENTITY, 4)
        self.assertEqual(result['status'], 'not_applicable')
        self.assertEqual(result['counts'],
                         {'satisfied': 0, 'violated': 0, 'not_applicable': 5})

    def test_missing_or_nonfinite_required_observed_values_fail(self):
        for engine in NATIVE:
            energy = NATIVE[engine]['energy']
            for actual in ('missing', None, math.nan, math.inf, -math.inf):
                with self.subTest(engine=engine, actual=actual):
                    observed = {} if actual == 'missing' else {energy: actual}
                    result = compare_features(engine, {energy: 21.}, observed, IDENTITY, 3)
                    self.assertEqual(result['status'], 'violated')
                    self.assertEqual(result['features'][energy]['status'], 'violated')

    def test_nonfinite_required_reference_values_fail(self):
        for engine in NATIVE:
            energy = NATIVE[engine]['energy']
            for value in (None, math.nan, math.inf, -math.inf):
                with self.subTest(engine=engine, reference=value):
                    result = compare_features(engine, {energy: value}, {energy: 21.}, IDENTITY, 3)
                    self.assertEqual(result['status'], 'violated')

    def test_empty_reference_cannot_succeed(self):
        for engine in NATIVE:
            with self.subTest(engine=engine):
                result = compare_features(engine, {}, {}, IDENTITY, 3)
                self.assertEqual(result['status'], 'violated')

    def test_absolute_anchors_reject_missing_and_nonfinite_values(self):
        for engine in NATIVE:
            energy = NATIVE[engine]['energy']
            for actual in ('missing', None, math.nan, math.inf, -math.inf):
                with self.subTest(engine=engine, actual=actual):
                    observed = native_features(engine)
                    if actual == 'missing':
                        del observed[energy]
                    else:
                        observed[energy] = actual
                    result = check_anchors(engine, observed, ANCHORS)
                    self.assertEqual(result['status'], 'violated')
                    self.assertEqual(result['counts']['violated'], 1)


if __name__ == '__main__':
    unittest.main()
