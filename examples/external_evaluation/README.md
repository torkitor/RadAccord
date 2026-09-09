# Run an independent evaluation

This kit makes an external evaluation recordable before any outcome is known.
It contains empty templates, not results or evidence of participating sites.
There is no upload endpoint or automatic data transmission.

1. Install the exact release in a new environment using [INSTALL](../../docs/INSTALL.md).
   Keep the wheel SHA-256, Python/OS and native package versions. Record every
   installation attempt, including failures, in `attempts.csv`.
2. Run the documented synthetic example first. Record elapsed setup time,
   assistance and whether the report was interpretable. A successful example is
   an installation result, not validation of your clinical pipeline.
3. Copy `evaluation_plan.json` into a private study directory. Set the study code,
   independence statement, engine/configuration, consecutive sampling window or
   fixed attempt count, source retention, comparators and two adjudicators.
   Replace every null before starting; save a timestamped hash of the final plan.
4. Follow [the external protocol](../../docs/EXTERNAL_EVALUATION.md). Keep the
   existing native computation and QA. Apply the audit in shadow mode and retain
   all attempts, including unsupported settings, abandoned runs and uncertainty.
5. For each reviewed discrepancy, complete `adjudication.csv` against independent
   evidence. Record the original verdict before any correction and rerun, and
   keep unresolved disagreements. A native feature change is not itself an error.
6. Keep images, masks, paths, raw logs and any linking key at your institution.
   Review identifiers and free text before sharing these derived tables. Share
   only material permitted by the data source and institutional arrangements.

The templates distinguish computational decisions, independent adjudication and
operational action. Do not recode `indeterminate` or `unavailable` as a pass; do
not discard a failed attempt or count repeated checkpoints as independent people.
Reported review times must be observed by real users. Software-generated or
author-estimated times are not substitutes.

No developer contact is necessary to run the released package or this protocol.
Public questions and minimal synthetic bug reproductions can use the repository's
issue templates. Submission of an issue does not enroll a group in a study.
