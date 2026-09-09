# Proposed external evaluation protocol

**Status: prospective protocol template, not a completed external validation.** The current project evaluation and development harness do not establish independent adoption, prevalence of processing defects or clinical benefit. Participating groups, dates, sample sizes and resources remain to be specified before this protocol is run. This document authorises no data transfer or contact with a third party.

RadAccord is a complementary check of declared processing relationships. It does not replace IBSI feature references, PyRadiomics, MIRP, routine imaging QA or a clinical validation study.

## Objectives and design

Assess whether independent groups can install the released package, apply a supported profile to their existing processing, interpret the evidence and identify actionable discrepancies beyond their existing checks. Distinguish four quantities: input-relation verification, feature-value change, an adjudicated implementation/configuration error, and an operational correction. None is a substitute for demonstrated patient benefit.

The target design includes at least three participating groups, with at least two having no role in RadAccord's implementation. This is a recruitment target, not a claim about participants already involved. Record each group's contribution to development, configuration and adjudication. Independence of authorship, independence of the producer/reference implementation and independence of study observations are separate properties.

Use two distinct components:

1. **Consecutive prospective processing:** include every attempted run in a fixed interval or a fixed number of consecutive attempts chosen before results are inspected. Select existing CT/MRI workflows before viewing audit outcomes. Run in shadow mode; clinical decisions and existing production outputs remain the responsibility of the site.
2. **A historical incident bank:** use documented failures that occurred before selection for this evaluation. Pin affected/fixed versions and reproduce the original operation with shareable synthetic inputs where possible. This enriched bank evaluates mechanisms; it cannot estimate their operational prevalence. Keep it separate from prospective denominators and from constructed fault injections.

## Freeze and reference decisions

Before evaluation, each group records its package/wheel hash, profile, engine environment, intended operations, source provenance, baseline QA, eligibility rules and tolerances. Declare the intended grid, interpolation, ROI treatment and observation points from workflow configuration rather than reconstructing them from the candidate being tested. Include frozen examples of legitimate operations, invalid operations and expected abstentions.

The baseline is the group's actual QA, supplemented by explicit paired image–mask and source-aware geometry checks where applicable. Document the baseline's observed boundary and available source information. Do not compare a source-aware RadAccord check only against a weaker baseline denied access to the same retained source.

Adjudication requires the retained inputs, intended operation and an independent numerical/geometric reference or a documented native patch and before/after reproduction. Two reviewers assess the discrepancy independently of RadAccord's verdict where practicable; record disagreements and unresolved cases. Agreement between two libraries is supporting evidence, not automatically a ground truth. A repeat run using the same faulty reader is not an independent reference.

## Prespecified endpoints and denominators

| Endpoint | Required numerator and denominator |
|---|---|
| Installation and first successful check | Successful clean installations and completed synthetic demonstrations / all installation attempts, including abandoned attempts. Record Python/OS/engine stack, assistance required and elapsed time to first interpretable report. Separate dependency-download time from other setup time. |
| Workflow coverage | Runs with an applicable completed profile / all attempted runs. Report excluded-before-run workflows separately with their prespecified exclusion reasons. Preserve unsupported operations and incomplete executions. |
| Decisions and review burden | Satisfied, violated, indeterminate and unavailable runs / all attempts, plus checkpoint counts reported separately. Record manual review time and the proportion of accepted baseline runs blocked by RadAccord. |
| Incremental findings | Independently adjudicated errors additionally identified with RadAccord / the same attempted or assessable runs, with both denominators shown. Report unconfirmed alerts, errors found by baseline QA only and missed incidents. |
| Runtime and unchanged production output | Added wall time, peak memory if measured and direct versus observed-execution feature differences for all paired timing/output runs. Separate I/O, feature extraction and audit time where measurable. |
| Version concordance | Paired differences in decisions, applicability and bound outputs / all planned cross-version comparisons. Same input hashes and configuration semantics are required; incompatibility is not a disagreement to discard. |
| Operational action | Reprocessing, configuration correction or justified no-action decisions / all reviewed findings. Record whether the action restored the intended relationship. A changed feature value alone is not evidence of a corrected error. |

One run may contain several checkpoints and many features. Keep those denominators distinct. Record the same issue recurring across images both as events and as a unique mechanism. An issue tracker entry is not an independent participant or a detected experimental case.

## Analysis and retention rules

Retain a ledger of planned, started, completed and not-completed attempts. Use stable study identifiers; do not replace failed images with easier examples. Where participant linkage is unavailable, call the unit an image/volume rather than a patient. Summarise runtime and burden by group and workflow, with median and spread. Report paired differences on the same inputs rather than comparing unrelated summaries.

Do not treat features, representations or repeated images as independent observations. Any interval estimation must respect the available grouping by source, workflow and group; a small convenience sample of groups does not support a precise population-wide claim. Present sparse real-incident counts descriptively. Choose sample size and any inferential analysis before evaluation using the primary endpoint and feasible independent units, not the number of generated transformations.

Keep the first frozen evaluation unchanged. If an incorrect decision leads to a patch or profile revision, preserve that result, document the revision and assess it on a separately identified follow-up set. Do not report a tolerance tuned on the evaluation cases as having passed the original evaluation unchanged.

## Data handling and interpretation

Inputs, patient-derived masks, provenance containing private paths and raw engine logs remain under each group's control. Public contributions should contain synthetic minimal reproductions, version/configuration identifiers and reviewed aggregate outcomes. Hashes can support linkage but do not anonymise the underlying files or establish permission to share them.

Success would demonstrate reproducible use by independent groups, explicit accounting for coverage/abstention, and adjudicated findings that improve a processing decision at an observed boundary. A study finding few or no additional real errors remains informative about that setting and should be reported. Universal software correctness, diagnostic accuracy and clinical readiness are outside this protocol.

See [public incident references](INCIDENTS.md), [installation](INSTALL.md) and [release roadmap](ROADMAP.md).

