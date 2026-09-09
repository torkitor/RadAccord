# Acquire and select the new clinical inputs

Run these commands from the repository root with Python 3.11 or later, NumPy
and NiBabel installed. Replace `PRIVATE_DATA_DIR` with an absolute destination
outside the repository. Replace `PUBLIC_PROVENANCE_DIR` with a new directory
for the reproducibility records, separate from the private data tree.

```text
python -B scripts/download_msd_validation.py --data-dir PRIVATE_DATA_DIR --public-output PUBLIC_PROVENANCE_DIR --transport-concurrency 32
python -B scripts/select_msd_validation.py --data-dir PRIVATE_DATA_DIR --public-output PUBLIC_PROVENANCE_DIR
```

The downloader fetches the complete official MSD Heart and Lung archives,
checks their published MD5 values against the pinned MONAI source, computes
SHA-256 hashes, and validates every TAR member before extraction. Download
concurrency changes transport only. The archives together require about 9.6 GB
before extraction; allow additional space for extracted images and temporary
files. Existing verified acquisitions can be reused only with matching local
acquisition provenance. Partial downloads and incomplete extraction staging
are retained after a failure and are never silently overwritten; use a fresh
private destination for another acquisition attempt.

The selector implements [the fixed selection protocol](../../new_cohort_selection.md).
It commits the hash-ranked first 12 training filenames per collection before
reading selected voxel arrays. Header geometry, finite values and label-1
occupancy determine eligibility; no radiomic feature, native engine or
RadAccord decision is evaluated. Missing or unreadable selected files remain
selected and receive explicit failure reasons. No replacement is permitted.
Existing selection outputs are not overwritten.

Public outputs contain source URLs, licence information, release metadata,
selected identifiers, hashes and eligibility metadata. The complete images and
`selected_inputs.jsonl` remain in the private data directory. That JSONL includes
absolute input paths for the local study harness and must not be committed or
shared as a public result. The public selector also records the proposed
label-1 bounding box with outward-rounded 10 mm context, without cropping or
resampling any image. Study preparation and evaluation require their separate
frozen protocol.

The initial acquisition used the preserved local predecessor of the public
downloader; source selection has the same hash string and eligibility rules.
Public parameterization adds explicit destinations, safe path handling and
retention of selected files whose hashes cannot be read. Acquisition timing
and transport details belong to provenance, not to a scientific result.
