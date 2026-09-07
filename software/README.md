# Physical-coordinate verification for radiomics integration

This package checks a declared transformation between a trusted source image and a candidate NIfTI representation. It compares physical coordinates, decoded intensities and the selected ROI, then checks applicable measurement relations and direct numerical references using a native radiomics engine.

The method requires a trustworthy source and transformation record. It cannot recover the true geometry of a source that was already mislabelled, inspect every internal state of an extraction library, or establish clinical validity.

Use `verify_refined.py` for the revised acceptance profile described below. The original `verify.py` remains available to reproduce the initial strict profile. The revision changes four PyRadiomics obligations for reindexing only; it does not alter native measurements, physical correspondence, anchors or numerical tolerances.

## Supported inputs

- Three-dimensional, finite, real-valued NIfTI images with spatial units explicitly set to millimetres.
- Orthogonal voxel axes, including anisotropic spacing and oblique orientation; shear is outside the contract.
- An integer label mask and an explicitly selected positive label. Image and mask geometry must agree.
- A full-grid signed axis permutation or flip with its index map and updated affine; equivalent intensity encoding or relabelling of the selected ROI; or a declared positive spatial scale or affine intensity transformation.

Reindexing preserves the same sampled physical object. Spatial scaling and intensity transformation are separate, covariant controls that change the object or its values according to specified laws. Cropping, interpolation and arbitrary deformations are not covered by the full-grid correspondence contract.

The adapters use unfiltered three-dimensional extraction, with no requested resampling or intensity normalisation. Feature definitions and discretisation remain native to each engine. There is no cross-engine feature-equality requirement. The MIRP adapter's modality, discretisation and nonnegative-ROI restriction are specified in [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## Environments

Run `verify_refined.py`, `benchmark.py` and `validation_refinement.py` in a core environment containing NumPy and NiBabel. Use separate Python environments for PyRadiomics and MIRP, passing the relevant executable explicitly. The programs do not install or change either engine. Run-specific package versions are recorded by `adapters.py --environment` and the benchmark environment manifests.

The recorded core environment uses Python 3.13.5 with NumPy 2.2.6 and NiBabel 5.3.3. In an isolated core environment, install these two dependencies with:

```text
python -m pip install -r requirements-core.txt
```

