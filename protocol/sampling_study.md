# Declared sampling evaluation protocol

Design date: 9 September 2026. This protocol and the implementation are bound by a local, timestamped SHA-256 freeze before running the reserved synthetic seeds or clinical transformations. This is an internal analysis freeze, not public preregistration. Development observations, including boundary cases, informed the implementation. Preserve the first evaluation and record any subsequent deviation.

## Question and contribution

Can an independent witness verify common declared spatial preprocessing and distinguish fidelity of execution, source ROI coverage and the conditions for reusing previously extracted measurements? The source arrays and declaration are trusted. Expected geometry is L A_source B, with candidate-index-to-source-index map B, physical map L, candidate shape, image interpolation, mask interpolation and fill specified before candidate generation. B is never inferred from the observed candidate geometry. The NumPy witness does not invoke the SimpleITK operators used to produce the candidates.

The implementation checks finite 3D orthogonal grids in millimetres. Source selected ROIs must be nonempty; observed empty ROIs are retained. Selected labels are checked as a binary membership set. This is a discrete sampling contract, not reconstruction of unknown continuous anatomy. Source ROI voxel-centre coverage of the destination field of view is reported separately; it is not continuous anatomical coverage or preservation of an unspecified filter neighbourhood.

## Development and numerical policy

Development uses constructed constant and affine fields, fixed answers, oblique anisotropic grids, signed intensities, boundary and empty-mask cases, and seeds 30000–30011 only. The production witness and independent SimpleITK candidates were developed on these fixtures. A separate adversarial half-voxel development experiment is retained even when nominal implementation choices differ.

The position tolerance is 0.0001 mm, measured as maximum Euclidean separation of voxel-centre corners; the intensity tolerance is 0.0001 decoded units. Neither is a clinical equivalence margin. Image–mask pairs must also satisfy the physical corner tolerance at file boundaries. Shape and selected label correspondence are otherwise exact.

Source support in each axis is [-0.5, size-0.5); nominal nearest neighbour uses floor(q+0.5); linear interpolation clamps to edge centres inside that half-voxel rim and uses eight neighbours. The image outside value is 0 in final decoded units and the selected mask outside value is 0. Coordinates within 1e-9 source-index units of an applicable nearest-neighbour or support boundary are treated as a numerical ambiguity band. This is a fixed engineering policy, not a proven bound on all floating-point error. Where discrete alternatives yield different values, the obligation is indeterminate; observations incompatible with every alternative violate it. Intermediate intensities between admissible discrete values are not accepted. Nominal discrepancies and ambiguous/incompatible voxel counts remain in the report. An indeterminate obligation is never an accepted control or approval for reuse.

## Evaluation inputs and denominators

Reserved synthetic evaluation: 32 volumes with seeds 31000–31031 inclusive, using the frozen phantom generator and subtracting 130.125 decoded intensity units. This reuses the generator family and therefore tests new instances, not external anatomical validity.

Clinical input transfer evaluation: all 260 released labelled T1-weighted hippocampal MRI subvolumes and all 41 labelled portal-venous spleen CT volumes in the Medical Segmentation Decathlon training manifests. These are the actual archive inventories, not counts copied from an earlier paper. Inputs are publicly distributed under CC BY-SA 4.0. Archives, source manifests and header eligibility are hashed before transformations. Header-only checks found all 301 pairs eligible. Voxel finiteness, ROI occupancy and native operation availability are assessed during the evaluation; failures remain in the attempted denominator.

The MRI release contains cropped hippocampal subvolumes. Public identifiers do not establish a mapping to unique participants; the CT release likewise does not establish participant independence. The unit is the released volume, with operations nested within that volume. Report descriptive counts and volume-level distributions, without binomial patient confidence intervals or treating transformations, voxels or features as independent patients. No disease labels, clinical outcomes, prediction models or data from the separate earlier manuscript are used.

The clinical working ROI is the union of all original positive annotation labels, explicitly stored as selected label 1. Preserve original labels and source file hashes in provenance. This does not test separate preservation of each original anatomical label. No raw clinical images or local paths enter the public software package.

## Fixed candidate battery

Fourteen cases are planned per volume: seven unmodified operator controls, six faults inserted into study wrappers, and one support-policy control. Every planned ID receives completed, unavailable or not_reached status. If an operation fails, retain the exact case and phase plus subsequent unexecuted IDs. Do not replace inputs or silently reduce operation denominators.

