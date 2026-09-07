# Runnable verification examples

These are synthetic inputs from reserved phantom 1026. The source is trusted.
The valid reindexing preserves decoded intensity, selected ROI and physical
coordinates. Its mesh-derived features illustrate why the revised profile
withholds four reindexing obligations while retaining the initial diagnostics.
The origin fault changes the jointly assigned image and mask origin; invariant
scalar features can remain unchanged although physical correspondence fails.

Run from the `software/` directory, replacing ENGINE_PYTHON with the interpreter in a
PyRadiomics 3.0.1 environment:

```text
python verify_refined.py --source-image examples/source_image.nii.gz --source-mask examples/source_mask.nii.gz --candidate-image examples/valid_reindex_image.nii.gz --candidate-mask examples/valid_reindex_mask.nii.gz --contract examples/valid_reindex_contract.json --engine pyradiomics --engine-python ENGINE_PYTHON --report valid_report.json
python verify_refined.py --source-image examples/source_image.nii.gz --source-mask examples/source_mask.nii.gz --candidate-image examples/origin_fault_image.nii.gz --candidate-mask examples/origin_fault_mask.nii.gz --contract examples/origin_fault_contract.json --engine pyradiomics --engine-python ENGINE_PYTHON --report fault_report.json
```

The expected decisions are `applicable_obligations_satisfied` (exit 0) and
`violated` (exit 1), respectively. Individual abstentions remain in the report;
exit 0 does not verify withheld obligations. Original `verify.py` retains the
initial strict profile and reports the valid mesh example as violated.
