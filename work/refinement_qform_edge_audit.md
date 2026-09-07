# Two retained boundary rejections in the refinement evaluation

The files for `2015_R06` and `2015_R07` were inspected without modifying their headers, input data, software or tolerance. Both have qform and sform codes 1 for image and mask; the image and mask headers agree with one another.

| Representation | Maximum qform–sform matrix-element difference | Maximum qform–sform corner difference | Maximum sform–declared corner difference |
|---|---:|---:|---:|
| 2015_reference | 8.506 × 10⁻⁸ | 0.000004343 mm | 0.000004314 mm |
| 2015_R06 | 0.000448434 | 0.021382197 mm | 0.000002255 mm |
| 2015_R07 | 0.000448434 | 0.018710685 mm | 0.000002817 mm |

The declared affine is the original pre-serialization source affine multiplied by the signed-permutation index map. The fixed agreement threshold is 0.0001 for matrix entries; both generated representations exceed it and therefore remain **outside the accepted domain and not approved**.

The specific numerical mechanism was verified in the installed NiBabel 5.3.3 source. `Nifti1Header.get_qform_quaternion` calls `fillpositive` with a threshold of 3.5762787 × 10⁻⁷ for the reconstructed scalar quaternion component squared. For R06 and R07, the stored float32 vector components give `1 − b² − c² − d² = 3.42720856 × 10⁻⁸`, below that threshold, so the scalar component is set to zero. The ideal component from the declared affine is 0.000166795664. The resulting near-half-turn reconstruction accounts for the larger qform discrepancy; the transformed sforms still track the declared affine within 3 × 10⁻⁶ mm. This is a numerical boundary of the declared reader/format contract, not evidence of a corrupted patient image or a request to relax the threshold.

All 2048 planned cases remain in the case log. Two boundary rejections prevent native scheduling, leaving **2302 actual jobs/outputs rather than 2304 planned jobs**. All 2302 scheduled IDs have exactly one completed output; all native statuses are `extracted`. No fault activation was changed to not-applicable. The two rejected equivalent cases must not enter the approved denominator.

Detailed matrices, quaternion components and unchanged input-file SHA-256 values are in `refinement_qform_edge_audit.json`; output coverage is in `refinement_output_coverage_audit.json`.