Native-engine versions, their separate Python environments and the two engine-specific requirements files are listed in [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

Commands below are run from the package directory. The engine paths illustrate environments within that directory; substitute your own executable. On Windows the executable is typically `.venv-pyradiomics/Scripts/python.exe`; on POSIX systems it is typically `.venv-pyradiomics/bin/python`.

## Make a small synthetic example

Save and run this example with the core interpreter:

```python
from pathlib import Path
import json
from physical_contracts import phantom, transform, write_frame

directory = Path("example")
source = phantom(0)
candidate, transformation = transform(
    source, "reindex", perm=(2, 0, 1), signs=(-1, 1, 1)
)
write_frame(source, directory, "source")
write_frame(candidate, directory, "candidate")
contract = {
    "source_label": source.label,
    "candidate_label": candidate.label,
    "transformation": transformation,
    "settings": {"bin_width": 25.0, "spatial_mode": "3d"}
}
(directory / "contract.json").write_text(
    json.dumps(contract, indent=2), encoding="utf-8"
)
```

Then verify the candidate using one native engine:

```text
python verify_refined.py --source-image example/source_image.nii.gz --source-mask example/source_mask.nii.gz --candidate-image example/candidate_image.nii.gz --candidate-mask example/candidate_mask.nii.gz --contract example/contract.json --engine pyradiomics --engine-python .venv-pyradiomics/Scripts/python.exe --report example/report.json
```

Use `--engine mirp` and its own interpreter to assess the same declared transformation through the second adapter. Passing one engine does not imply passing another configuration or implementation.

## Read the decision

| CLI result | Exit code | Interpretation |
|---|---:|---|
| `applicable_obligations_satisfied` | 0 | The applicable obligations passed within their declared tolerances; inspect the report for individual abstentions. |
| `violated` | 1 | At least one required check failed, or required extraction content was unavailable or nonfinite. |
| `not_applicable` | 2 | A required relation does not apply to the declared transformation or settings. |
| `unavailable` | 2 | The supported input or execution conditions could not be established. |

The JSON report retains geometry checks, maximum coordinate and intensity discrepancies, ROI agreement, per-feature relations, numerical anchors and native extraction records. It identifies the revised profile and preserves `initial_relations`, including the original mesh comparisons. An unassigned law is an abstention, not a passed feature. A passing comparison is not a claim that every returned feature is correct or useful for modelling.

## Why the acceptance profile was revised

The initial frozen challenge used 64 new phantoms, seeds 1000–1063. PyRadiomics produced strict relation alerts in 36 of 3200 equivalent representations, concentrated in one phantom and four mesh-derived measurements: MeshVolume, SurfaceArea, SurfaceVolumeRatio and Sphericity. Their geometric definitions are invariant; the observation does not establish an upstream software defect or mathematical non-invariance.

The revised profile withholds these four obligations only for PyRadiomics reindexing. Their values and initial diagnostics remain visible. Equivalent encoding and label-remapping checks, physical scaling and intensity laws, anchors, the transport witness and the MIRP profile are unchanged.

A separately frozen follow-up used 32 new phantoms, seeds 2000–2031, including 16 with a prescribed alternating binary-face enrichment. Of 1600 equivalent representations, 1598 were analysable: the revised profile produced no alerts, while the original profile produced 384. Two files, `2015_R06` and `2015_R07`, were outside the declared qform/sform agreement domain and were retained as unavailable. The combined revised verifier detected all 256 injected transport violations. This follow-up tests new inputs after a known profile revision, not unseen fault families or clinical performance. A transport violation can coexist with mathematically correct invariant feature values.

The initial 16-file freeze and the follow-up freeze covering those files plus three additions remain distinct. See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for commands, planned versus executed counts, and interpretation of both phases. The completed MIRP evaluation retained all 4608 calls: 0/3200 equivalent-representation alerts, 256 covariant controls satisfying assigned laws and 64 changed-bin-width controls abstaining. The witness detected 512/512 injected transport violations; feature laws detected 384/512 and anchors 320/512. All 512 repeated inputs produced identical feature mappings; repeat comparison detected none of the transport violations. No native extraction, schema or finiteness failures occurred.

## Use your own images

Keep an unmodified source image and mask. Produce the candidate through the conversion you intend to evaluate and record the transformation at that stage. Supply the source and candidate paths, labels and contract to `verify_refined.py`; replacing the synthetic generator is unnecessary.

`index_map` maps candidate indices to source indices. `world_map` describes the intended physical transformation; both are homogeneous 4×4 matrices. `intensity_gain` and `intensity_offset` specify the intended decoded-intensity relation. Keep extraction settings fixed unless the comparison is deliberately outside the relation. Do not infer a convenient transformation from the already processed candidate merely to make a discrepancy disappear.

Image processing and extraction run locally. Reports contain measurements derived from the supplied inputs. Native records redact known input paths, but raw benchmark worker logs may contain environment paths or other library messages; keep those logs private and inspect any reports before sharing results from your own data. For benchmark replication, environment recording, fixed tolerances and interpretation of reserved cases, see [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## Licence and provenance

The package retains the Apache License 2.0 of its source repository. Third-party packages retain their own licences and attribution requirements. Public protocol files identify the transformation and fault definitions used in an evaluation; environment manifests identify the installed implementations. The injected faults belong to the study's adapters and are not assertions of faults in the third-party libraries.

The manuscript distributes this study's software as Supplementary Software 1, a ZIP containing the source, protocol and reproducibility materials. Identify the release using its accompanying manifest. No external archive DOI is claimed here; any later repository deposit must use the identifier actually assigned to this release.
