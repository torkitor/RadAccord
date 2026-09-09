# Sampling figures

Run from the repository root in the recorded scientific environment:

```text
python -B scripts/figures/build_sampling_fig1.py
python -B scripts/figures/build_sampling_results_figures.py
python -B scripts/figures/build_sampling_graphical_abstract.py
```

Outputs are written to `docs/figures/sampling/` as 600 dpi PNG/TIFF and vector PDF/SVG. Earlier figures remain in their original locations. These scripts do not run native image extraction or change the scientific records.

Figure 1 uses the development phantom generator in `software/physical_contracts.py`. Figures 2–4 and the graphical abstract read `results/sampling_clinical/cases.jsonl`, `results/sampling_clinical/checkpoint_demo.jsonl` and `results/native_feature_subset/native_comparisons.jsonl` as applicable. The reserved synthetic evaluation remains available in `results/sampling_reserved/`; it is reported separately and is not pooled into the anatomical figures.

The shared style is `work/figure_style.py`. Rendering requires the recorded Matplotlib, NumPy, Pillow and scikit-image packages, plus locally installed Arial regular and bold. The style raises an error if Arial is absent; the repository does not distribute font files. The PNG and TIFF pixels match, PDFs embed the used font subsets, and SVG text remains editable.

The graphical abstract is an optional scientific summary, not a journal-provided template. Its evidence counts are calculated from the archived case records. Numerical results represent controlled technical evaluations of research preprocessing, not patient-level clinical performance.
