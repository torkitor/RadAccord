# Scientific scope and evidence

RadAccord 1.0.0 makes the expected relationship between a retained source and a candidate image explicit before radiomic feature reuse. Its intended uses are research acceptance testing after supported storage or representation changes and regression testing of input adapters. Start with the [overview](../README.md) and [runnable examples](../USAGE.md); use the [reproduction guide](REPRODUCIBILITY.md) to inspect the evidence.

## Three complementary checks

| Check | What it compares | Why it matters |
|---|---|---|
| Physical correspondence | Candidate coordinates, decoded intensities and selected ROI membership against the trusted source and declared transformation | An image and mask can share an unintended origin or direction while staying mutually aligned and producing unchanged invariant scalars. |
| Conditional measurement laws | Each candidate measurement against the value expected for its assigned transformation | Equivalent representations and intentional physical changes need different obligations: for example, volume is invariant under reindexing but scales with the cube of physical length. |
| Direct numerical anchors | Selected native outputs against mean, minimum, maximum, population variance, energy and occupied voxel volume computed directly from intended inputs | A consistent output bias can preserve a response law while disagreeing with an absolute numerical reference. |

The source and transformation declaration are trusted. Verification observes saved input files; this checkpoint does not reveal every internal extractor state. The checks complement one another, and an alert about physical correspondence does not imply that every scalar measurement is numerically wrong.

Required scalar comparisons use absolute tolerance 10⁻⁶ plus relative tolerance 10⁻⁵ against the expected value. Physical corner displacement is bounded by 10⁻⁴ mm, decoded intensity by 10⁻⁴ input units, and selected ROI correspondence is exact. These are engineering tolerances for this profile. The [complete protocol](../software/REPRODUCIBILITY.md) explains applicability and settings.

## Supported domain

Inputs are finite real-valued 3D NIfTI images in explicit millimetres, with orthogonal axes, consistent coded qform/sform geometry and an integer mask with a selected positive label. Anisotropic spacing and oblique directions are supported. Declared operations cover full-grid signed axis permutations/flips, equivalent calibrated storage, selected-ROI relabelling, positive isotropic spatial scaling and supported positive affine intensity changes.

The adapters use original unfiltered 3D features without requested resampling or normalisation. PyRadiomics 3.0.1 and MIRP 2.5.0 are compared within their own native definitions and settings; cross-engine equality is not required. The supplied MIRP MR profile uses bin size 25 and lower intensity bound zero, so its selected ROI must have nonnegative intensities.

Cropping, interpolation, shear, arbitrary deformation, signed-ROI intensities in this MIRP profile and different preprocessing need additional contracts. A satisfied report describes applicable obligations; unavailable or unassigned checks retain their own status.

## Archived controlled evaluation

Development used 12 synthetic phantoms. The initial implementation and protocol were frozen before generating 64 reserved phantoms. A separately frozen PyRadiomics follow-up then used 32 new phantoms, including 16 with prescribed boundary enrichment.

| Outcome | Initial PyRadiomics | Initial MIRP | PyRadiomics follow-up |
|---|---:|---:|---:|
| Base phantoms | 64 | 64 | 32 |
| Transport violations detected by physical correspondence | 512/512 | 512/512 | 256/256 |
| Transport violations detected by feature laws | 384/512 | 384/512 | 192/256 |
| Transport violations detected by anchors | 320/512 | 320/512 | 160/256 |
| Original-profile alerts on analysable equivalent representations | 36/3,200 | 0/3,200 | 384/1,598 |
| Revised-profile alerts on analysable equivalent representations | Not the initial evaluation | Profile unchanged | 0/1,598 |
| Equivalent attempts unavailable at the input boundary | 0/3,200 | 0/3,200 | 2/1,600 |

Sources: [initial group counts](../work/heldout/summary.json), [follow-up group counts](../work/refinement/pyradiomics_refined_summary.json), and independent [PyRadiomics](../work/independent_results_audit_pyradiomics.json), [MIRP](../work/independent_results_audit_mirp.json) and [follow-up](../work/independent_refinement_audit.json) audits. The byte-identical [1.0.0 release archive](../data/RadAccord-1.0.0.zip) contains the full JSONL measurements and decisions omitted from the browsable tree; the reproduction guide explains restoration. All initial corrupted-input repeats gave identical feature mappings: repeat comparison detected none of those transport violations.

Each initial engine completed 4,608 native calls for 4,096 cases, including one extra call for each of 512 faults. Follow-up retained 2,048 planned cases and completed 2,302 of 2,304 planned calls. The two unavailable equivalents, `2015_R06` and `2015_R07`, exceeded the fixed qform/sform agreement tolerance and were not submitted for extraction. They remain in the attempted denominator.

All 256 prescribed physical changes per initial engine, and 128 in follow-up, satisfied their assigned laws. Changed-bin-width controls (64 per initial engine; 32 in follow-up) caused explicit feature abstention. Abstentions are not successful equality checks.

## Four withheld reindexing obligations

The initial PyRadiomics alerts concerned MeshVolume, SurfaceArea, SurfaceVolumeRatio and Sphericity in one synthetic boundary configuration. The revised profile withholds these four obligations **only for PyRadiomics reindexing**. It retains their measurements and original diagnostics, as well as their assigned scaling laws. Physical correspondence, numerical anchors, tolerances and the MIRP profile remain unchanged.

There are 65 assigned reindexing equality obligations among 72 native PyRadiomics features in the revised profile; three axis-labelled measurements already lacked assigned scalar-invariance obligations. Zero revised follow-up alerts does not establish equivalence of the four withheld measurements. The reconstruction in [the geometry record](../work/shape_lookup_reconstruction.json) localises this observation; it does not establish a universal defect in a native library.

The follow-up tests new inputs after the limitation was known. Its fault mechanisms were already known, and the unchanged witness provides a regression check. Both phases are constructed coverage studies from one generator, not independent clinical populations. Their counts do not estimate clinical sensitivity, real-world error prevalence, predictive utility or patient benefit.
