# Continuous verification

[Core verification](../.github/workflows/ci.yml) checks the release inventory, frozen evidence, archived decisions and core contracts. [Installed wheel and native integrations](../.github/workflows/native.yml) checks package installation and supported native integration profiles independently of that workflow.

The native workflow runs on pushes, pull requests and manual dispatches. Each of its six automatic jobs has a 20-minute limit and uses a fresh virtual environment, with system and user site packages excluded. It builds the wheel through an isolated PEP 517 build environment, installs that wheel, and runs the selected tests from a temporary directory outside the checkout. Tests also check that the imported package comes from the installation rather than the source tree.

| Profile | Python | Principal dependency pins | Platforms | Required test groups |
|---|---|---|---|---|
| PyRadiomics | 3.10 | PyRadiomics 3.0.1, SimpleITK 2.2.1, NumPy 1.23.5, NiBabel 5.3.3 | Ubuntu and Windows | Packaging and native PyRadiomics regressions |
| MIRP | 3.13 | MIRP 2.5.0, SimpleITK 2.5.3, NumPy 2.2.6, SciPy 1.15.3, pandas as pinned in the installed wheel, scikit-image 0.26.0, ITK 5.4.6, pydicom 3.0.1, NiBabel 5.3.3 | Ubuntu and Windows | Packaging and native MIRP regressions |
| Independent operator comparisons | 3.13 | NumPy 2.2.6, SciPy 1.15.3, SimpleITK 2.5.3, NiBabel 5.3.3 | Ubuntu and Windows | Packaging, operator and numerical-boundary tests against analytic fields, SimpleITK and SciPy |

Every automatic job runs `pip check`, verifies the applicable core and extra requirements recorded in the installed wheel metadata and requires all selected tests to execute. The workflow requires at least eleven packaging tests and, respectively, eleven PyRadiomics, eight MIRP or eighteen operator tests. Any omitted test fails its selected group; installing neither native engine cannot produce a passing native job. Additional tests are allowed without changing these lower bounds. PyRadiomics source builds receive NumPy, setuptools and wheel inside their dedicated environment before installing the legacy dependency; this does not disable isolation of the RadAccord wheel build. The native installation and requirement checks follow the wheel extras, including the pandas pin, so a package revision does not require a duplicate version list in the workflow. Principal dependencies are pinned; the workflow is not a complete transitive dependency lock.

The independent-operator jobs additionally require all twelve numerical-envelope
tests in `test_numerics.py`, including their SimpleITK and SciPy comparisons.
These checks preserve indeterminate boundary cases and reject unsupported
numerical profiles; they do not turn a tolerance band into a certified error bound.
Every automatic job also requires the five evidence/reporting tests, including
escaping of untrusted text and the limits of provenance and failure reports.

Linux MIRP installation uses pip **24.1.2** because the upstream ITK 5.4.6
Linux metawheel records a malformed `WHEEL` tag containing the package name and
version before the normal interpreter/ABI/platform fields. Later pip versions
raise a parsing exception in `pip check` after successful installation. The
installed upstream files remain untouched. The pinned pip command still checks
missing and conflicting dependencies; it does not perform the later installed-
wheel tag audit. Pip's platform selection at installation, the explicit version
assertions and the actual native import/extraction tests remain required. This
installer compatibility pin is not a correction of ITK or a skipped dependency
check. Windows keeps its normal installer. See the
[ITK release artifacts](https://pypi.org/project/itk/5.4.6/#files) and
[pip 24.1.2 check implementation](https://github.com/pypa/pip/blob/24.1.2/src/pip/_internal/commands/check.py).
The two optional historical Linux environments use the same ITK 5.4.6
metadistribution and the same installer pin; they remain manual jobs.

The synthetic native tests compare returned features with direct engine execution, exercise declared preprocessing checkpoints, and retain unsupported or ambiguous operations as unavailable or indeterminate. Packaging tests also exercise command entry points, report handling, and byte identity of the historical modules included in the wheel. Successful CI establishes those tested behaviors on the recorded environments; it does not establish correctness of every feature definition, clinical performance, or coverage of arbitrary configurations.

## Optional historical regression

When manually running the native workflow, enable **historical_mirp** to add two Ubuntu jobs for MIRP 2.4.1 and 2.4.2. They run the [documented synthetic NIfTI writer reproduction](INCIDENTS.md) with separately pinned historical environments. Each requires three completed cases: the axial control must satisfy the position check in both versions, and the two oblique cases must violate it in 2.4.1 and satisfy it in 2.4.2. Arrays, masks and paired image/mask geometry must remain equal in every case. Geometry checks allow ordinary floating-point variation; they do not require identical compressed NIfTI bytes or execution times across platforms.

These optional jobs are explicitly absent from ordinary push and pull-request runs. A green automatic run therefore does not imply that the historical reproduction ran. The historical file-writing experiment tests a different boundary from the MIRP 2.5.0 in-memory adapter.

All workflow inputs are small generated fixtures. The workflows do not download clinical collections, run the clinical benchmark or upload images, dependency caches or raw execution files as artifacts. Checkout and Python setup actions use the same immutable revisions as the core workflow, with read-only repository permissions and checkout credentials disabled.

The committed workflow is a test specification. Its presence is not evidence that GitHub Actions has passed: use the run associated with the exact commit being evaluated. Local wheel evidence is recorded separately in [WHEEL_VERIFICATION.md](WHEEL_VERIFICATION.md); installation instructions are in [INSTALL.md](INSTALL.md).

## Canonical temporary paths in Windows fixtures

The Windows hosted runner can expose an abbreviated 8.3 user path through TEMP.
Production repository roots are already resolved, but test fixtures that replace
those roots must use the same canonical spelling as their temporary files.
The release-tool test launcher resolves `tempfile.tempdir` before constructing
fixtures. All tests and production containment checks still execute unchanged.
The initial 1.3.0rc1 core run exposed this fixture mismatch on Windows while the
Ubuntu job passed; the scientific freeze and clinical analysis were not changed.
