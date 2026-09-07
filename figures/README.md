# Figure reproduction

The archive includes plotting code and its source records; manuscript PNG, PDF and TIFF files are distributed separately. Run the scripts from a working copy of the extracted package:

```text
python -B work/build_fig1.py
python -B work/build_fig2.py
python -B work/build_fig3_4.py
```

Install Matplotlib, Pillow and scikit-image alongside the recorded core dependencies if needed. Arial regular and bold must be installed locally; no font files are included in this software archive. The shared work/figure_style.py checks Arial availability and sets the publication styling. Each script exports 600 dpi PNG/TIFF, vector PDF with embedded text fonts, and SVG with editable text.

Figure 1 uses development phantom 0 and labels the RadAccord checks; Figures 2-4 use the packaged archived results. No omitted image volumes or new native feature extraction are required. The figure scripts were rerun for this release, and all four output formats for all four figures were byte-identical to the final manuscript figures. The source data and frozen scientific modules remain unchanged. The rendering comparison used the existing local font and plotting environment; other font or plotting versions can change visual output. This check concerns figure reproduction, not a new benchmark evaluation.
