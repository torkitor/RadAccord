# New clinical input collections: source and selection record

Accessed 9 September 2026 from the official MONAI-managed [AWS MSD mirror](https://registry.opendata.aws/msd/). The selected inputs are newly used in this project; no claim is made that an independent clinical site or external operator conducted this evaluation.

The registry and original `dataset.json` files identify the data licence as **CC-BY-SA 4.0**. That licence and dataset attribution remain separate from the Apache-2.0 software licence. Raw clinical volumes and private manifests are excluded from the software repository.

The complete archives matched their published MD5 values in the [pinned MONAI source](https://github.com/Project-MONAI/MONAI/blob/20df60253d364be69601114adae3bd609e0cb6f6/monai/apps/datasets.py). SHA-256 values below were calculated locally to identify the received bytes; they are not publisher-supplied SHA-256 attestations. HTTP Content-Range and total size were checked for every requested range.

| Collection | Bytes | Released training pairs | Released unlabelled test images | Published/observed MD5 | Observed SHA-256 |
|---|---:|---:|---:|---|---|
| Task02_Heart | 455721472 | 20 | 10 | 06ee59366e1e5124267b774dbd654057 | 4277dc6dfe100142aa8060e895f6ff0f81c5b733703ea250bd294df8f820bcba |
| Task06_Lung | 9163696640 | 63 | 32 | 8afd997733c7fc0432f71255ba4e52dc | f782cd09da9cf7a3128475d4a53650d371db10f0427aa76e166fccfcb2654161 |

Direct unsigned download URLs and HTTP response metadata are in [download_provenance.json](download_provenance.json). The complete archive was validated before extraction. Extraction rejected absolute/traversal paths, links, special members and duplicate destinations, and copied regular files into a fresh staging directory without `extractall`. Platform metadata files were omitted and counted in the private acquisition inventories.

Twelve training volumes per collection were selected by the SHA-256 ranking specified in [the selection protocol](../../new_cohort_selection.md), without replacement after eligibility assessment. The preselection protocol and script hashes were recorded before inspecting selected content; an interim Heart eligibility report was prepared while Lung was downloading. The complete [selection order](selection_order.json) and [source eligibility record](selected_source_eligibility.json) bind the final selection. The larger Lung transfer was restarted with greater request concurrency; [the transport adjustment](download_transport_adjustment.json) records this change without changing source bytes, checksums or selection.

Eligibility assessed source headers, decoded finiteness, integral mask labels and label-1 support. No resampling, intensity conversion, native feature extraction or RadAccord evaluation was performed by these acquisition scripts. Source eligibility does not establish that every native configuration is supported; all selected slots, exclusions and subsequent unavailable or failed attempts remain reportable.

| Collection | Selected | Source eligible | Source excluded | Storage dtype(s) | Spatial units | Source shape range | Proposed bbox + 10 mm crop shape range |
|---|---:|---:|---:|---|---|---|---|
| Task02_Heart | 12 | 12 | 0 | float32 | mm | 320 × 320 × 100 to 320 × 320 × 130 | 50 × 60 × 70 to 70 × 83 × 95 |
| Task06_Lung | 12 | 12 | 0 | float32 | mm | 512 × 512 × 115 to 512 × 512 × 493 | 43 × 46 × 14 to 112 × 172 × 97 |

These are released source-volume counts, not an inferred count of unique participants. The selected files and their headers govern this evaluation. In particular, the Heart release has 1.25 × 1.25 × approximately 1.37 mm spacing in the selected volumes; this should not be conflated with the approximately 2.7 mm acquisition slice resolution described in the original dataset paper. The crop dimensions are a deterministic preparation proposal from the source label bounding box, not measured extractor performance or proof of feature equivalence with the full image.

The original dataset description states that contributing sites de-identified the data. No additional institutional approval, independent de-identification audit, external operator participation or clinical outcome validation is asserted by this source record.

Dataset citations: Simpson AL, Antonelli M, Bakas S et al. [A large annotated medical image dataset for the development and evaluation of segmentation algorithms](https://doi.org/10.48550/arXiv.1902.09063) (2019); Antonelli M, Reinke A, Bakas S et al. [The Medical Segmentation Decathlon](https://doi.org/10.1038/s41467-022-30695-9), Nature Communications 13, 4128 (2022).
