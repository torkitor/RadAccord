# Contributing to RadAccord

Contributions can improve supported integration checks, documentation and reproducibility. Read [installation and native entry points](docs/INSTALL.md), [declared sampling](docs/SAMPLING.md) and [the scientific scope](docs/SCIENCE.md) first so a proposed change has an explicit input relationship and expected outcome. RadAccord complements extractors and feature-reference standards; it does not certify an entire pipeline.

## Report a reproducible problem

Use the bug-report form with the RadAccord version and exact profile, engine and package versions, a minimal command, and expected versus observed component decisions. State whether the problem concerns installation, file-level sampling, a native boundary or a historical full-grid profile. Prefer one of the bundled synthetic examples or a small script generating a synthetic image/mask pair and declaration.

Public issues and pull requests must contain no patient data, patient-derived masks, account information, private absolute paths or raw worker logs. A privacy check of the released synthetic archive does not anonymise a report generated from other inputs.

## Propose a change

For a new transformation or engine, describe the permitted input domain, its mathematical obligation, an independent expected result, a valid control and a controlled violation. State when a check should abstain. A disagreement between engines alone does not establish which result is correct.

Keep changes focused. Explain the observed behaviour, resulting behaviour and validation performed. New scientific obligations need a small independent numerical or geometric oracle; documentation-only changes do not need artificial tests.

Preserve the released scientific modules and their frozen protocol manifests as historical evidence. A new profile or changed experiment needs a separately identified version and protocol, with its decisions reported alongside the relevant prior results. Do not rewrite old outcomes or regenerate historical hashes to conceal a change. Changes to unfrozen entry points or documentation should remain distinct from changes to scientific logic.

## Local checks and attribution

Follow [installation](docs/INSTALL.md) and [reproducibility](docs/REPRODUCIBILITY.md) for isolated environments. Install the package before running the new interface tests in `tests/`; native integration tests need their respective engine environment, and independent operator comparisons may also require SciPy/SimpleITK. Historical checks and benchmark replication retain their own documented commands. State which checks ran, which were skipped and any environment limitations; a core-only run does not establish native-engine compatibility.

Retain the [Apache License 2.0](LICENSE) and applicable third-party notices. Do not copy external implementations without their required attribution and compatible redistribution terms. Describe substantive AI assistance honestly; numerical claims still need executable evidence.

## Evidence and maintenance priorities

The [roadmap](docs/ROADMAP.md) distinguishes stable release gates from scientific external validation. Independent groups can contribute an installation report or follow the [prospective evaluation template](docs/EXTERNAL_EVALUATION.md). Describe their actual relationship to development rather than labelling every second execution independent. Historical incidents need the original source and a faithful version-specific reproduction; an inspired fault injection remains a controlled test.

Keep proposed changes small, include validation relevant to the changed behaviour and explain any schema/profile compatibility impact. Existing frozen outcomes remain available even when a later implementation changes a decision. Do not claim endorsement by an extractor project or a standardisation initiative without a documented basis.
