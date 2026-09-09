# Roadmap and release gates

This is a proposed roadmap for the 1.2.0 release candidate. It describes work to verify, not completed external adoption or a commitment to dates.

1. **An installable, bounded release:** maintain core and separate native environments; keep the API/report schema and supported versions explicit; preserve the historical scientific archive and test the wheel outside the source checkout.
2. **Version-specific incident regressions:** reproduce documented upstream incidents with owned inputs and exact affected/fixed implementations. Separate a writer/reader regression from the native boundary profile, and keep misses and unavailable cases visible.
3. **Independent operational evaluation:** apply the [prospective protocol](EXTERNAL_EVALUATION.md), measuring installation, coverage, burden and adjudicated findings. Add maintainers and example workflows through reviewed contributions.

## Proposed gates for a stable technical release

- The release wheel installs in documented isolated environments; the supported Windows/Linux CI jobs complete their required checks, with native jobs identified separately from core tests and all skips disclosed.
- Public API signatures, report schema, exit codes, supported engine versions and explicit non-applicability rules are documented. Unsupported settings cannot silently become satisfied obligations.
- Release examples run from outside the source checkout. At least one independent user repeats a clean installation and the documented demonstration; this is installation evidence, not external scientific validation.
- The required valid controls, controlled violations and applicable version-specific regressions pass. Known incorrect acceptance cases are corrected or made explicitly unavailable before release; exclusions and remaining limitations appear in the release notes.
- Frozen artifacts retain their original hashes; new profiles, changed scientific rules and reproducibility evidence have separately identified provenance. A published version has a concrete archive and release record rather than a future or invented identifier.

Meeting these gates supports a stable **technical interface within its declared scope**. Reference-infrastructure status additionally requires sustained external use, independent evaluation, maintenance capacity and community scrutiny. No badge or release number establishes clinical validity or universal feature correctness.

