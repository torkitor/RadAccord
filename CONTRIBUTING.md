# Contributing to RadAccord

Contributions can improve supported integration checks, documentation and reproducibility. Read [USAGE.md](USAGE.md) and [the scientific scope](docs/SCIENCE.md) first so a proposed change has an explicit input relationship and expected outcome.

## Report a reproducible problem

Use the bug-report form with the RadAccord version, original or revised profile, engine and package versions, a minimal command, and expected versus observed component decisions. Prefer one of the bundled synthetic examples or a small script generating a synthetic image/mask pair and manifest.

Public issues and pull requests must contain no patient data, patient-derived masks, account information, private absolute paths or raw worker logs. A privacy check of the released synthetic archive does not anonymise a report generated from other inputs.

## Propose a change

For a new transformation or engine, describe the permitted input domain, its mathematical obligation, an independent expected result, a valid control and a controlled violation. State when a check should abstain. A disagreement between engines alone does not establish which result is correct.

Keep changes focused. Explain the observed behaviour, resulting behaviour and validation performed. New scientific obligations need a small independent numerical or geometric oracle; documentation-only changes do not need artificial tests.

Preserve the released scientific modules and their frozen protocol manifests as historical evidence. A new profile or changed experiment needs a separately identified version and protocol, with its decisions reported alongside the relevant prior results. Do not rewrite old outcomes or regenerate historical hashes to conceal a change. Changes to unfrozen entry points or documentation should remain distinct from changes to scientific logic.

## Local checks and attribution

Follow [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md) for isolated environments. Run relevant unit tests from `software/`; core physical tests require SimpleITK in addition to the core dependencies. State which checks ran and any environment limitations. Native benchmark replication is a separate, more expensive level of validation.

Retain the [Apache License 2.0](LICENSE) and applicable third-party notices. Do not copy external implementations without their required attribution and compatible redistribution terms. Describe substantive AI assistance honestly; numerical claims still need executable evidence.

