# Bounded post hoc review of the mesh-dependent alerts

The initial frozen PyRadiomics profile produced **36 output-level alerts among 3200 valid equivalent representations**, all from phantom 1026. Input transport, paired geometry and analytic anchors passed. The affected outputs were MeshVolume (36), Sphericity (36), SurfaceVolumeRatio (36), and SurfaceArea (24). The largest relative mesh-volume discrepancy was approximately 0.143%. These observations remain part of the original frozen result; they must not be erased or recast as injected input faults.

## Independent input and source evidence

A read-only scan of the 64 reference masks found exactly one alternating binary 2×2 face, in phantom 1026. None of the other 63 masks had such a face. For its most discrepant representation, an independent SimpleITK permutation/flip reconstruction matched both image and mask arrays exactly; the maximum corner-coordinate difference was 5.63 × 10⁻⁶ mm. See `shape_alert_geometry_description.json`.

PyRadiomics describes these outputs as properties of an approximate triangle mesh constructed from midpoint edge crossings and a lookup table. VoxelVolume and principal-axis features use different constructions. SurfaceVolumeRatio and Sphericity are functions of the same mesh volume and area, so their correlated alerts do not constitute four independent failures. [PyRadiomics v3.0.1 feature documentation](https://pyradiomics.readthedocs.io/en/v3.0.1/features.html#shape-features-3d).

The pinned C implementation selects triangles from a 128-row table, uses a complemented cube index with sign correction for the other configurations, and accumulates signed triangle-based volumes and surface areas. No asymptotic-decider branch is present in that inspected calculation. The source was downloaded from the v3.0.1 tag, without modifying the installed package. Its SHA-256 is `e8d56aec5b7daa1777d97d91be942952949150c058eb817582ca80d37cd1f14e`. [Pinned upstream cshape.c](https://raw.githubusercontent.com/AIM-Harvard/pyradiomics/v3.0.1/radiomics/src/cshape.c).

Ambiguous face configurations are a known issue in marching-cubes surface construction, motivating explicit disambiguation methods. This gives a relevant numerical-method context; it is not, on its own, proof of the cause of an individual implementation's output. [Nielson and Hamann, *The asymptotic decider: Resolving the ambiguity in marching cubes*, 1991](https://doi.org/10.1109/VISUAL.1991.175782); [primary paper](https://graphics.stanford.edu/courses/cs164-10-spring/Handouts/paper_p83-nielson.pdf).

## Reconstruction of the observed output classes

To test the proposed explanation, `reproduce_shape_lookup.py` reads the pinned upstream tables and reconstructs triangles for one existing representation from each observed volume class. It independently crops to the occupied bounding box and adds the native one-voxel padding. No native extractor was rerun, no source mask was edited, and no frozen output was overwritten.

| Existing case | Reconstructed mesh volume, mm³ | Triangles | Edges used only once |
|---|---:|---:|---:|
| 1026_R00 | 5090.959667768722 | 2302 | 4 |
| 1026_R01 | 5090.5051685237495 | 2304 | 0 |
| 1026_R02 | 5089.596170033803 | 2304 | 0 |
| 1026_R03 | 5083.687679849137 | 2302 | 4 |

The reconstructed volumes and areas match the archived native outputs to an absolute error of at most 1.91 × 10⁻¹¹. For the two cases with no singly used edge, every mesh edge is used twice. Across all 48 representations, each of the four volume classes contains 12 cases. This reproduction locates the observed dependence in triangle selection and signed-volume construction for this binary configuration, rather than in image transport or floating-point tolerance noise. Evidence is in `shape_lookup_reconstruction.json`.

The finding does **not** justify a general claim that PyRadiomics shape extraction is wrong, that every mesh-dependent feature is unreliable, or that every marching-cubes implementation behaves this way. It establishes that unconditional exact reindexing invariance of those four approximate mesh-derived outputs is unsupported in this tested native context. Their intended continuous geometric definitions and their discrete reconstruction are distinct levels of the contract.

## Consequence for a revised relation profile

A separately versioned profile may abstain from the four PyRadiomics mesh-derived reindexing obligations while retaining the source-aware transport witness, direct anchors and supported scalar obligations. This is an applicability refinement prompted by the first 64 phantoms, not evidence that the initial profile had no alerts. Keep its code, diagnostics and raw results unchanged and show both profiles.

Any subsequent 32-phantom evaluation must be labelled as validation of that refined profile on new phantoms, including targeted ambiguous configurations where specified. The ambiguity class and original fault mechanisms are now known; they cannot be described as unseen mechanisms in that second phase. Changing neither tolerances nor original case selection is necessary for an interpretable comparison, but does not remove the need to disclose the refinement chronology.
