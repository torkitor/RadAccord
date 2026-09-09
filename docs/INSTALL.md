# Install and run RadAccord

RadAccord 1.2.0rc3 is a local release candidate for physical consistency checks in radiomics research. These instructions install the supplied source checkout or wheel; they do not imply that this version has been published on PyPI. The code is licensed under Apache-2.0.

The rc3 change normalizes CLI filenames to strings for native dispatch. The
scientific native modules and their rc2 evaluation remain unchanged and are
preserved in the [refinement archive](../data/RadAccord-native-refinement-2.zip).

## Core installation

Create and activate a fresh Python environment, then install the source checkout:

```sh
python -m venv .venv-core
# Linux/macOS: source .venv-core/bin/activate
# Windows PowerShell: .venv-core\Scripts\Activate.ps1
python -m pip install /path/to/RadAccord
radaccord version
radaccord demo --output ./demo-output
```

The demo creates a **new** directory containing synthetic source/candidate NIfTI files, a declared identity plan and JSON/HTML reports. It requires no clinical images or radiomics engine. Run it from a writable working directory; installed package files are never used as output destinations. `python -m radaccord` exposes the same commands as `radaccord`.

Core dependencies are NumPy and NiBabel. Python 3.13 with NumPy 2.2.6 is the core study environment; Python 3.10 with NumPy 1.23.5 is the separate historical PyRadiomics environment. The package's dependency range accommodates both; a successful installation alone does not validate every intermediate dependency version.

## Check a declared operation

```sh
radaccord verify --plan /private/work/plan.json --report ./sampling-report.json --html ./sampling-report.html
```

Use the demo plan as a small schema example, and consult [sampling instructions](SAMPLING.md) before replacing it with your own source and candidate files. Relative image paths resolve against the plan's directory. The source and intended operation must be established independently of the candidate. Keep clinical inputs and plans containing private paths outside the public repository.

The JSON/HTML reports contain checkpoint decisions, component diagnostics and hashes, rather than input filenames or raw reader exceptions. A satisfied resampling operation can still require feature extraction again. Input ROI preservation is a conditional input result, not a general guarantee of feature equivalence or clinical validity.

## Native-engine environments

Use **separate environments** for the two extras. Their pinned dependency stacks differ; do not combine `[pyradiomics,mirp]` in one environment.

| Environment | Install after activating the environment |
|---|---|
| Python 3.10, PyRadiomics 3.0.1 | Use the bootstrap commands below. |
| Python 3.13, MIRP 2.5.0 | `python -m pip install "/path/to/RadAccord[mirp]"` |

In the activated Python 3.10 environment, install the build prerequisites before
the PyRadiomics extra. Its source distribution requires NumPy at build time:

```sh
python -m pip install setuptools==80.9.0 wheel==0.45.1 numpy==1.23.5 SimpleITK==2.2.1
python -m pip install --no-build-isolation "/path/to/RadAccord[pyradiomics]"
python -m pip check
```

The same commands accept the supplied wheel filename in place of the source
directory, with `[pyradiomics]` appended. PyRadiomics still requires a compatible
C compiler when neither an upstream nor a locally cached native wheel is
available. A successful fresh-environment installation using a cached native
wheel does not verify compilation from source on another computer.

These extras select the versions used by the respective native adapters. Core installation does not import, download or initialise either engine. The optional `[oracle]` extra adds SciPy for independent operator comparisons; it is not required by the core sampling witness.

The MIRP extra pins pandas 2.3.3 for the tested integer-IVH compatibility case.
See [MIRP scope and compatibility](MIRP.md) before changing that dependency.

```sh
radaccord native --engine pyradiomics --image /private/work/image.nii.gz --mask /private/work/mask.nii.gz --label 1 --report ./native-report.json --html ./native-report.html --methods ./methods.txt
```

Replace `pyradiomics` with `mirp` in its own environment. `--config engine-config.json` accepts an engine-specific JSON object: PyRadiomics parameter dictionaries or MIRP keyword settings. Configuration and domain support belong to the selected native profile; options are not interchangeable between engines. Optional `--html` and `--methods` render the same report without adding claims of feature correctness. Review the methods text before incorporating it into a manuscript. The CLI exports audit evidence rather than the engine's feature container. Native feature values remain available through the Python API:

```python
from radaccord import audit_pyradiomics  # audit_mirp has the same call signature

result = audit_pyradiomics(image, mask, config=None, label=1)
report = result["report"]
features = result["features"]
```

Check the report before using the extracted values. Unsupported or unevaluated operations must remain explicit; successful extraction does not establish that the requested processing was verified. The API preserves engine-specific feature containers and does not assert equality between engines.

## Exit codes and diagnostics

- `0`: the native report has `status: satisfied`, the sampling plan has `decision: sampling_satisfied`, or version/help was displayed.
- `1`: native `violated`/`indeterminate`, or a completed sampling plan requiring review.
- `2`: operation or command unavailable, including missing dependencies, invalid inputs or an unwritable output.

Read the report's component decisions and scope, rather than interpreting the exit code as a clinical recommendation. Commands suppress raw engine/reader exception text. If an output cannot be safely written, only a generic console message and exit code are returned.

Before native execution, the writable requested reports are replaced with
`unavailable` records marked `native_execution_not_completed`. Each subsequent
file replacement is atomic. An interrupted process can therefore leave pending
evidence; it must not be interpreted as a completed evaluation. Sampling commands
also replace prior positive reports before starting their child process.

## Build and verify a wheel

```sh
python -m pip wheel --no-deps /path/to/RadAccord --wheel-dir ./dist
python -m venv .venv-wheel
# Activate this new environment, then install the generated wheel:
python -m pip install ./dist/radaccord-1.2.0rc3-py3-none-any.whl
radaccord version
radaccord demo --output ./installed-demo
```

Run the installed checks from outside the source checkout. A wheel contains the Python interfaces and unchanged scientific source modules, but excludes the clinical images, stored study records and archival ZIP. Use the source release and [reproducibility guide](REPRODUCIBILITY.md) to reproduce archived results. The frozen sources remain in `software/` in the checkout and are packaged byte-identically under the private `radaccord._frozen` namespace; the sampling command runs its historical wrapper in a subprocess.
