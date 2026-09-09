# Reproducing the native integration evidence

The two native evaluations are preserved in separate immutable archives. The first is development/calibration; the second is calibration-informed reevaluation on the same inputs. Neither is independent clinical validation. Later command-line and package-version changes do not replace either scientific snapshot.

## Verify the historical archives and current implementation separately

From the current repository root, using Python 3.10 or later:

```sh
python -B scripts/verify_native_freeze.py --archives-only
python -B scripts/verify_prospective_freeze.py
```

The first command reads the ZIP files without extracting them and verifies their pinned SHA-256 values, every manifest entry, and the embedded scientific freezes: 15 frozen files in calibration and 27 in refinement. Its explicit archives-only mode makes no claim that current source files remain identical to rc2. The second command checks the new implementation and protocol against the separately identified prospective freeze. Omitting archives-only retains the strict rc2 source-identity check and correctly rejects the changed 1.3.0 implementation.

The retained `protocol/native_freeze.json` and `protocol/native_refinement_freeze.json` are unchanged provenance pointers to the archived studies. The final release manifest binds all distributed files; the prospective freeze binds the declared new implementation, preparation and analysis. Neither integrity check by itself establishes scientific validity or completed remote CI.

| Archive | SHA-256 | Payload entries excluding manifest |
|---|---|---:|
| `data/RadAccord-native-calibration-1.zip` | `a3e2bff93996884ca8f8c31a38dbe8f1bb75acf2e011509e4d06ca9cbfd1532f` | 32 |
| `data/RadAccord-native-refinement-2.zip` | `d8780b56b63c50e75631fa63ac0cb68874c60357d9ceb8828cf3d47b27ce6bb5` | 45 |

## Reproduce calibration from its own snapshot

After the archive verification above, extract to a fresh directory:

```sh
python -m zipfile -e data/RadAccord-native-calibration-1.zip outputs/native_calibration
cd outputs/native_calibration/RadAccord-native-calibration-1
python -B scripts/verify_native_freeze.py
python -B -m unittest discover -s scripts/tests -p test_native_summary.py
python -B -m scripts.summarize_native_study --run results/native_integration/mirp --run results/native_integration/pyradiomics --out reproduced_summary
```

The eight files in `reproduced_summary` must be byte-identical to `results/native_integration/summary_first_development`. The archive includes its own original verifier and summarizer. Using current scientific sources to replay an old freeze would correctly fail the identity check.

The initial plan has 62 pairs per engine. MIRP retained 62 attempts and completed 61; PyRadiomics retained 51 complete attempts before interruption. The next PyRadiomics slot has no persisted result, and ten subsequent slots were not reached. Its cause is undetermined. The archive preserves all 113 case records and the interruption ledger; it fabricates no measurements for the eleven unrecorded slots.

## Reproduce refinement from its own snapshot

Return to the current repository root and extract the second archive to a fresh directory:

```sh
python -m zipfile -e data/RadAccord-native-refinement-2.zip outputs/native_refinement
cd outputs/native_refinement/RadAccord-native-refinement-2
python -B -m unittest scripts.tests.test_native_refinement_summary
python -B scripts/summarize_native_refinement.py --run results/native_refinement/mirp --run results/native_refinement/pyradiomics --freeze protocol/native_refinement_freeze.json --out reproduced_summary
```

The eight generated files must be byte-identical to `results/native_refinement/summary`. The new summarizer defaults to `protocol/native_refinement_freeze.json` and accepts only phase `native-refinement-2`, candidate `1.2.0rc2`. The explicit `--freeze` above makes the binding visible. Summary generation requires no clinical images or native radiomics installation and never repeats extraction.

The inherited frozen summarizer expected five checking-source hashes, whereas rc2 reports include a sixth, `numerics`. A separate analysis compatibility correction was recorded at 2026-09-09 13:12:19 UTC, after native evaluation began and before the refinement records were summarized. `protocol/native_refinement_analysis.json` binds the corrected summarizer and its three integrity tests; its SHA-256 is `cef8976136b9a2797e2c753ddf5ef7de0ae5164a895a874c862121eca7b1223e`. This is a summary compatibility correction after native evaluation began; no change to inference, native thresholds, source/configuration or raw data. The original frozen summarizer remains intact.

The rc2 evaluation completed all 124 planned pairs and preserved their native outputs exactly. Pair outcomes are 47 satisfied, 11 indeterminate and four unavailable for MIRP, and 52 satisfied, eight indeterminate and two unavailable for PyRadiomics. There are zero violated pairs, zero incomplete attempts and zero missing slots in this phase. The 248 checkpoints have separate denominators: MIRP observes one checkpoint per pair, PyRadiomics three. The eight PyRadiomics indeterminate pairs must not be confused with its three indeterminate final feature-input checkpoints. Abstentions and unsupported profiles remain in the denominator.

The 22 inputs comprise eight synthetic volumes, twelve previously used public MRI volumes and two previously used public CT volumes. Public image IDs do not establish independent patients. Label 1 is used in the native study, unlike the earlier union-of-positive-label sampling experiment. Source data and configuration hashes are in the plan and original records. Native extraction requires the external image releases and the exact engine environments listed in the respective freeze; raw clinical images and private paths are not distributed here.

## Interpretation and later interface changes

Refinement changes are documented in `protocol/native_refinement.md`: source-derived numerical uncertainty, compatible MIRP/pandas versions, fixed bin count 32 for MRI/synthetic PyRadiomics inputs, retained CT bin width 25, and a subprocess controller with a 300-second per-pair limit. Because the extraction configuration changes, cross-phase feature equality is not an endpoint. The numerical envelope is conditional on its stated arithmetic assumptions; it is not a formal certificate for an entire backend.

The scientific evaluation is rc2. The subsequent rc3 CLI change converts file-path objects to strings at the MIRP call boundary; its interface tests are separate from the archived scientific evaluation. CLI repair and package-version metadata do not retrospectively amend rc2 results. The complete current release is verified by its own manifest and release QA receipt.

Native-output preservation means the observer returned the producer values unchanged. It does not establish measurement correctness, feature finiteness, clinical utility, outcome prediction or cross-engine equivalence. Timing summaries are descriptive: baseline extraction precedes audited extraction, and process startup contributes to total pair time. They do not establish a causal overhead multiplier. These are local Windows checks; this document does not assert Linux or GitHub Actions success for the candidate.

## Earlier full-grid and sampling evidence

From the current repository root:

```sh
python -B scripts/restore_records.py
python -B reproduce_archived.py --output outputs/full_grid_replay
python -B scripts/verify_sampling_freeze.py
```

The first command restores only the twenty hash-verified legacy `work/**/*.jsonl` records from the immutable 1.0.0 archive. These large generated records are ignored and are not added to the release manifest. The legacy replay verifies ten archived outputs byte for byte; it does not regenerate images or rerun native extraction. The sampling verifier checks the retained 16-file freeze and its source relocation. All replay commands require a fresh output directory and preserve archived records.
