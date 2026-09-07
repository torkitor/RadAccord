# Using RadAccord 1.0.0

RadAccord checks declared physical correspondence and selected measurement obligations at a NIfTI input-file boundary. The source image, source mask and transformation manifest must be trustworthy. A satisfied decision does not establish clinical validity or equivalence of every extracted feature.

## Environment and entry point

Use a core Python environment with NumPy and NiBabel and a separate native-engine environment. The recorded dependencies are in `software/requirements-core.txt`, `software/requirements-pyradiomics.txt` and `software/requirements-mirp.txt`. Follow [software/REPRODUCIBILITY.md](software/REPRODUCIBILITY.md) to reproduce the recorded environments. Install requirements only into the isolated environments you intend to use. This archive is not a PyPI package.

From the RadAccord directory, with the core interpreter active:

```text
python -B radaccord.py --version
python -B radaccord.py --help
```

The version command returns `RadAccord 1.0.0`. All other arguments are delegated to the unchanged `software/verify_refined.py`; its original script name may appear in help and parser messages. Paths supplied for images, masks, contracts and reports are interpreted relative to your current working directory. The entry point locates its own scientific modules independently of that directory.

The default is the revised acceptance profile. To access the original strict profile directly, use `python -B software/verify.py` with the same arguments. Do not describe results from one profile as results from the other. The wrapper adds no measurement rules, tolerance changes or native-engine modifications.

## Run the two included examples

These six small NIfTI files are synthetic. `ENGINE_PYTHON` below is a placeholder: replace it with the full path to your PyRadiomics 3.0.1 Python executable, retaining quotation marks if the path contains spaces. Run each command from the RadAccord directory using the core interpreter.

```text
python -B radaccord.py --source-image software/examples/source_image.nii.gz --source-mask software/examples/source_mask.nii.gz --candidate-image software/examples/valid_reindex_image.nii.gz --candidate-mask software/examples/valid_reindex_mask.nii.gz --contract software/examples/valid_reindex_contract.json --engine pyradiomics --engine-python "ENGINE_PYTHON" --report valid_report.json

python -B radaccord.py --source-image software/examples/source_image.nii.gz --source-mask software/examples/source_mask.nii.gz --candidate-image software/examples/origin_fault_image.nii.gz --candidate-mask software/examples/origin_fault_mask.nii.gz --contract software/examples/origin_fault_contract.json --engine pyradiomics --engine-python "ENGINE_PYTHON" --report fault_report.json
```

Expected results under the revised profile:

| Example | Printed decision | Exit code | Interpretation |
|---|---|---:|---|
| `valid_reindex` | `applicable_obligations_satisfied` | 0 | The applicable checks passed. Four mesh-related reindexing obligations remain withheld; their original diagnostics are retained. |
| `origin_fault` | `violated` | 1 | Image and mask share an undeclared origin change. Physical correspondence fails even though invariant feature relations and anchors can pass. |

Both reports retain native measurements, component decisions and individual reasons for abstention. The original strict `software/verify.py` flags the valid mesh example; that historical result is intentionally retained. Exit code 2 denotes an unavailable or non-applicable overall assessment, not acceptance. A required check that fails remains a violation. Inspect the full JSON rather than relying only on the exit code.

The included expected reports are reference examples. New run durations may differ. The original branded-entry checks are recorded in `release_history/radaccord_1_0_0/software_branding_audit.json`; historical tests from the source package are stored separately under `release_history/`.

## Apply the tool to another integration

Retain the original source image and segmentation before conversion, together with their identifiers and hashes. Record the intended transformation when specifying or producing the conversion. Do not derive a convenient manifest retrospectively solely to make a candidate pass.

Supply the new source/candidate paths, selected labels and manifest using the same arguments. The documented domain includes three-dimensional orthogonal millimetre NIfTI, consistent coded qform/sform geometry and supported full-grid relationships. Cropping, interpolation and arbitrary deformation are outside this correspondence contract. Other preprocessing or feature settings need their own applicability assessment. The scientific modules retain their original version-specific rules; a new engine or configuration is a new compatibility evaluation.

The tool observes the input files presented at the chosen checkpoint. It cannot certify the extractor's internal image state or correct an already mislabelled trusted source. Its scalar tests cover assigned obligations, not every possible feature. The revised PyRadiomics profile withholds four mesh obligations only for reindexing; their absence must remain visible in any claim about coverage.

Reports from your own data may contain sensitive measurements. Keep private input data and worker logs in your controlled environment and inspect exports before sharing. The synthetic release's privacy check does not certify arbitrary future reports.

## Methods reporting template

Use this template only after performing the stated procedures. Replace every bracketed field with what was actually done; delete procedures that were not performed. Do not imply use of RadAccord from citing or downloading it alone.

> Physical consistency was assessed using RadAccord [software version and release identifier/hash] with the [revised or original strict] profile, identified by [profile name and freeze-file SHA256]. Verification was performed at [precise input-file checkpoint] between [source image/segmentation and provenance] and [candidate conversion]. The source and transformation manifest were treated as trusted because [how they were retained and established independently of the acceptance result]. Native measurements were extracted using [engine, version, relevant dependencies and complete configuration], with [preprocessing, dimensional aggregation, discretisation and selected ROI labels]. We checked [physical correspondence, assigned laws and/or anchors actually evaluated], using [reported tolerances]. Of [attempted comparisons], [number] were assessable, [number] violated required checks, and [number] satisfied all applicable obligations. [Number and reasons] remained unavailable or outside the supported domain. Feature-level non-applicability and [withheld obligations, including the four mesh obligations if relevant] were reported separately and were not counted as satisfied checks. The source files, manifests, configuration, component decisions and release identifiers are [public location or explicit controlled-access/unavailable statement]. These checks concern the declared file boundary and assigned obligations; [clinical performance or internal-state validation, if separately conducted, described with its own evidence].

Also specify whether reported counts refer to subjects, images, transformations or fault cases. Repeated representations from the same source are not independent subjects. Cite the actual software version and the article when bibliographic details exist; `CITATION.cff` identifies the software and repository without assigning an unpublished article a DOI.
