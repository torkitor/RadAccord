# A documented NIfTI export regression, reproduced independently

This experiment reproduces the oblique-orientation export defect reported in
[MIRP issue 124](https://github.com/oncoray/mirp/issues/124) and corrected in
[MIRP 2.4.2](https://github.com/oncoray/mirp/releases/tag/v2.4.2). It uses actual
released MIRP 2.4.1 and 2.4.2 packages, with no injected fault or altered producer
source. It tests the file-writing boundary. It does not extend the coverage of
the separate MIRP 2.5.0 adapter, which observes native objects after decoding and
extraction.

## Source, observation and comparison

Three analytical images have dimensions 11 × 13 × 9, spacing 0.8 × 1.3 × 2.1 mm,
and a nonzero RAS origin of (27.5, −61.25, 14.75) mm. An asymmetric intensity
field and a 157-voxel selected mask are identical across the three geometries.
The geometries are axis aligned, rotated 0.31 radians about z, and rotated about
all three axes (x = 0.23, y = −0.17, z = 0.31 radians; R = Rz Ry Rx).

The script declares these arrays and their physical affine before any MIRP
call. NiBabel writes the source image and mask with millimetre units and matching
qform/sform. MIRP reads each image into a native object, then executes its real
`write(..., file_format="nifti")` method. NiBabel independently reads both
exported files. The reference is the retained analytical affine, never an affine
reconstructed with the producer's decoder. Input NIfTI serialization error is
reported separately.

An identity index map declares that writing must preserve samples, selected
membership and physical positions. The checker compares the eight corner voxel
centres to the retained source, using the previously declared 0.0001 mm absolute
position tolerance. Intensity tolerance is 0.0001 with relative tolerance zero;
all observed image and mask arrays also receive exact equality checks. Separate
pairwise geometry checks compare the exported image with the exported mask.
NIfTI fixtures are temporary; only JSON evidence and hashes are retained.

## Observed results

| Geometry | MIRP 2.4.1 maximum corner error, mm | 2.4.1 status | MIRP 2.4.2 maximum corner error, mm | 2.4.2 status |
|---|---:|---|---:|---|
| Axis aligned | 0.000000961096 | Satisfied | 0.000000961096 | Satisfied |
| Oblique z | 10.696383924212 | Violated | 0.000000922884 | Satisfied |
| Oblique xyz | 11.122417757163 | Violated | 0.000002073230 | Satisfied |

Image arrays and mask arrays were exactly preserved in all six exports. Exported
image and mask geometry agreed with each other in all six exports. Consequently,
array equality and image–mask alignment alone did not reveal the two historical
oblique orientation failures. Comparing physical positions with an independently
retained source did. The axis-aligned control also shows that the check does not
reject every export from the older release.

Each version was run a second time in a fresh process. All recorded fields,
including generated file hashes, were identical after excluding elapsed runtime.
These are six deterministic test cases and a repeatability check, not an estimate
of prevalence, sensitivity, clinical error, or patient-level performance. The
position tolerance was not adjusted between versions.

## Mechanism and limits

The public [fix commit 172d24964a6d8ab8b264bc32650c6f09f5635805](https://github.com/oncoray/mirp/commit/172d24964a6d8ab8b264bc32650c6f09f5635805)
changes the orientation flattening order in `GenericImage.write` before passing
the direction matrix to ITK. With J denoting axis reversal and O the stored
orientation matrix, the old expression yields J O J and the corrected expression
yields J Oᵀ J. The observed failures and correction agree with that documented
file-writing mechanism. This attribution comes from the public fix and the
controlled version comparison; RadAccord itself reports a positional
discrepancy, not an automatically diagnosed library defect.

The experiment does not extract radiomic features. It does not show that every
older MIRP operation is wrong, that every later operation is correct, or that an
in-memory extraction observer automatically checks subsequent NIfTI exports.
It illustrates why the chosen observation boundary and an independent retained
reference matter. A source derived through the same incorrect file conversion
would not provide that independence.

## Reproduction

From the repository root, use separate Python environments and install one MIRP
version in each. The following example pins the relevant scientific dependencies
to those used for the recorded reproduction; remaining MIRP dependencies are
resolved by pip. Replace the activation command as appropriate for the shell.

```text
python -m venv .venv_mirp241
# Activate .venv_mirp241, then:
python -m pip install "mirp==2.4.1" "numpy==2.2.6" "nibabel==5.3.3" "itk==5.4.6" "scipy==1.15.3" "pandas==3.0.2" "pydicom==3.0.1" "scikit-image==0.26.0"
python -B -m scripts.reproduce_mirp_nifti_regression --expected-version 2.4.1 --out reproduced/mirp_nifti_2.4.1.json

# Repeat in a separate .venv_mirp242 environment with mirp==2.4.2:
python -B -m scripts.reproduce_mirp_nifti_regression --expected-version 2.4.2 --out reproduced/mirp_nifti_2.4.2.json
```

The recorded runs used Windows and Python 3.13.5. To isolate the producer-version
change locally, two new private environments inherited the same installed
scientific dependency set, and only the specified MIRP wheel was installed into
each with `pip install --no-deps`. Existing environments were not modified. This
is a controlled reproduction with common contemporary dependencies, not a claim
to recreate the complete environment used when the original issue was reported.
Linux and macOS reproduction have not been run here.

The script rejects a wrong producer version, refuses to overwrite an existing
evidence path, records versions and implementation hashes, and exports no
clinical files or local paths. The archived observations are in
[`2.4.1.json`](../results/mirp_nifti_regression/2.4.1.json) and
[`2.4.2.json`](../results/mirp_nifti_regression/2.4.2.json).

## Recorded implementation and artifact hashes

| Artifact | SHA-256 |
|---|---|
| Reproduction script | `7d7ce0ec09978a29c31042c78f3949dd8a08930a3b317774d3a4db97209ea6fb` |
| NumPy operator checker used for these records | `3fd1162b34ee806481a2e13daad7f8ddfae0ced3f473439582a5ffa1d5a0dbf2` |
| MIRP 2.4.1 generic-image module | `f51dcffcdc53a8b3bc1f27e7060855162bba55ee73ad011bf69f4b1933e80beb` |
| MIRP 2.4.1 result | `3ebdb595ecf4676f3ea41eeb3af95d53ae6c14abd21b97f2ad3569b85e917f33` |
| MIRP 2.4.2 result | `86a18030ca12ac1fc46c44fd4d9d7c6f15d0c0ecb64ae335f120ea41cc5238f4` |

The second record also contains the MIRP 2.4.2 module hash. Each case records
hashes for the generated source and exported NIfTI image/mask, the source and
observed matrices, nominal discrepancies, ambiguity counts and complete checker
decisions.