The first control crops the selected ROI bounding box with six source voxels of margin, clipped to the source extent, and verifies it against the entire retained input. The working crop is the source for subsequent operations. Controls are: crop; identity; constant padding (lower 3,4,2 and upper 2,1,3 voxels); axis permutation (2,0,1) with first/third-axis flips; isotropic resampling to 0.8, 1 and 2 mm. SimpleITK produces candidates without calling the witness. Images use Float64 linear interpolation and selected masks use nearest neighbour. Target origin and direction are retained, with size floor((source_size-1)*source_spacing/target_spacing)+1. These target extents are declared; source ROI coverage is checked, not assumed.

The 0.8-mm grid was added using source header spacing, before clinical outcomes, to require fractional sampling for the 1-mm MRI inputs. One- and two-millimetre sampling alone can coincide with integer source indices in those volumes. All three grids remain regardless of their outcomes.

Own-wrapper faults: stale origin after crop; an 11-mm shared image–mask origin shift along RAS x; a half-source-voxel sampling displacement with unchanged declared output headers; nearest-neighbour image interpolation instead of declared linear; linear mask interpolation followed by threshold >=0.5; premature Int32 storage of interpolated intensities followed by Float64 conversion. The last four use the correct 0.8-mm output as reference. Mutation activity is declared if position/intensity change exceeds its fixed tolerance or selected labels differ; exact changes are also retained. Inactive mutations remain reported. These are engineered faults, not discovered defects in the evaluated libraries.

The support-policy control correctly crops away approximately half the selected ROI extent along axis 0. Sampling can pass while coverage and reuse remain blocked. Two constructed checkpoint examples on the first sorted ID of each dataset compare an identity chain with a shifted intermediate that is restored at the endpoint. Saved checkpoints can expose the intermediate discrepancy; endpoint-only testing cannot. This does not claim observation of unrecorded internal extractor states.

## Comparators and outcomes

Compare the same candidates using: paired image–mask shape/geometry, finiteness and ROI occupancy; source-aware declared shape/physical geometry; the frozen original full-grid RadAccord witness; and the new independent sampling witness. The original witness's unavailable/out-of-domain results are separate from violations. A complete independent sampling oracle is not claimed to be less capable than this implementation.

Tabulate satisfied, violated, boundary-indeterminate and unavailable controls by dataset and operation; active and inactive faults; violations detected by each comparator; support status and reuse decision. Do not count abstention as detection or successful verification. Report certain incompatible and nominal mismatches separately. Aggregate repeated operations descriptively and retain case-level results.

Measure isolated witness seconds, input I/O seconds, full source dimensions and working-grid dimensions. Report runtime distributions by modality and operation; they depend on these inputs and hardware and are not a general speed guarantee. Direct occupied-voxel volume, mean and population variance describe the consequences of sampling; they are not evidence of clinical utility or predictive harm.

## File boundary and native feature subset

Roundtrip all 32 reserved synthetic volumes and all 14 cases for the first three lexicographically sorted IDs in each clinical manifest. IDs are selected before outcomes, without replacement if a source or operation fails. Save Float64 NIfTI images and integer selected masks with millimetre units and coded qform/sform, reload them, and compare evidence with the in-memory result. Keep roundtrip changes and unavailable results explicit.

For the same six clinical volumes retain five roles: working source crop; correct 0.8-, 1- and 2-mm outputs; and the wrong-image-kernel output. This prespecifies 30 image–mask pairs for native PyRadiomics 3.0.1 extraction using the unchanged archived adapter: three-dimensional shape, first-order, GLCM and GLRLM features; bin width 25; normalization disabled; internal resampling disabled; correctMask false; voxelArrayShift 0. Keep missing/nonfinite features and failures. No selection depends on feature drift.

Compare each correct resampled feature vector with its working source, and wrong-kernel output with the corresponding correct 0.8-mm output: four comparisons per selected volume, 24 planned comparisons. A difference is abs(candidate-reference) > 1e-6 + 1e-5*abs(reference), the archived scalar numerical comparison rule. This is a numerical difference count, not an equivalence test or clinical threshold. Relative differences use abs(reference) as denominator and are unavailable for a zero reference. Report finite comparable feature counts and changes in voxel volume, mean and variance; do not pool feature rows into patient-level inference. The native extraction implementation and summarization script are hashed in the freeze.

## Preservation and reporting

The original scientific archive and original protocol freezes remain byte-identical. New evidence is a separately dated extension. Preserve development, first reserved and first clinical outputs. Any post-freeze change to producer, witness, policy or analysis must be recorded with old/new hashes, reason, affected results and rerun status. An internally timestamped freeze demonstrates workflow provenance but is not an independently registered protocol.

Source documentation: Medical Segmentation Decathlon, https://medicaldecathlon.com/dataaws/ ; Antonelli et al., https://doi.org/10.1038/s41467-022-30695-9 ; Simpson et al., https://arxiv.org/abs/1902.09063 . Source archive URLs, licence and checksums accompany the release.
