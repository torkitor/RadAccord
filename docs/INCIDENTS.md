# Public incident references and verification boundaries

Checked against primary project sources on 2026-09-09. These five entries document upstream reports or fixes relevant to input geometry, ROI handling and version compatibility. **Entry 1 now has a separate version-specific synthetic reproduction; entries 2–5 remain documentary antecedents, not experimental detections.** No third-party image data were downloaded and no real-world detection rate is inferred from this ledger. Two entries concern distinct fixes in the same MIRP release; they are not independent study observations.

The current native profiles target PyRadiomics 3.0.1 and MIRP 2.5.0. A fix recorded in a release does not establish its complete affected-version range or imply that the current supported version has the historical defect. Statements about possible coverage below are conditional assessments of the implemented boundaries, not results of reproducing the original incident.

## 1. MIRP: oblique orientation when writing NIfTI

**Confirmed record.** The MIRP 2.4.2 release notes identify a fix for incorrect oblique orientation when image objects were saved as NIfTI. Issue 124 states that using the exported image and mask together can hide the discrepancy, which becomes apparent when combining an export with existing images or masks. The fix changes the orientation array's flattening order from C to Fortran before reversal and reshaping. The complete affected-version range is not established here. [MIRP 2.4.2, Fixes](https://github.com/oncoray/mirp/releases/tag/v2.4.2), [MIRP issue 124](https://github.com/oncoray/mirp/issues/124), [fix commit 172d249](https://github.com/oncoray/mirp/commit/172d24964a6d8ab8b264bc32650c6f09f5635805)

**Boundary relevance.** The current 1.3.0rc1 MIRP profile observes original-feature dispatch arguments and a later in-memory original-image/ROI export. Neither checkpoint inspects the subsequent NIfTI writer and therefore does not establish coverage of this incident. A separate read-back checkpoint against an independently retained affine could assess a resulting orientation discrepancy within the supported NIfTI domain.

**Separate reproduced regression.** The [reproduction script](../scripts/reproduce_mirp_nifti_regression.py) exercised the actual 2.4.1 and 2.4.2 writers on three owned synthetic cases. All six exported image/mask arrays remained exact and each exported pair agreed geometrically. Against the independently declared source mapping, 2.4.1 produced maximum corner errors of 10.6964 and 11.1224 mm in the two oblique cases; both were violated. The axis-aligned control was satisfied. All three 2.4.2 cases were satisfied, with maximum error 2.0733e-6 mm. [2.4.1 records](../results/mirp_nifti_regression/2.4.1.json), [2.4.2 records](../results/mirp_nifti_regression/2.4.2.json)

This is one historical writer defect reproduced across two oblique configurations with a valid control, not a cohort estimate. Its read-back observation is separate from the current MIRP 2.5.0 native in-memory adapter and from the earlier controlled-fault study.

## 2. MIRP: metadata accompanying exported masks

**Confirmed record.** The same 2.4.2 release records a correction to mask metadata exported as a dictionary for masks originating from NIfTI, NRRD or NumPy inputs. It does not enumerate the affected metadata fields. [MIRP 2.4.2, Fixes](https://github.com/oncoray/mirp/releases/tag/v2.4.2)

**Boundary relevance.** Native checks compare selected ROI membership and declared physical geometry. Incorrect exported fields used to reconstruct those quantities could cause a discrepancy or unavailable assessment. The release note alone does not show that those particular fields were affected; RadAccord does not validate every exported metadata field. The supported 2.5.0 adapter must not be labelled as a validated detector of the older export defect.

**Candidate future regression.** Identify the precise upstream patch and reproduce the affected export with a synthetic labelled mask before assigning a detection endpoint.

## 3. PyRadiomics: an ROI occupying the whole image was rejected

**Confirmed record.** Pull request 660 explains that a mask containing a single label caused an erroneous no-label `ValueError`; rejection should apply when that sole label is background zero. The fix was merged on 2020-11-17 and is listed in the 3.1.0 release notes. [PyRadiomics PR 660](https://github.com/AIM-Harvard/pyradiomics/pull/660), [PyRadiomics 3.1.0](https://github.com/AIM-Harvard/pyradiomics/releases/tag/v3.1.0)

**Boundary relevance.** If a native call aborts on this condition, the command must preserve an unavailable result. That is failure accounting, not detection of a silent processing error: the extractor already reports an exception. The adapter does not repair the native validation logic or pretend that an extraction completed.

**Candidate future regression.** A synthetic mask filled with the selected nonzero label can test failure accounting. Claiming reproduction of the published defect additionally requires documenting the affected implementation and the changed behaviour after the upstream fix.

## 4. ITK: a scale-dependent NIfTI sform invertibility check

**Confirmed record.** Issue 2674 reports downstream reading failures following an sform-selection change. PR 2701 identifies rejection of sform matrices with determinant below 10^-5, a condition dependent on the product of voxel spacings; a valid sform could then be unusable when no qform fallback was available. The fix was merged on 2021-08-20. [ITK issue 2674](https://github.com/InsightSoftwareConsortium/ITK/issues/2674), [ITK PR 2701](https://github.com/InsightSoftwareConsortium/ITK/pull/2701)

**Boundary relevance.** A reader exception is unavailable evidence, not a satisfied check. More subtly, a source read and an extraction that share the same erroneous reader can agree with one another. The current native adapter's retained SimpleITK source does not independently establish the correctness of that initial read. The file-level sampling profile also has explicit geometry applicability limits; it does not resolve contradictory spatial forms by choosing whichever one passes.

**Candidate future regression.** Retain an independently specified, well-conditioned small-voxel affine and test the actual affected/fixed reader versions. Report a rejected valid input separately from a silently misread coordinate system.

## 5. MIRP: complex-valued maximum correlation coefficient output

**Confirmed record.** MIRP 2.3.4 documents a correction concerning complex values from the co-occurrence-matrix maximum correlation coefficient. The 2.4.0 notes further clarify that the returned type could still be complex even after the earlier numerical correction. [MIRP 2.3.4, Fixes](https://github.com/oncoray/mirp/releases/tag/v2.3.4), [MIRP 2.4.0, Fixes](https://github.com/oncoray/mirp/releases/tag/v2.4.0)

**Boundary relevance.** This concerns feature computation/output type, which is outside the new native input-relation profiles. A feature digest binds returned values to an execution; it does not validate their formula or type against an independent feature oracle. A satisfied input audit cannot rule out this class of error.

**Candidate future regression.** Such a case belongs in a separately specified feature-conformance test, with a valid reference for the feature and its supported output type. It should not inflate the success count of an input-geometry audit.

## What would support a reproduced-incident claim?

Keep a distinct incident experiment with the original issue/fix link, affected and fixed commit identifiers, independently justified expected behaviour, input provenance, exact configuration, complete execution ledger and outcomes from both implementations. State whether RadAccord observed the affected boundary, abstained or had no applicable obligation. Preserve cases in which the upstream failure was already apparent, the profile could not evaluate it, or RadAccord missed it.

Fault injections inspired by these mechanisms remain controlled tests. The documentary ledger remains separate from the existing synthetic and public-image evaluation denominators. Neither source-code similarity nor a plausible mechanism alone establishes reproduction of an upstream incident.

The [prospective 1.3.0rc1 evaluation](PROSPECTIVE_VALIDATION.md) used new public source volumes. Its controlled tasks and unresolved native relationships do not add spontaneous upstream incidents to this ledger.
