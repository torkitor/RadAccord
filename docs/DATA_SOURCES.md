# Sampling-study data sources and reproduction

The 1.1.0rc1 sampling candidate uses released Medical Segmentation Decathlon (MSD) image–annotation pairs as external inputs to a technical processing evaluation. Clinical images and derived image volumes are not included in this repository. Source manifests, acquisition provenance and pre-evaluation header checks are included as small metadata files.

The [MSD project](https://medicaldecathlon.com/dataaws/) and [AWS Open Data registry](https://registry.opendata.aws/msd/) provide the official sources. The AWS registry identifies the MONAI Development Team as manager and specifies **CC BY-SA 4.0** for the data. Cite [Antonelli et al., Nature Communications 2022](https://doi.org/10.1038/s41467-022-30695-9) and the [original dataset description](https://arxiv.org/abs/1902.09063) when using these inputs. Source metadata retain their dataset attribution and licence; the RadAccord software licence is Apache-2.0. No new permission to redistribute clinical data is implied by the software licence.

## Released inventories

| Collection | Released training pairs | Unlabelled test images | Direct official archive used |
|---|---:|---:|---|
| Task04_Hippocampus: T1-weighted MRI patches, anterior/posterior hippocampal labels | 260 | 130 | [Task04_Hippocampus.tar](https://msd-for-monai.s3-us-west-2.amazonaws.com/Task04_Hippocampus.tar) |
| Task09_Spleen: portal-venous CT, spleen annotation | 41 | 20 | [Task09_Spleen.tar](https://msd-for-monai-eu.s3.eu-west-2.amazonaws.com/Task09_Spleen.tar) |

These are the actual downloaded-release counts. A volume identifier is not proof of an independent participant, particularly for the cropped hippocampal inputs. Analyses use released volumes descriptively, with operations nested within volume. No bilateral-to-participant mapping is inferred. The study uses the union of positive annotation labels as selected label 1 and therefore does not separately validate preservation of each original anatomical label.

The training manifests are retained byte-identically as [Hippocampus metadata](../protocol/sources/Task04_Hippocampus_dataset.json) and [Spleen metadata](../protocol/sources/Task09_Spleen_dataset.json). The [acquisition record](../protocol/sources/MSD_download_provenance.json) supplies exact URLs, HTTP metadata, the pinned MONAI source and its hash. It contains no credentials or personal filesystem paths.

| Archive | Bytes | Published MONAI MD5 | Locally computed SHA-256 |
|---|---:|---|---|
| Task04_Hippocampus.tar | 28,425,216 | `9d24dba78a72977dbd1d2e110310f31b` | `282d808a3e84e5a52f090d9dd4c0b0057b94a6bd51ad41569aef5ff303287771` |
| Task09_Spleen.tar | 1,610,352,640 | `410d4a301da4e5b2f6f86ec3ddba524e` | `dfeba347daae4fb08c38f4d243ab606b28b91b206ffc445ec55c35489fa65e60` |

The expected MD5 values were verified against [MONAI datasets.py at commit 20df60253d364be69601114adae3bd609e0cb6f6](https://github.com/Project-MONAI/MONAI/blob/20df60253d364be69601114adae3bd609e0cb6f6/monai/apps/datasets.py). The SHA-256 values identify the downloaded bytes; they are not publisher-supplied SHA-256 certificates.

Header-only checks preceded clinical processing: all 301 training pairs had 3D grids, millimetre units, matching image–annotation geometries, orthogonal voxel axes and identical qform/sform matrices with codes 1/1. The complete criteria are in the [Hippocampus eligibility record](../protocol/sources/Task04_Hippocampus_header_eligibility.json) and [Spleen eligibility record](../protocol/sources/Task09_Spleen_header_eligibility.json). Header eligibility does not assert voxel finiteness, selected-label occupancy, successful processing or clinical validity.

## Verify the retained scientific freeze

Run from the repository root; Python's standard library is sufficient:

```text
python -B scripts/verify_sampling_freeze.py
```

The verifier checks the original [sampling freeze](../protocol/sampling_freeze.json), its pinned [location mapping](../protocol/sampling_freeze_locations.json), all 16 relocated frozen payloads and the original `data/RadAccord-1.0.0.zip` archive. It does not require clinical images or normalize line endings. The mapping translates historical relative locations into public repository locations without changing the payloads. The freeze is an internally timestamped pre-evaluation record, not an independently registered public protocol. This integrity check does not rerun the scientific experiment.

## Obtain and verify the external inputs

Place the two official TAR downloads in a separate sibling directory, for example `../msd-private`, outside this repository. Before extraction, the following command checks their sizes and complete SHA-256 values against the retained acquisition record. It requires Python 3.11 or later and reads each archive in bounded blocks through `hashlib.file_digest`.

```text
python -c "import hashlib,json,pathlib; root=pathlib.Path('../msd-private'); rows=json.load(open('protocol/sources/MSD_download_provenance.json'))['archives']; ok=all((root/(r['task']+'.tar')).stat().st_size==r['bytes'] and hashlib.file_digest(open(root/(r['task']+'.tar'),'rb'),'sha256').hexdigest()==r['observed_sha256'] for r in rows); print({'verified':ok}); raise SystemExit(0 if ok else 1)"
```

Continue only when both full archives match. The exact checked archives were inspected at acquisition: all member paths were validated, links/special members and duplicate destinations rejected, and regular files copied individually; no untrusted archive extraction was used. Extract the verified archives into the same external directory using a TAR utility:

```text
tar -xf ../msd-private/Task04_Hippocampus.tar -C ../msd-private
tar -xf ../msd-private/Task09_Spleen.tar -C ../msd-private
```

Apple metadata entries in the archives are not study inputs. Use only each task's original `dataset.json` training list. The test images have no supplied training annotations and are not part of this evaluation. Keep all raw and derived image volumes outside the software repository.

## Reproduce clinical processing

The clinical driver was run with Python 3.13.5, NumPy 2.2.6, NiBabel 5.3.3 and SimpleITK 2.5.3. Use an environment separate from the older native PyRadiomics environment described in [NATIVE_FEATURES.md](NATIVE_FEATURES.md).

```text
python -m pip install -r software/requirements-core.txt SimpleITK==2.5.3
python -B scripts/run_sampling_study.py --dataset-root ../msd-private/Task04_Hippocampus --dataset-root ../msd-private/Task09_Spleen --native-input-output ../msd-private/native-inputs --output results/reproduced_sampling_clinical
```

Run the retained [study protocol](../protocol/sampling_study.md) as written: all 260 MRI and 41 CT training volumes are attempted, without selection by processing outcome. The native-input option saves five roles for the first three lexicographic volume IDs per collection; it does not itself extract radiomic features. Every selected role remains private, with a private input manifest for the separate native extraction step.

Use a fresh output directory for each independent run. Retain unavailable and unexecuted cases, inactive perturbations and boundary indeterminacy. A completed process is not evidence that every sampling obligation passed. The engineered wrapper faults remain distinct from unmodified SimpleITK controls, and correct resampling is permitted to change quantitative measurements. See [SAMPLING.md](SAMPLING.md) for interpretation and [NATIVE_FEATURES.md](NATIVE_FEATURES.md) for the 30-pair native subset.
