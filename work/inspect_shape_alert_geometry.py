"""Post hoc read-only geometry description; does not change benchmark decisions."""
from collections import Counter
from itertools import product
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import SimpleITK as sitk

WORK = Path(__file__).resolve().parent
DIRECTORY = WORK/"heldout"
cases = {row["job_id"]: row for row in (json.loads(line) for line in (DIRECTORY/"cases.jsonl").read_text().splitlines())}
jobs = {row["job_id"]: row for row in (json.loads(line) for line in (DIRECTORY/"jobs.jsonl").read_text().splitlines())}
native = {row["job_id"]: row for row in (json.loads(line) for line in (DIRECTORY/"pyradiomics.jsonl").read_text().splitlines())}
plaquettes = {}
for seed in range(1000, 1064):
    job = jobs[f"{seed}_reference"]
    mask = np.asanyarray(nib.load(DIRECTORY/job["mask_path"]).dataobj) == job["label"]
    count = 0
    for axis in range(3):
        grid = np.moveaxis(mask, axis, 0)
        a, b, c, d = grid[:, :-1, :-1], grid[:, :-1, 1:], grid[:, 1:, :-1], grid[:, 1:, 1:]
        count += int(np.count_nonzero((a == d) & (b == c) & (a != b)))
    if count:
        plaquettes[str(seed)] = count

source_job = jobs["1026_reference"]
target_job = jobs["1026_R46"]
source = sitk.ReadImage(str(DIRECTORY/source_job["image_path"]))
source_mask = sitk.ReadImage(str(DIRECTORY/source_job["mask_path"]))
actual = sitk.ReadImage(str(DIRECTORY/target_job["image_path"]))
actual_mask = sitk.ReadImage(str(DIRECTORY/target_job["mask_path"]))
parameters = cases["1026_R46"]["spec"]["parameters"]
expected = sitk.Flip(sitk.PermuteAxes(source, parameters["perm"]), [s < 0 for s in parameters["signs"]], False)
expected_mask = sitk.Flip(sitk.PermuteAxes(source_mask, parameters["perm"]), [s < 0 for s in parameters["signs"]], False)
np.testing.assert_array_equal(sitk.GetArrayFromImage(actual), sitk.GetArrayFromImage(expected))
np.testing.assert_array_equal(sitk.GetArrayFromImage(actual_mask), sitk.GetArrayFromImage(expected_mask))
corner_error = max(float(np.linalg.norm(np.asarray(actual.TransformIndexToPhysicalPoint(index))-
                                       np.asarray(expected.TransformIndexToPhysicalPoint(index))))
                   for index in product(*[(0, n-1) for n in actual.GetSize()]))
voxel_volume = float(np.prod(source.GetSpacing()))
reference_volume = native["1026_reference"]["features"]["original_shape_MeshVolume"]
volume_groups = Counter(round((native[f"1026_R{idx:02d}"]["features"]["original_shape_MeshVolume"]-reference_volume)/voxel_volume, 6)
                        for idx in range(48))
output = {
    "scope": "Post hoc description only; frozen evaluation unchanged; no native extraction rerun",
    "reference_masks_with_checkerboard_2x2_faces": plaquettes,
    "seed1026_R46_independent_SimpleITK_array_and_mask_transport_exact": True,
    "seed1026_R46_independent_max_corner_difference_mm": corner_error,
    "seed1026_voxel_volume_mm3": voxel_volume,
    "seed1026_mesh_volume_delta_in_voxel_volume_units_by_orientation_count": dict(volume_groups),
    "interpretation": "Alternating binary 2x2 face configurations are compatible with a mesh-triangulation ambiguity explanation; this description alone does not establish an upstream defect or its exact implementation mechanism."
}
(WORK/"shape_alert_geometry_description.json").write_text(json.dumps(output, indent=2), encoding="utf-8")
print(json.dumps(output, indent=2))
