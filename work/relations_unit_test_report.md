# Independent analytic relation tests

Date: 7 September 2026.

Created `software/tests/test_relations.py` using standard-library `unittest`. Production code was not changed by this test task. No extractor was run and no development, held-out, clinical, or previous-paper data was read.

Final verification: **15 test methods passed**, including parameterized subcases for both native feature naming schemes. Runtime reported by unittest: 0.004 s, excluding interpreter/import startup.

Command from the workspace root:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest discover -s 'manuscript\er\p2_standalone_2026-09-07\software\tests' -p test_relations.py -v
```

Expectations use a three-voxel calculation with intensities `[1,2,4]`, individual voxel volume 24 mm³, ROI volume 72 mm³, energy 21 and population variance 14/9. Calibration `I'=2I+3` gives `[5,7,11]` and energy 195 directly. These expectations do not call the production anchor function or import its law maps. A separate four-point noncoplanar domain fixture supports the tests of conditional MIRP measures.

Covered behavior:

* Cubic spatial response of voxel volume and PyRadiomics TotalEnergy; unchanged volume fails positive scale response.
* A consistent 1.02 volume multiplier satisfies the scale relation but fails the independent absolute volume anchor.
* Affine first-order response, including the nonzero energy cross-term; multiplying energy by ROI volume is rejected.
* Changed configuration abstains and contributes zero successful feature checks.
* Zero intensity sum, constant intensity, insufficient points, and planar geometry abstain for the corresponding MIRP measures.
* Regular domains evaluate those measures; they are not indiscriminately excluded.
* Domain predicates use the independently supplied domain even when reported mean, variance and PCA axes are deliberately false. Missing independent domain information abstains.
* Required observed values that are missing, null, NaN or infinite fail; nonfinite reference values and an empty reference fail. The same missing/nonfinite controls apply to absolute anchors.

The initial source-derived applicability concern was reported to the root agent. Root added the independent `domain` argument and changed production callers; the tests were then adapted and revalidated. No unresolved failure was observed in the tested cases. Checking the complete required feature schema is a separate production change owned by root and is not claimed as covered here.
