# Installed wheel verification

## Current 1.3.0rc1 artifact

Three fresh Windows environments tested the installed package outside the source
checkout: 52 oracle/core checks, 27 PyRadiomics/core checks and 32 MIRP/core checks.
These comprise 79 distinct tests and 111 executions, with no selected test skipped.
The final wheel updates installation prose in METADATA and RECORD only; every
Python payload is byte-identical to the fully tested wheel. It was reinstalled
in all three environments, with installed payload identity and pip check passing.
The [machine-readable receipt](wheel-verification-1.3.0rc1.json) retains both hashes.
The final local wheel SHA-256 is
`f58e91262f56890fe8b330fecf38bcc5cb43179bd95ff3d8f40ec299dea170f7`.

Remote verification completed for commit
`9963d5940f5fa863b27c63932a704b822ddbfc41`: all eight mandatory jobs passed.
The [native workflow](https://github.com/torkitor/RadAccord/actions/runs/34370081420)
passed its PyRadiomics, MIRP and oracle jobs on both Ubuntu and Windows. Its
optional historical-writer job was skipped by design and is not counted as an
executed regression. The [core workflow](https://github.com/torkitor/RadAccord/actions/runs/34370081417)
passed on both platforms. This identifies source-commit CI evidence; it does not
assert that platform-built wheel archives have the local wheel's byte hash or
that a later documentation commit has been retested remotely.

The [prospective native results](PROSPECTIVE_VALIDATION.md) are separate from
installation and unit-test success. The clinical-source execution was author-run
on its recorded Windows host; passing CI does not repeat that experiment.

## Historical verification records

The following entries describe their named earlier artifacts and remain historical.


## Final 1.2.0rc3 artifact

Local Windows verification completed on 2026-09-09. The supplied wheel has
**79,836 bytes** and SHA-256
`1976dc89877a7bed5b93dbad8fbbcf33dc4bc1bb25e781ed04a7d2e6b86644a6`.
Its filename is `radaccord-1.2.0rc3-py3-none-any.whl`.
This record identifies a local candidate; it does not assert PyPI publication,
completed remote native CI or clinical validation. Machine-readable evidence is
in [wheel-verification-1.2.0rc3.json](wheel-verification-1.2.0rc3.json).

The PEP 517 build ran in an isolated build environment. The wheel was installed
in three dedicated virtual environments without system site-packages. Tests
were copied outside the checkout, and imports were checked to originate from
each installed package. Execution also took place outside the checkout.

The initial rc3 wheel passed **65 distinct tests**, with no failures, errors or
skips: 11 packaging, five evidence/reporting, 11 PyRadiomics, eight MIRP,
18 operator and 12 numerical tests. Common groups ran in multiple environments;
their repetitions are not additional distinct tests. The initial tested wheel
had SHA-256 `0b33fac37d11f8c5cdfdf97f99434ce2b28f1cd06d4e63932e08d65fe427b746`.

After those tests, the installation guide was corrected to document the
PyRadiomics build prerequisites. The final rebuild differs **only in METADATA
and RECORD**. Every Python payload is byte-identical. The complete suite was
therefore not repeated. The final wheel was reinstalled in all three environments;
source-integrity checks, version commands, native CLI comparisons and
`pip check` passed again. The initial rc3, rc2 and rc1 wheels remain retained.

## Tested environments

| Environment | Versions | Distinct groups exercised there |
|---|---|---|
| Core | Python 3.12.14; NumPy 2.2.6; NiBabel 5.3.3 | 11 packaging + 5 evidence/reporting |
| PyRadiomics | Python 3.10.11; PyRadiomics 3.0.1; SimpleITK 2.2.1; NumPy 1.23.5; NiBabel 5.3.3 | The same 16 common tests + 11 native tests |
| MIRP and independent operator comparisons | Python 3.13.5; MIRP 2.5.0; pandas 2.3.3; NumPy 2.2.6; NiBabel 5.3.3; SciPy 1.15.3; SimpleITK 2.5.3; scikit-image 0.26.0; ITK 5.4.6; pydicom 3.0.1 | The same 16 common tests + 8 native + 18 operator + 12 numerical tests |

A fourth, fresh Python 3.10.11 environment also completed the exact source
installation recipe in [INSTALL.md](INSTALL.md): bootstrap setuptools 80.9.0,
wheel 0.45.1, NumPy 1.23.5 and SimpleITK 2.2.1, then install the PyRadiomics extra
with `--no-build-isolation`. Its version command and `pip check` passed.
That installation used a cached PyRadiomics native wheel; compilation from
source on a machine without a matching wheel was not tested.

## Real native CLI checks

The final installed PyRadiomics CLI processed the generated demo, returned
`satisfied` at its three observed checkpoints and wrote JSON, HTML and methods
text. The final MIRP CLI processed a supported synthetic NIfTI case, returned
`satisfied` at its observed checkpoint and wrote the same output types.
For both, the report matched the direct string-based API except elapsed time,
and the native feature digest matched exactly. Reports and captured output
contained no temporary input identifiers, and HTML had no executable scripts.

The generic demo also exercised MIRP's unavailable path: it returned
`unavailable`, exit code 2, consistently with the direct API because its decoded
native spacing was outside the checked profile. This outcome remains explicit;
it is not converted into a satisfied result. The supported fixture returned
exit code 0. These are generated input checks, not clinical performance estimates.

## Scientific identity and retained history

The rc3 code correction converts CLI filenames from `pathlib.Path` to strings
before native dispatch. A real rc2 MIRP CLI execution had raised an unsupported
input-type exception while the same supported files succeeded through the
string API. The rc3 regression exercises native MIRP when installed; engine-free
environments exercise the filename contract with a strict stand-in.

The adapter, operator, numerical and evidence modules are byte-identical to
the retained rc2 evaluation. The 27-file rc2 freeze remains unchanged. Four
current source files deliberately differed from that historical freeze at the
initial rc3 wheel verification:
`pyproject.toml`, `radaccord/__init__.py`, `radaccord/cli.py` and
`tests/test_packaging.py`. Version/CLI/test updates do not constitute a new
scientific cohort evaluation.

The first Ubuntu CI run exposed a platform-specific assumption in the integer
resampling test: it required every preserved nominal diagnostic to reproduce
the Windows result, even though weighted integer sampling is outside the checked
numerical profile. The current test requires `unavailable` at every checkpoint,
unchanged native outputs and retained nominal diagnostic fields. The scientific
modules and the final wheel are unchanged. This adds a fifth current difference
from the historical rc2 freeze, `tests/test_native_pyradiomics.py`.
All eleven current PyRadiomics tests were repeated on Windows and passed without
skips; they are a repeat of that group, not eleven additional distinct tests.
The original 65-test record above remains intact. At the time of that historical
local record, completion of the corrected PR jobs remained pending. The current
1.3.0rc1 remote verification is identified separately at the top of this document.

| Retained artifact | SHA-256 |
|---|---|
| rc2 wheel (79,492 bytes) | `82d81f4452f69e3c50641162ab8fc58f44ee32cb6fd26d11ed79ab75acdb076f` |
| rc1 wheel (72,087 bytes) | `8df00df467dcdb11cfd68a45283e368d8034020732fbe0c6e71f4a3413448b26` |
| [rc2 source and evaluation archive](../data/RadAccord-native-refinement-2.zip) | `d8780b56b63c50e75631fa63ac0cb68874c60357d9ceb8828cf3d47b27ce6bb5` |
| [rc1 calibration archive](../data/RadAccord-native-calibration-1.zip) | `a3e2bff93996884ca8f8c31a38dbe8f1bb75acf2e011509e4d06ca9cbfd1532f` |

The MIRP extra retains the tested pandas 2.3.3 compatibility pin. A synthetic
uint8 MR IVH case reproduced an extraction TypeError with pandas 3.0.2 and
completed with 2.3.3; the latter still emits a dtype-assignment warning.
This documents a dependency combination, not a MIRP source modification.

The wheel excludes clinical images, study JSONL records and archival ZIPs.
Historical scientific modules are packaged byte-identically under
`radaccord._frozen`. Installation and input-relation checks do not validate all
feature formulae, hidden processing states or clinical utility. Broader platform
results require the actual runs described in [CI.md](CI.md); prospective adoption
is addressed in [EXTERNAL_EVALUATION.md](EXTERNAL_EVALUATION.md).
