# Native subset: independent numeric audit

All counts refer to the fixed subset and retained first run. No imaging input was reopened for this audit.

Extraction status: {'extracted': 30}. Comparison status: {'fully_analyzed': 24}.
Finite native values: 2160/2160; comparable feature pairs: 1728/1728.
Numerically changed pairs: 1418; tolerance = 1e-6 + 1e-5 × |reference|. This pooled feature count is an audit total, not an independent sample size.

Values below are median [minimum, maximum] across three released volumes. Relative absolute differences are multiplied by 100 for display; exact fractions and all 24 landmark rows remain in the accompanying JSON.

| Collection | Candidate vs reference | Features changed / 72 | Volume absolute Δ (mm³) | Volume relative | Mean absolute Δ | Mean relative | Variance absolute Δ | Variance relative |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Task04_Hippocampus | isotropic_0p8mm vs source_working_crop | 72 [71, 72] | 24.4799 [19.8799, 34.1278] | 0.830389 [0.592897, 0.922873]% | 3.97811 [0.321339, 6.16427] | 1.19952 [0.625372, 1.72306]% | 1639.94 [11.3251, 2167.25] | 20.29 [9.38315, 21.4083]% |
| Task04_Hippocampus | isotropic_1mm vs source_working_crop | 0 [0, 0] | 0 [0, 0] | 0 [0, 0]% | 0 [0, 0] | 0 [0, 0]% | 0 [0, 0] | 0 [0, 0]% |
| Task04_Hippocampus | isotropic_2mm vs source_working_crop | 69 [69, 70] | 49 [38, 84] | 1.46138 [1.02758, 2.84939]% | 1.37148 [0.12108, 3.72572] | 0.413544 [0.235639, 1.04143]% | 13.5129 [10.653, 450.593] | 5.5749 [0.133482, 8.8263]% |
| Task04_Hippocampus | wrong_image_kernel vs isotropic_0p8mm | 58 [57, 58] | 0 [0, 0] | 0 [0, 0]% | 5.03317 [0.282047, 6.22284] | 1.49967 [0.545493, 1.70997]% | 1740.17 [9.33851, 2181.22] | 27.0104 [8.5384, 27.4155]% |
| Task09_Spleen | isotropic_0p8mm vs source_working_crop | 72 [72, 72] | 164.71 [88.586, 229.038] | 0.0650867 [0.0193246, 0.0815675]% | 1.90616 [0.731372, 4.32474] | 1.80181 [0.589667, 4.80247]% | 127.339 [21.2287, 189.38] | 11.2741 [3.06471, 18.9132]% |
| Task09_Spleen | isotropic_1mm vs source_working_crop | 72 [72, 72] | 527.001 [80.347, 912.517] | 0.199062 [0.028614, 0.20825]% | 2.01555 [0.790332, 4.15591] | 1.90522 [0.637204, 4.61499]% | 126.545 [9.67929, 237.209] | 11.2038 [1.39737, 23.6898]% |
| Task09_Spleen | isotropic_2mm vs source_working_crop | 72 [72, 72] | 430.517 [358.001, 452.347] | 0.141468 [0.0939155, 0.161094]% | 1.70642 [0.81335, 4.32452] | 1.61301 [0.655762, 4.80222]% | 172.785 [4.24488, 179.171] | 15.2978 [0.612819, 17.8936]% |
| Task09_Spleen | wrong_image_kernel vs isotropic_0p8mm | 58 [58, 58] | 0 [0, 0] | 0 [0, 0]% | 1.92844 [0.767893, 4.50167] | 1.85633 [0.622785, 5.25112]% | 133.638 [20.2754, 182.911] | 10.633 [3.01963, 15.3617]% |

The working crop is the reference for the three correct resampling grids. The correct linear 0.8 mm output is the sole reference for the deliberately wrong image kernel. Correct resampling may legitimately change all feature families; this audit does not designate these changes as software failures or clinical harm.

Integrity checks passed: exact 30/24/72 assignments; native-to-public value correspondence; independently recomputed NumPy scalar comparisons; retained missingness; contrast counts; and public-output path/log exclusion. Original result files were not modified.
