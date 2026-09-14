# ICA 2026 — results for writing

Generated from repository artifacts by script. Nothing here is retyped.

- Runs: 18 of 18
- Seeds: 42, 1337, 2026
- Dataset lock digest: `83449f60136918554904cb9c596122f8b89cb51ff5bb5c52c541394a5698082d`
- Contributing commits: `054834cd45`, `261fd3af0a`, `370d4cff00`, `476b354395`, `4e25c4ecb4`, `5e81b9fd1c`, `784ec9cba4`, `7d21448721`, `872b5f6ed8`, `b385ca602b`, `ba881b1175`, `d3d7e5f1b6`, `ddcfd18853`
- Hardware: macOS-26.5.1-arm64-arm-64bit-Mach-O, backend mps, torch 2.13.0

Sources: `experiments/ica26/tables/`, `experiments/ica26/metrics/`, `experiments/ica26/figures/`, `paper/generated/results_macros.tex`.

---

## 1. LaTeX source of every generated table

Literal file contents, current three-seed versions. Paste directly.

### table1 — dataset statistics

Source: `experiments/ica26/tables/table1_dataset_statistics.tex`

```latex
\begin{table}[htbp]
\caption{Dataset composition after leakage control and conservative exclusion. The cross-domain evaluation subset holds 1951 PlantDoc Core images over 21 shared classes.}
\label{tab:dataset-stats}
\begin{tabular}{lrrrr}
\toprule
Dataset & Images & Train & Test & Classes \\
\midrule
PlantVillage & 54305 & 43596 & 10709 & 38 \\
PlantDoc Core & 2561 & 2336 & 225 & 28 \\
\bottomrule
\end{tabular}
\end{table}
```

### table1b — dataset provenance and leakage control

Source: `experiments/ica26/tables/table1b_dataset_provenance.tex`

```latex
\begin{table}[htbp]
\caption{Dataset provenance and leakage control. Perceptual-hash Hamming threshold 6; all 16 near pairs human-adjudicated as clearly different.}
\label{tab:dataset-provenance}
\begin{tabular}{lr}
\toprule
Quantity & Value \\
\midrule
PlantDoc acquired (source) & 2578 \\
PlantDoc previous effective & 2564 \\
PlantDoc Core & 2561 \\
PlantDoc non-reviewed unchanged & 2554 \\
PlantDoc retained reviewed & 7 \\
PlantDoc excluded reviewed & 17 \\
Cross-dataset exact duplicates (acquired) & 0 \\
Cross-dataset near duplicates (acquired) & 16 \\
Cross-dataset exact duplicates (Core) & 0 \\
Cross-dataset near duplicates (Core) & 16 \\
Unresolved leakage pairs & 0 \\
Shared cross-domain classes & 21 \\
Cross-domain evaluation images & 1951 \\
\bottomrule
\end{tabular}
\end{table}
```

### table2 — in-domain performance (full)

Source: `experiments/ica26/tables/table2_in_domain_performance.tex`

```latex
\begin{table}[htbp]
\caption{In-domain test performance, mean $\pm$ sample standard deviation over independent training seeds (42, 1337, 2026). Macro averages are computed over the classes present in the evaluation split; PlantDoc Core's arthropod-pest class has zero test images and is reported separately rather than averaged in as zero.}
\label{tab:in-domain}
\begin{tabular}{llrrllllll}
\toprule
Model & Dataset & Seeds & N & Accuracy & Macro-F1 & Weighted-F1 & Balanced Acc. & Macro Prec. & Macro Rec. \\
\midrule
ResNet-50 & PlantVillage & 3 & 10709 & 0.9945 $\pm$ 0.0021 & 0.9927 $\pm$ 0.0029 & 0.9945 $\pm$ 0.0021 & 0.9923 $\pm$ 0.0029 & 0.9934 $\pm$ 0.0028 & 0.9923 $\pm$ 0.0029 \\
EfficientNet-B0 & PlantVillage & 3 & 10709 & 0.9964 $\pm$ 0.0005 & 0.9950 $\pm$ 0.0006 & 0.9964 $\pm$ 0.0005 & 0.9945 $\pm$ 0.0008 & 0.9956 $\pm$ 0.0004 & 0.9945 $\pm$ 0.0008 \\
MobileNetV3-Small & PlantVillage & 3 & 10709 & 0.9948 $\pm$ 0.0004 & 0.9927 $\pm$ 0.0004 & 0.9948 $\pm$ 0.0004 & 0.9916 $\pm$ 0.0003 & 0.9940 $\pm$ 0.0006 & 0.9916 $\pm$ 0.0003 \\
ResNet-50 & PlantDoc Core & 3 & 225 & 0.6637 $\pm$ 0.0403 & 0.6823 $\pm$ 0.0386 & 0.6946 $\pm$ 0.0406 & 0.6551 $\pm$ 0.0393 & 0.7539 $\pm$ 0.0317 & 0.6551 $\pm$ 0.0393 \\
EfficientNet-B0 & PlantDoc Core & 3 & 225 & 0.6652 $\pm$ 0.0128 & 0.6768 $\pm$ 0.0139 & 0.6920 $\pm$ 0.0162 & 0.6569 $\pm$ 0.0087 & 0.7430 $\pm$ 0.0082 & 0.6569 $\pm$ 0.0087 \\
MobileNetV3-Small & PlantDoc Core & 3 & 225 & 0.5600 $\pm$ 0.0044 & 0.5876 $\pm$ 0.0061 & 0.5936 $\pm$ 0.0044 & 0.5640 $\pm$ 0.0030 & 0.6564 $\pm$ 0.0136 & 0.5640 $\pm$ 0.0030 \\
\bottomrule
\end{tabular}
\end{table}
```

### table2_compact — in-domain performance (paper)

Source: `experiments/ica26/tables/table2_in_domain_performance_compact.tex`

```latex
\begin{table}[htbp]
\caption{In-domain test performance, mean $\pm$ sample standard deviation over three seeds. Weighted-F1, balanced accuracy, and macro precision and recall are in the supplementary table.}
\label{tab:in-domain-compact}
\footnotesize
\centering
\begin{tabular}{llrll}
\toprule
Model & Corpus & N & Accuracy & Macro-F1 \\
\midrule
ResNet-50 & PV & 10709 & 0.9945 $\pm$ 0.0021 & 0.9927 $\pm$ 0.0029 \\
EfficientNet-B0 & PV & 10709 & 0.9964 $\pm$ 0.0005 & 0.9950 $\pm$ 0.0006 \\
MobileNetV3-Small & PV & 10709 & 0.9948 $\pm$ 0.0004 & 0.9927 $\pm$ 0.0004 \\
ResNet-50 & PDC & 225 & 0.6637 $\pm$ 0.0403 & 0.6823 $\pm$ 0.0386 \\
EfficientNet-B0 & PDC & 225 & 0.6652 $\pm$ 0.0128 & 0.6768 $\pm$ 0.0139 \\
MobileNetV3-Small & PDC & 225 & 0.5600 $\pm$ 0.0044 & 0.5876 $\pm$ 0.0061 \\
\bottomrule
\end{tabular}
\end{table}
```

### table3 — cross-domain performance (full)

Source: `experiments/ica26/tables/table3_cross_domain_performance.tex`

```latex
\begin{table}[htbp]
\caption{Cross-domain generalisation, mean $\pm$ sample standard deviation over three seeds: PlantVillage-trained models evaluated on the frozen shared-class PlantDoc Core subset. Metrics are computed only over the 21 shared classes; unmapped PlantDoc images are excluded from the evaluation set rather than counted as errors. Retained probability mass is the share of the source model's belief falling inside the shared space before renormalisation.}
\label{tab:cross-domain}
\begin{tabular}{llrrllllllrl}
\toprule
Model & Dataset & Seeds & N & Accuracy & Macro-F1 & Weighted-F1 & Balanced Acc. & Macro Prec. & Macro Rec. & Shared classes & Retained prob. mass \\
\midrule
ResNet-50 & PlantVillage $\rightarrow$ PlantDoc Core & 3 & 1951 & 0.2583 $\pm$ 0.0206 & 0.2291 $\pm$ 0.0107 & 0.2512 $\pm$ 0.0138 & 0.2389 $\pm$ 0.0188 & 0.3629 $\pm$ 0.0197 & 0.2389 $\pm$ 0.0188 & 21 & 0.6367 $\pm$ 0.0945 \\
EfficientNet-B0 & PlantVillage $\rightarrow$ PlantDoc Core & 3 & 1951 & 0.2653 $\pm$ 0.0102 & 0.2300 $\pm$ 0.0065 & 0.2528 $\pm$ 0.0078 & 0.2475 $\pm$ 0.0110 & 0.3455 $\pm$ 0.0257 & 0.2475 $\pm$ 0.0110 & 21 & 0.6595 $\pm$ 0.0086 \\
MobileNetV3-Small & PlantVillage $\rightarrow$ PlantDoc Core & 3 & 1951 & 0.2238 $\pm$ 0.0162 & 0.1869 $\pm$ 0.0109 & 0.2013 $\pm$ 0.0160 & 0.2141 $\pm$ 0.0135 & 0.3090 $\pm$ 0.0248 & 0.2141 $\pm$ 0.0135 & 21 & 0.5662 $\pm$ 0.0477 \\
\bottomrule
\end{tabular}
\end{table}
```

### table3_compact — cross-domain performance (paper)

Source: `experiments/ica26/tables/table3_cross_domain_performance_compact.tex`

```latex
\begin{table}[htbp]
\caption{Cross-domain generalisation on the frozen shared-class PlantDoc Core subset, mean $\pm$ sample standard deviation over three seeds. Metrics cover only the 21 shared classes; unmapped images are excluded rather than counted as errors. `Ret.\ mass' is the mean source-model probability retained inside the shared space before renormalisation.}
\label{tab:cross-domain-compact}
\footnotesize
\centering
\begin{tabular}{lrlll}
\toprule
Model & N & Accuracy & Macro-F1 & Ret. mass \\
\midrule
ResNet-50 & 1951 & 0.2583 $\pm$ 0.0206 & 0.2291 $\pm$ 0.0107 & 0.6367 $\pm$ 0.0945 \\
EfficientNet-B0 & 1951 & 0.2653 $\pm$ 0.0102 & 0.2300 $\pm$ 0.0065 & 0.6595 $\pm$ 0.0086 \\
MobileNetV3-Small & 1951 & 0.2238 $\pm$ 0.0162 & 0.1869 $\pm$ 0.0109 & 0.5662 $\pm$ 0.0477 \\
\bottomrule
\end{tabular}
\end{table}
```

### table4 — efficiency

Source: `experiments/ica26/tables/table4_efficiency.tex`

```latex
\begin{table}[htbp]
\caption{Model efficiency, mean $\pm$ sample standard deviation over three seeds. Epoch counts vary between seeds because early stopping fires at different points, so training time is reported alongside seconds per epoch. Latency and throughput are measured after warm-up on the accelerator reported in the run metadata.}
\label{tab:efficiency}
\begin{tabular}{llrrllllll}
\toprule
Model & Dataset & Seeds & Params (M) & Epochs & Train time (min) & s / epoch & Latency b1 (ms) & Throughput (img/s) & Peak mem (MB) \\
\midrule
ResNet-50 & PlantVillage & 3 & 23.59 & 12.0 $\pm$ 2.6 & 143.9 $\pm$ 35.1 & 718.7 $\pm$ 53.1 & 8.82 $\pm$ 0.36 & 216.5 $\pm$ 5.7 & 9472.5 $\pm$ 18.5 \\
EfficientNet-B0 & PlantVillage & 3 & 4.06 & 13.0 $\pm$ 1.7 & 127.8 $\pm$ 16.1 & 590.4 $\pm$ 21.2 & 9.26 $\pm$ 0.22 & 271.7 $\pm$ 5.7 & 9241.6 $\pm$ 6.9 \\
MobileNetV3-Small & PlantVillage & 3 & 1.56 & 13.0 $\pm$ 3.5 & 30.4 $\pm$ 7.1 & 141.2 $\pm$ 7.1 & 6.42 $\pm$ 0.31 & 1286.8 $\pm$ 22.8 & 2150.0 $\pm$ 9.2 \\
ResNet-50 & PlantDoc Core & 3 & 23.57 & 10.7 $\pm$ 2.1 & 11.3 $\pm$ 2.2 & 63.9 $\pm$ 7.6 & 8.58 $\pm$ 0.21 & 209.9 $\pm$ 5.7 & 11849.1 $\pm$ 591.2 \\
EfficientNet-B0 & PlantDoc Core & 3 & 4.04 & 9.3 $\pm$ 0.6 & 10.6 $\pm$ 1.9 & 67.8 $\pm$ 11.4 & 9.75 $\pm$ 0.17 & 192.6 $\pm$ 131.2 & 11829.6 $\pm$ 339.5 \\
MobileNetV3-Small & PlantDoc Core & 3 & 1.55 & 13.0 $\pm$ 2.0 & 2.7 $\pm$ 0.4 & 12.6 $\pm$ 0.3 & 6.28 $\pm$ 0.23 & 1268.4 $\pm$ 5.1 & 2150.7 $\pm$ 5.3 \\
\bottomrule
\end{tabular}
\end{table}
```

### table5 — domain-shift degradation (full)

Source: `experiments/ica26/tables/table5_domain_shift_degradation.tex`

```latex
\begin{table}[htbp]
\caption{Domain-shift degradation, mean $\pm$ sample standard deviation over three seeds. Drops are computed within each seed and then averaged, preserving the pairing between a checkpoint and its own cross-domain evaluation. In-domain is the PlantVillage test split over 38 classes; cross-domain is the PlantDoc Core shared-class subset over 21 classes. The two label spaces differ, so the drop combines domain shift with the change of task difficulty and should be read as a paired trend across models rather than as an isolated quantity.}
\label{tab:degradation}
\begin{tabular}{lrllllllll}
\toprule
Model & Seeds & Accuracy (in-domain) & Accuracy (cross-domain) & Accuracy abs. drop & Accuracy rel. drop \% & Macro-F1 (in-domain) & Macro-F1 (cross-domain) & Macro-F1 abs. drop & Macro-F1 rel. drop \% \\
\midrule
ResNet-50 & 3 & 0.9945 $\pm$ 0.0021 & 0.2583 $\pm$ 0.0206 & 0.7361 $\pm$ 0.0213 & 74.02 $\pm$ 2.09 & 0.9927 $\pm$ 0.0029 & 0.2291 $\pm$ 0.0107 & 0.7636 $\pm$ 0.0131 & 76.92 $\pm$ 1.13 \\
EfficientNet-B0 & 3 & 0.9964 $\pm$ 0.0005 & 0.2653 $\pm$ 0.0102 & 0.7310 $\pm$ 0.0097 & 73.37 $\pm$ 1.01 & 0.9950 $\pm$ 0.0006 & 0.2300 $\pm$ 0.0065 & 0.7650 $\pm$ 0.0064 & 76.89 $\pm$ 0.65 \\
MobileNetV3-Small & 3 & 0.9948 $\pm$ 0.0004 & 0.2238 $\pm$ 0.0162 & 0.7710 $\pm$ 0.0162 & 77.50 $\pm$ 1.63 & 0.9927 $\pm$ 0.0004 & 0.1869 $\pm$ 0.0109 & 0.8058 $\pm$ 0.0111 & 81.17 $\pm$ 1.10 \\
\bottomrule
\end{tabular}
\end{table}
```

### table5_compact — domain-shift degradation (paper)

Source: `experiments/ica26/tables/table5_domain_shift_degradation_compact.tex`

```latex
\begin{table}[htbp]
\caption{Domain-shift degradation in macro-F1, mean $\pm$ sample standard deviation over three seeds. Drops are computed within each seed and then averaged, preserving the pairing between a checkpoint and its own cross-domain evaluation. The label spaces differ (38-way in domain, 21-way cross-domain), so this is a paired trend across models, not an isolated quantity. Accuracy-based drops are in the supplementary table.}
\label{tab:degradation-compact}
\footnotesize
\centering
\begin{tabular}{lllll}
\toprule
Model & F1 in-dom. & F1 cross-dom. & Abs. drop & Rel. drop (\textbackslash \%) \\
\midrule
ResNet-50 & 0.9927 $\pm$ 0.0029 & 0.2291 $\pm$ 0.0107 & 0.7636 $\pm$ 0.0131 & 76.92 $\pm$ 1.13 \\
EfficientNet-B0 & 0.9950 $\pm$ 0.0006 & 0.2300 $\pm$ 0.0065 & 0.7650 $\pm$ 0.0064 & 76.89 $\pm$ 0.65 \\
MobileNetV3-Small & 0.9927 $\pm$ 0.0004 & 0.1869 $\pm$ 0.0109 & 0.8058 $\pm$ 0.0111 & 81.17 $\pm$ 1.10 \\
\bottomrule
\end{tabular}
\end{table}
```

### table6 — calibration and selective prediction (full)

Source: `experiments/ica26/tables/table6_calibration.tex`

```latex
\begin{table}[htbp]
\caption{Confidence calibration and selective prediction, mean $\pm$ sample standard deviation over three seeds. Temperature is fitted on the held-out validation split only and applied unchanged to test and cross-domain logits; it is never refitted on evaluation data. AURC is the area under the risk-coverage curve; lower is better.}
\label{tab:calibration}
\begin{tabular}{lllrllllll}
\toprule
Model & Dataset & Setting & Seeds & NLL & Brier & ECE & MCE & AURC & T \\
\midrule
ResNet-50 & PlantVillage & in-domain & 3 & 0.1218 $\pm$ 0.0138 & 0.0195 $\pm$ 0.0042 & 0.0987 $\pm$ 0.0113 & 0.3504 $\pm$ 0.0611 & 0.0007 $\pm$ 0.0002 & 1.0000 $\pm$ 0.0000 \\
ResNet-50 & PlantVillage & in-domain (T-scaled) & 3 & 0.0283 $\pm$ 0.0041 & 0.0092 $\pm$ 0.0026 & 0.0092 $\pm$ 0.0011 & 0.3061 $\pm$ 0.0897 & 0.0006 $\pm$ 0.0002 & 0.7028 $\pm$ 0.0076 \\
ResNet-50 & PlantVillage & cross-domain & 3 & 2.9441 $\pm$ 0.1055 & 0.9938 $\pm$ 0.0342 & 0.2829 $\pm$ 0.0459 & 0.5042 $\pm$ 0.0136 & 0.6428 $\pm$ 0.0282 & 1.0000 $\pm$ 0.0000 \\
ResNet-50 & PlantVillage & cross-domain (T-scaled) & 3 & 3.5879 $\pm$ 0.2283 & 1.1068 $\pm$ 0.0529 & 0.4178 $\pm$ 0.0533 & 0.6400 $\pm$ 0.0236 & 0.6427 $\pm$ 0.0282 & 0.7028 $\pm$ 0.0076 \\
EfficientNet-B0 & PlantVillage & in-domain & 3 & 0.1195 $\pm$ 0.0075 & 0.0165 $\pm$ 0.0019 & 0.1015 $\pm$ 0.0069 & 0.5075 $\pm$ 0.1154 & 0.0009 $\pm$ 0.0003 & 1.0000 $\pm$ 0.0000 \\
EfficientNet-B0 & PlantVillage & in-domain (T-scaled) & 3 & 0.0230 $\pm$ 0.0017 & 0.0059 $\pm$ 0.0006 & 0.0095 $\pm$ 0.0013 & 0.4969 $\pm$ 0.1793 & 0.0007 $\pm$ 0.0003 & 0.7006 $\pm$ 0.0040 \\
EfficientNet-B0 & PlantVillage & cross-domain & 3 & 2.8680 $\pm$ 0.0086 & 0.9588 $\pm$ 0.0242 & 0.2561 $\pm$ 0.0186 & 0.4783 $\pm$ 0.0577 & 0.6156 $\pm$ 0.0280 & 1.0000 $\pm$ 0.0000 \\
EfficientNet-B0 & PlantVillage & cross-domain (T-scaled) & 3 & 3.4624 $\pm$ 0.0278 & 1.0665 $\pm$ 0.0314 & 0.3973 $\pm$ 0.0192 & 0.5966 $\pm$ 0.0337 & 0.6152 $\pm$ 0.0295 & 0.7006 $\pm$ 0.0040 \\
MobileNetV3-Small & PlantVillage & in-domain & 3 & 0.1213 $\pm$ 0.0032 & 0.0199 $\pm$ 0.0015 & 0.0988 $\pm$ 0.0025 & 0.6900 $\pm$ 0.1577 & 0.0003 $\pm$ 0.0000 & 1.0000 $\pm$ 0.0000 \\
MobileNetV3-Small & PlantVillage & in-domain (T-scaled) & 3 & 0.0271 $\pm$ 0.0012 & 0.0086 $\pm$ 0.0006 & 0.0091 $\pm$ 0.0003 & 0.4771 $\pm$ 0.2112 & 0.0002 $\pm$ 0.0000 & 0.6976 $\pm$ 0.0046 \\
MobileNetV3-Small & PlantVillage & cross-domain & 3 & 2.7900 $\pm$ 0.0281 & 0.9296 $\pm$ 0.0068 & 0.1517 $\pm$ 0.0139 & 0.4799 $\pm$ 0.0438 & 0.6772 $\pm$ 0.0145 & 1.0000 $\pm$ 0.0000 \\
MobileNetV3-Small & PlantVillage & cross-domain (T-scaled) & 3 & 3.1303 $\pm$ 0.0525 & 1.0172 $\pm$ 0.0107 & 0.2938 $\pm$ 0.0128 & 0.5680 $\pm$ 0.0415 & 0.6769 $\pm$ 0.0145 & 0.6976 $\pm$ 0.0046 \\
ResNet-50 & PlantDoc Core & in-domain & 3 & 1.2067 $\pm$ 0.0168 & 0.4769 $\pm$ 0.0172 & 0.1157 $\pm$ 0.0079 & 0.2413 $\pm$ 0.0669 & 0.1642 $\pm$ 0.0185 & 1.0000 $\pm$ 0.0000 \\
ResNet-50 & PlantDoc Core & in-domain (T-scaled) & 3 & 1.1890 $\pm$ 0.0150 & 0.4699 $\pm$ 0.0187 & 0.0831 $\pm$ 0.0192 & 0.2254 $\pm$ 0.0373 & 0.1649 $\pm$ 0.0181 & 0.8780 $\pm$ 0.0447 \\
EfficientNet-B0 & PlantDoc Core & in-domain & 3 & 1.1907 $\pm$ 0.0022 & 0.4858 $\pm$ 0.0065 & 0.1318 $\pm$ 0.0204 & 0.4597 $\pm$ 0.3660 & 0.1642 $\pm$ 0.0147 & 1.0000 $\pm$ 0.0000 \\
EfficientNet-B0 & PlantDoc Core & in-domain (T-scaled) & 3 & 1.1332 $\pm$ 0.0075 & 0.4671 $\pm$ 0.0127 & 0.0659 $\pm$ 0.0183 & 0.2648 $\pm$ 0.0797 & 0.1632 $\pm$ 0.0129 & 0.7796 $\pm$ 0.0448 \\
MobileNetV3-Small & PlantDoc Core & in-domain & 3 & 1.5064 $\pm$ 0.0506 & 0.5952 $\pm$ 0.0185 & 0.1456 $\pm$ 0.0100 & 0.3238 $\pm$ 0.0464 & 0.2350 $\pm$ 0.0134 & 1.0000 $\pm$ 0.0000 \\
MobileNetV3-Small & PlantDoc Core & in-domain (T-scaled) & 3 & 1.4666 $\pm$ 0.0592 & 0.5822 $\pm$ 0.0215 & 0.0868 $\pm$ 0.0318 & 0.2306 $\pm$ 0.0163 & 0.2365 $\pm$ 0.0154 & 0.8317 $\pm$ 0.0512 \\
\bottomrule
\end{tabular}
\end{table}
```

### table6_compact — calibration (paper)

Source: `experiments/ica26/tables/table6_calibration_compact.tex`

```latex
\begin{table}[htbp]
\caption{Expected calibration error, mean $\pm$ sample standard deviation over three seeds. `T' is the temperature fitted on the held-out validation split and applied unchanged; it is never refitted on evaluation data. Temperature does not move the argmax, so accuracy is unchanged by it. Negative log-likelihood, Brier score, maximum calibration error, and AURC are in the supplementary table.}
\label{tab:calibration-compact}
\footnotesize
\centering
\begin{tabular}{lllll}
\toprule
Model & Corpus & Setting & ECE & T \\
\midrule
ResNet-50 & PV & in-dom. & 0.0987 $\pm$ 0.0113 & 1.0000 $\pm$ 0.0000 \\
ResNet-50 & PV & in-dom. (T) & 0.0092 $\pm$ 0.0011 & 0.7028 $\pm$ 0.0076 \\
ResNet-50 & PV & cross-dom. & 0.2829 $\pm$ 0.0459 & 1.0000 $\pm$ 0.0000 \\
ResNet-50 & PV & cross-dom. (T) & 0.4178 $\pm$ 0.0533 & 0.7028 $\pm$ 0.0076 \\
EfficientNet-B0 & PV & in-dom. & 0.1015 $\pm$ 0.0069 & 1.0000 $\pm$ 0.0000 \\
EfficientNet-B0 & PV & in-dom. (T) & 0.0095 $\pm$ 0.0013 & 0.7006 $\pm$ 0.0040 \\
EfficientNet-B0 & PV & cross-dom. & 0.2561 $\pm$ 0.0186 & 1.0000 $\pm$ 0.0000 \\
EfficientNet-B0 & PV & cross-dom. (T) & 0.3973 $\pm$ 0.0192 & 0.7006 $\pm$ 0.0040 \\
MobileNetV3-Small & PV & in-dom. & 0.0988 $\pm$ 0.0025 & 1.0000 $\pm$ 0.0000 \\
MobileNetV3-Small & PV & in-dom. (T) & 0.0091 $\pm$ 0.0003 & 0.6976 $\pm$ 0.0046 \\
MobileNetV3-Small & PV & cross-dom. & 0.1517 $\pm$ 0.0139 & 1.0000 $\pm$ 0.0000 \\
MobileNetV3-Small & PV & cross-dom. (T) & 0.2938 $\pm$ 0.0128 & 0.6976 $\pm$ 0.0046 \\
ResNet-50 & PDC & in-dom. & 0.1157 $\pm$ 0.0079 & 1.0000 $\pm$ 0.0000 \\
ResNet-50 & PDC & in-dom. (T) & 0.0831 $\pm$ 0.0192 & 0.8780 $\pm$ 0.0447 \\
EfficientNet-B0 & PDC & in-dom. & 0.1318 $\pm$ 0.0204 & 1.0000 $\pm$ 0.0000 \\
EfficientNet-B0 & PDC & in-dom. (T) & 0.0659 $\pm$ 0.0183 & 0.7796 $\pm$ 0.0448 \\
MobileNetV3-Small & PDC & in-dom. & 0.1456 $\pm$ 0.0100 & 1.0000 $\pm$ 0.0000 \\
MobileNetV3-Small & PDC & in-dom. (T) & 0.0868 $\pm$ 0.0318 & 0.8317 $\pm$ 0.0512 \\
\bottomrule
\end{tabular}
\end{table}
```

### table7 — backbone ranking stability across seeds

Source: `experiments/ica26/tables/table7_ranking_stability.tex`

```latex
\begin{table}[htbp]
\caption{Backbone ranking by macro-F1 under each evaluation setting, per seed. A setting is STABLE when all seeds agree on the ordering. This is the direct test of whether the in-domain ranking predicts the cross-domain ranking, or whether an apparent reordering is within seed noise.}
\label{tab:ranking-stability}
\begin{tabular}{lllrrr}
\toprule
Setting & Seed & Ranking (macro-F1; best first) & ResNet-50 macro-F1 & EfficientNet-B0 macro-F1 & MobileNetV3-Small macro-F1 \\
\midrule
PlantVillage in-domain & 42 & EfficientNet-B0 $>$ MobileNetV3-Small $>$ ResNet-50 & 0.9899 & 0.9956 & 0.9927 \\
PlantVillage in-domain & 1337 & EfficientNet-B0 $>$ MobileNetV3-Small $>$ ResNet-50 & 0.9925 & 0.9944 & 0.9931 \\
PlantVillage in-domain & 2026 & ResNet-50 $>$ EfficientNet-B0 $>$ MobileNetV3-Small & 0.9957 & 0.9951 & 0.9923 \\
PlantVillage in-domain & all & UNSTABLE: 2/3 seeds give EfficientNet-B0 $>$ MobileNetV3-Small $>$ ResNet-50 & 0.9927 & 0.9950 & 0.9927 \\
PlantVillage $\rightarrow$ PlantDoc Core & 42 & ResNet-50 $>$ EfficientNet-B0 $>$ MobileNetV3-Small & 0.2414 & 0.2359 & 0.1982 \\
PlantVillage $\rightarrow$ PlantDoc Core & 1337 & EfficientNet-B0 $>$ ResNet-50 $>$ MobileNetV3-Small & 0.2218 & 0.2312 & 0.1764 \\
PlantVillage $\rightarrow$ PlantDoc Core & 2026 & ResNet-50 $>$ EfficientNet-B0 $>$ MobileNetV3-Small & 0.2242 & 0.2230 & 0.1862 \\
PlantVillage $\rightarrow$ PlantDoc Core & all & UNSTABLE: 2/3 seeds give ResNet-50 $>$ EfficientNet-B0 $>$ MobileNetV3-Small & 0.2291 & 0.2300 & 0.1869 \\
PlantDoc Core in-domain & 42 & ResNet-50 $>$ EfficientNet-B0 $>$ MobileNetV3-Small & 0.6994 & 0.6927 & 0.5841 \\
PlantDoc Core in-domain & 1337 & ResNet-50 $>$ EfficientNet-B0 $>$ MobileNetV3-Small & 0.7094 & 0.6663 & 0.5946 \\
PlantDoc Core in-domain & 2026 & EfficientNet-B0 $>$ ResNet-50 $>$ MobileNetV3-Small & 0.6381 & 0.6716 & 0.5840 \\
PlantDoc Core in-domain & all & UNSTABLE: 2/3 seeds give ResNet-50 $>$ EfficientNet-B0 $>$ MobileNetV3-Small & 0.6823 & 0.6768 & 0.5876 \\
\bottomrule
\end{tabular}
\end{table}
```

### table7b — pairwise ranking margins vs seed noise

Source: `experiments/ica26/tables/table7b_ranking_margins.tex`

```latex
\begin{table}[htbp]
\caption{Pairwise macro-F1 margins against seed noise. The margin is computed within each seed and then averaged. Pooled seed SD is the root-mean-square of the two models' across-seed standard deviations. A margin comfortably exceeding the seed SD, with a consistent sign across all seeds, is a difference the seed alone does not explain; one below it is not claimed. With three seeds these are descriptive ratios, not significance tests.}
\label{tab:ranking-margins}
\begin{tabular}{llrllll}
\toprule
Setting & Comparison & Seeds & Mean margin & Pooled seed SD & |Margin| / seed SD & Sign consistent \\
\midrule
PlantVillage in-domain & ResNet-50 - EfficientNet-B0 & 3 & -0.0023 $\pm$ 0.0032 & 0.0021 & 1.11 & 2/3 \\
PlantVillage in-domain & ResNet-50 - MobileNetV3-Small & 3 & 0.0000 $\pm$ 0.0031 & 0.0021 & 0.02 & 2/3 \\
PlantVillage in-domain & EfficientNet-B0 - MobileNetV3-Small & 3 & 0.0023 $\pm$ 0.0008 & 0.0005 & 4.73 & 3/3 \\
PlantVillage $\rightarrow$ PlantDoc Core & ResNet-50 - EfficientNet-B0 & 3 & -0.0009 $\pm$ 0.0077 & 0.0089 & 0.10 & 2/3 \\
PlantVillage $\rightarrow$ PlantDoc Core & ResNet-50 - MobileNetV3-Small & 3 & 0.0422 $\pm$ 0.0038 & 0.0108 & 3.90 & 3/3 \\
PlantVillage $\rightarrow$ PlantDoc Core & EfficientNet-B0 - MobileNetV3-Small & 3 & 0.0431 $\pm$ 0.0102 & 0.0090 & 4.78 & 3/3 \\
PlantDoc Core in-domain & ResNet-50 - EfficientNet-B0 & 3 & 0.0054 $\pm$ 0.0383 & 0.0290 & 0.19 & 2/3 \\
PlantDoc Core in-domain & ResNet-50 - MobileNetV3-Small & 3 & 0.0947 $\pm$ 0.0352 & 0.0276 & 3.43 & 3/3 \\
PlantDoc Core in-domain & EfficientNet-B0 - MobileNetV3-Small & 3 & 0.0893 $\pm$ 0.0185 & 0.0108 & 8.30 & 3/3 \\
\bottomrule
\end{tabular}
\end{table}
```

### table8 — BCa bootstrap confidence intervals

Source: `experiments/ica26/tables/table8_confidence_intervals.tex`

```latex
\begin{table}[htbp]
\caption{BCa bootstrap 95\% confidence intervals for accuracy and macro-F1, seed 42, 10000 resamples. Intervals describe sampling variability of the fixed evaluation set for one trained checkpoint; they are not seed variance, which is reported separately.}
\label{tab:confidence-intervals}
\begin{tabular}{llrllll}
\toprule
Setting & Model & N & Accuracy & Accuracy 95\% CI & Macro-F1 & Macro-F1 95\% CI \\
\midrule
PlantVillage in-domain & ResNet-50 & 10709 & 0.9925 & [0.9908, 0.9940] & 0.9899 & [0.9870, 0.9922] \\
PlantVillage in-domain & EfficientNet-B0 & 10709 & 0.9968 & [0.9956, 0.9978] & 0.9956 & [0.9938, 0.9969] \\
PlantVillage in-domain & MobileNetV3-Small & 10709 & 0.9950 & [0.9935, 0.9962] & 0.9927 & [0.9901, 0.9948] \\
PlantDoc Core in-domain & ResNet-50 & 225 & 0.6933 & [0.6311, 0.7511] & 0.6994 & [0.6526, 0.7721] \\
PlantDoc Core in-domain & EfficientNet-B0 & 225 & 0.6800 & [0.6178, 0.7378] & 0.6927 & [0.6457, 0.7598] \\
PlantDoc Core in-domain & MobileNetV3-Small & 225 & 0.5556 & [0.4889, 0.6222] & 0.5841 & [0.5352, 0.6675] \\
PlantVillage $\rightarrow$ PlantDoc Core & ResNet-50 & 1951 & 0.2778 & [0.2584, 0.2978] & 0.2414 & [0.2253, 0.2595] \\
PlantVillage $\rightarrow$ PlantDoc Core & EfficientNet-B0 & 1951 & 0.2742 & [0.2553, 0.2942] & 0.2359 & [0.2203, 0.2538] \\
PlantVillage $\rightarrow$ PlantDoc Core & MobileNetV3-Small & 1951 & 0.2419 & [0.2230, 0.2609] & 0.1982 & [0.1831, 0.2158] \\
\bottomrule
\end{tabular}
\end{table}
```

### table8b — pairwise McNemar exact tests

Source: `experiments/ica26/tables/table8b_mcnemar.tex`

```latex
\begin{table}[htbp]
\caption{Pairwise McNemar exact tests on per-item correctness, seed 42. `A only' and `B only' are the discordant counts the test is computed from. Holm-adjusted p-values control the family-wise error rate across all pairwise tests reported here.}
\label{tab:mcnemar}
\begin{tabular}{lllllrrrll}
\toprule
Setting & Comparison & Acc. A & Acc. B & Diff. & A only & B only & Discordant & p (exact) & p (Holm) \\
\midrule
PlantVillage in-domain & ResNet-50 vs EfficientNet-B0 & 0.9925 & 0.9968 & -0.0043 & 18 & 64 & 82 & <0.0001 & <0.0001 \\
PlantVillage in-domain & ResNet-50 vs MobileNetV3-Small & 0.9925 & 0.9950 & -0.0024 & 34 & 60 & 94 & 0.0095 & 0.0363 \\
PlantVillage in-domain & EfficientNet-B0 vs MobileNetV3-Small & 0.9968 & 0.9950 & +0.0019 & 37 & 17 & 54 & 0.0091 & 0.0363 \\
PlantDoc Core in-domain & ResNet-50 vs EfficientNet-B0 & 0.6933 & 0.6800 & +0.0133 & 20 & 17 & 37 & 0.7428 & 1.0000 \\
PlantDoc Core in-domain & ResNet-50 vs MobileNetV3-Small & 0.6933 & 0.5556 & +0.1378 & 48 & 17 & 65 & 0.0002 & 0.0012 \\
PlantDoc Core in-domain & EfficientNet-B0 vs MobileNetV3-Small & 0.6800 & 0.5556 & +0.1244 & 47 & 19 & 66 & 0.0008 & 0.0045 \\
PlantVillage $\rightarrow$ PlantDoc Core & ResNet-50 vs EfficientNet-B0 & 0.2778 & 0.2742 & +0.0036 & 179 & 172 & 351 & 0.7488 & 1.0000 \\
PlantVillage $\rightarrow$ PlantDoc Core & ResNet-50 vs MobileNetV3-Small & 0.2778 & 0.2419 & +0.0359 & 207 & 137 & 344 & 0.0002 & 0.0013 \\
PlantVillage $\rightarrow$ PlantDoc Core & EfficientNet-B0 vs MobileNetV3-Small & 0.2742 & 0.2419 & +0.0323 & 205 & 142 & 347 & 0.0008 & 0.0045 \\
\bottomrule
\end{tabular}
\end{table}
```

### table9 — significance across seeds

Source: `experiments/ica26/tables/table9_significance_across_seeds.tex`

```latex
\begin{table}[htbp]
\caption{Stability of each pairwise verdict across independent training seeds. Each seed's McNemar test is computed on that seed's own checkpoints and Holm-adjusted within that seed. A comparison significant in every seed is a conclusion about the architectures; one significant in a single seed is a statement about that run.}
\label{tab:significance-across-seeds}
\begin{tabular}{llrlll}
\toprule
Setting & Comparison & Seeds & Significant (Holm) & Sign consistent & Mean acc. diff. \\
\midrule
PlantVillage in-domain & ResNet-50 vs EfficientNet-B0 & 3 & 1/3 & no & -0.0019 \\
PlantVillage in-domain & ResNet-50 vs MobileNetV3-Small & 3 & 2/3 & no & -0.0003 \\
PlantVillage in-domain & EfficientNet-B0 vs MobileNetV3-Small & 3 & 2/3 & yes & +0.0016 \\
PlantDoc Core in-domain & ResNet-50 vs EfficientNet-B0 & 3 & 0/3 & no & -0.0015 \\
PlantDoc Core in-domain & ResNet-50 vs MobileNetV3-Small & 3 & 2/3 & yes & +0.1037 \\
PlantDoc Core in-domain & EfficientNet-B0 vs MobileNetV3-Small & 3 & 3/3 & yes & +0.1052 \\
PlantVillage $\rightarrow$ PlantDoc Core & ResNet-50 vs EfficientNet-B0 & 3 & 0/3 & no & -0.0070 \\
PlantVillage $\rightarrow$ PlantDoc Core & ResNet-50 vs MobileNetV3-Small & 3 & 3/3 & yes & +0.0345 \\
PlantVillage $\rightarrow$ PlantDoc Core & EfficientNet-B0 vs MobileNetV3-Small & 3 & 3/3 & yes & +0.0415 \\
\bottomrule
\end{tabular}
\end{table}
```

---

## 2. generated/results_macros.tex

Source: `paper/generated/results_macros.tex`

```latex
% ICA 2026 -- generated result macros. DO NOT EDIT BY HAND.
%
% Written by scripts/ica26_build_paper_macros.py from:
%   data/manifests/ica26_core_experiment_lock.json
%   experiments/ica26/metrics/*.json
%   experiments/ica26/metrics/significance.json
%
% Regenerate after any run completes:
%   python scripts/ica26_build_paper_macros.py
%
% seeds complete : [42, 1337, 2026]
% runs complete  : 18/18
% pending macros : 0

% Typeset marker for a number that does not exist yet. A draft with any
% of these is visibly incomplete rather than quietly wrong.
\providecommand{\ResultPending}{\textbf{[PENDING]}}

% --- provenance ----------------------------------------------------------
\newcommand{\LockDigest}{\texttt{83449f6013691855}}
\newcommand{\LockDigestFull}{\texttt{83449f6013691855\allowbreak 4904cb9c596122f8\allowbreak b89cb51ff5bb5c52\allowbreak c541394a5698082d}}
\newcommand{\NSeedsDone}{3}
\newcommand{\SeedList}{42, 1337, 2026}
\newcommand{\NRunsDone}{18}
\newcommand{\NRunsPlanned}{18}

% --- numerical guard -----------------------------------------------------
\newcommand{\NRunsWithSkippedSteps}{1}
\newcommand{\NSkippedSteps}{11}
\newcommand{\NGuardedRuns}{10}
\newcommand{\NGuardedOptimiserSteps}{38\,036}
\newcommand{\RunsWithSkippedSteps}{\texttt{pv\_efficientnet\_b0\_s1337} (11)}
\newcommand{\SkippedStepsNote}{1 of 10 runs trained under the guard skipped a step, 11 in total out of 38\,036: \texttt{pv\_efficientnet\_b0\_s1337} (11)}

% --- dataset composition -------------------------------------------------
\newcommand{\NPv}{54\,305}
\newcommand{\NPvTrain}{43\,596}
\newcommand{\NPvTest}{10\,709}
\newcommand{\NPvClasses}{38}
\newcommand{\NPdcAcquired}{2\,578}
\newcommand{\NPdc}{2\,561}
\newcommand{\NPdcTrain}{2\,336}
\newcommand{\NPdcTest}{225}
\newcommand{\NPdcClasses}{28}
\newcommand{\NPdcExcludedDup}{14}
\newcommand{\NPdcExcludedReview}{3}
\newcommand{\NSharedClasses}{21}
\newcommand{\NXdImages}{1\,951}
\newcommand{\NLeakExactAcq}{0}
\newcommand{\NLeakNearAcq}{16}
\newcommand{\NLeakExactCore}{0}
\newcommand{\NLeakNearCore}{16}
\newcommand{\NLeakUnresolved}{0}

% --- leakage audit -------------------------------------------------------
\newcommand{\NPhashComparisons}{136\,847\,443}
\newcommand{\NPhashComparisonsSci}{\ensuremath{1.37 \times 10^{8}}}
\newcommand{\PhashBits}{64}
\newcommand{\LeakThreshold}{6}

% --- corpus shape --------------------------------------------------------
\newcommand{\PdcImbalance}{90}
\newcommand{\PdcLargestClass}{180}
\newcommand{\PdcSmallestClass}{2}
\newcommand{\NPdcTestClasses}{27}

% --- results: PvIn -------------------------------------------------------
\newcommand{\AccPvInRn}{\ensuremath{0.9945 \pm 0.0021}}
\newcommand{\MacroFPvInRn}{\ensuremath{0.9927 \pm 0.0029}}
\newcommand{\BalAccPvInRn}{\ensuremath{0.9923 \pm 0.0029}}
\newcommand{\EcePvInRn}{\ensuremath{0.0987 \pm 0.0113}}
\newcommand{\NllPvInRn}{\ensuremath{0.122 \pm 0.014}}
\newcommand{\BrierPvInRn}{\ensuremath{0.0195 \pm 0.0042}}
\newcommand{\AurcPvInRn}{\ensuremath{0.0007 \pm 0.0002}}
\newcommand{\AccMeanPvInRn}{0.9945}
\newcommand{\MacroFMeanPvInRn}{0.9927}
\newcommand{\AccPvInEb}{\ensuremath{0.9964 \pm 0.0005}}
\newcommand{\MacroFPvInEb}{\ensuremath{0.9950 \pm 0.0006}}
\newcommand{\BalAccPvInEb}{\ensuremath{0.9945 \pm 0.0008}}
\newcommand{\EcePvInEb}{\ensuremath{0.1015 \pm 0.0069}}
\newcommand{\NllPvInEb}{\ensuremath{0.119 \pm 0.007}}
\newcommand{\BrierPvInEb}{\ensuremath{0.0165 \pm 0.0019}}
\newcommand{\AurcPvInEb}{\ensuremath{0.0009 \pm 0.0003}}
\newcommand{\AccMeanPvInEb}{0.9964}
\newcommand{\MacroFMeanPvInEb}{0.9950}
\newcommand{\AccPvInMn}{\ensuremath{0.9948 \pm 0.0004}}
\newcommand{\MacroFPvInMn}{\ensuremath{0.9927 \pm 0.0004}}
\newcommand{\BalAccPvInMn}{\ensuremath{0.9916 \pm 0.0003}}
\newcommand{\EcePvInMn}{\ensuremath{0.0988 \pm 0.0025}}
\newcommand{\NllPvInMn}{\ensuremath{0.121 \pm 0.003}}
\newcommand{\BrierPvInMn}{\ensuremath{0.0199 \pm 0.0015}}
\newcommand{\AurcPvInMn}{\ensuremath{0.0003 \pm 0.0000}}
\newcommand{\AccMeanPvInMn}{0.9948}
\newcommand{\MacroFMeanPvInMn}{0.9927}

% --- results: PvInT ------------------------------------------------------
\newcommand{\AccPvInTRn}{\ensuremath{0.9945 \pm 0.0021}}
\newcommand{\MacroFPvInTRn}{\ensuremath{0.9927 \pm 0.0029}}
\newcommand{\BalAccPvInTRn}{\ensuremath{0.9923 \pm 0.0029}}
\newcommand{\EcePvInTRn}{\ensuremath{0.0092 \pm 0.0011}}
\newcommand{\NllPvInTRn}{\ensuremath{0.028 \pm 0.004}}
\newcommand{\BrierPvInTRn}{\ensuremath{0.0092 \pm 0.0026}}
\newcommand{\AurcPvInTRn}{\ensuremath{0.0006 \pm 0.0002}}
\newcommand{\AccMeanPvInTRn}{0.9945}
\newcommand{\MacroFMeanPvInTRn}{0.9927}
\newcommand{\AccPvInTEb}{\ensuremath{0.9964 \pm 0.0005}}
\newcommand{\MacroFPvInTEb}{\ensuremath{0.9950 \pm 0.0006}}
\newcommand{\BalAccPvInTEb}{\ensuremath{0.9945 \pm 0.0008}}
\newcommand{\EcePvInTEb}{\ensuremath{0.0095 \pm 0.0013}}
\newcommand{\NllPvInTEb}{\ensuremath{0.023 \pm 0.002}}
\newcommand{\BrierPvInTEb}{\ensuremath{0.0059 \pm 0.0006}}
\newcommand{\AurcPvInTEb}{\ensuremath{0.0007 \pm 0.0003}}
\newcommand{\AccMeanPvInTEb}{0.9964}
\newcommand{\MacroFMeanPvInTEb}{0.9950}
\newcommand{\AccPvInTMn}{\ensuremath{0.9948 \pm 0.0004}}
\newcommand{\MacroFPvInTMn}{\ensuremath{0.9927 \pm 0.0004}}
\newcommand{\BalAccPvInTMn}{\ensuremath{0.9916 \pm 0.0003}}
\newcommand{\EcePvInTMn}{\ensuremath{0.0091 \pm 0.0003}}
\newcommand{\NllPvInTMn}{\ensuremath{0.027 \pm 0.001}}
\newcommand{\BrierPvInTMn}{\ensuremath{0.0086 \pm 0.0006}}
\newcommand{\AurcPvInTMn}{\ensuremath{0.0002 \pm 0.0000}}
\newcommand{\AccMeanPvInTMn}{0.9948}
\newcommand{\MacroFMeanPvInTMn}{0.9927}

% --- results: PdcIn ------------------------------------------------------
\newcommand{\AccPdcInRn}{\ensuremath{0.6637 \pm 0.0403}}
\newcommand{\MacroFPdcInRn}{\ensuremath{0.6823 \pm 0.0386}}
\newcommand{\BalAccPdcInRn}{\ensuremath{0.6551 \pm 0.0393}}
\newcommand{\EcePdcInRn}{\ensuremath{0.1157 \pm 0.0079}}
\newcommand{\NllPdcInRn}{\ensuremath{1.207 \pm 0.017}}
\newcommand{\BrierPdcInRn}{\ensuremath{0.4769 \pm 0.0172}}
\newcommand{\AurcPdcInRn}{\ensuremath{0.1642 \pm 0.0185}}
\newcommand{\AccMeanPdcInRn}{0.6637}
\newcommand{\MacroFMeanPdcInRn}{0.6823}
\newcommand{\AccPdcInEb}{\ensuremath{0.6652 \pm 0.0128}}
\newcommand{\MacroFPdcInEb}{\ensuremath{0.6768 \pm 0.0139}}
\newcommand{\BalAccPdcInEb}{\ensuremath{0.6569 \pm 0.0087}}
\newcommand{\EcePdcInEb}{\ensuremath{0.1318 \pm 0.0204}}
\newcommand{\NllPdcInEb}{\ensuremath{1.191 \pm 0.002}}
\newcommand{\BrierPdcInEb}{\ensuremath{0.4858 \pm 0.0065}}
\newcommand{\AurcPdcInEb}{\ensuremath{0.1642 \pm 0.0147}}
\newcommand{\AccMeanPdcInEb}{0.6652}
\newcommand{\MacroFMeanPdcInEb}{0.6768}
\newcommand{\AccPdcInMn}{\ensuremath{0.5600 \pm 0.0044}}
\newcommand{\MacroFPdcInMn}{\ensuremath{0.5876 \pm 0.0061}}
\newcommand{\BalAccPdcInMn}{\ensuremath{0.5640 \pm 0.0030}}
\newcommand{\EcePdcInMn}{\ensuremath{0.1456 \pm 0.0100}}
\newcommand{\NllPdcInMn}{\ensuremath{1.506 \pm 0.051}}
\newcommand{\BrierPdcInMn}{\ensuremath{0.5952 \pm 0.0185}}
\newcommand{\AurcPdcInMn}{\ensuremath{0.2350 \pm 0.0134}}
\newcommand{\AccMeanPdcInMn}{0.5600}
\newcommand{\MacroFMeanPdcInMn}{0.5876}

% --- results: PdcInT -----------------------------------------------------
\newcommand{\AccPdcInTRn}{\ensuremath{0.6637 \pm 0.0403}}
\newcommand{\MacroFPdcInTRn}{\ensuremath{0.6823 \pm 0.0386}}
\newcommand{\BalAccPdcInTRn}{\ensuremath{0.6551 \pm 0.0393}}
\newcommand{\EcePdcInTRn}{\ensuremath{0.0831 \pm 0.0192}}
\newcommand{\NllPdcInTRn}{\ensuremath{1.189 \pm 0.015}}
\newcommand{\BrierPdcInTRn}{\ensuremath{0.4699 \pm 0.0187}}
\newcommand{\AurcPdcInTRn}{\ensuremath{0.1649 \pm 0.0181}}
\newcommand{\AccMeanPdcInTRn}{0.6637}
\newcommand{\MacroFMeanPdcInTRn}{0.6823}
\newcommand{\AccPdcInTEb}{\ensuremath{0.6652 \pm 0.0128}}
\newcommand{\MacroFPdcInTEb}{\ensuremath{0.6768 \pm 0.0139}}
\newcommand{\BalAccPdcInTEb}{\ensuremath{0.6569 \pm 0.0087}}
\newcommand{\EcePdcInTEb}{\ensuremath{0.0659 \pm 0.0183}}
\newcommand{\NllPdcInTEb}{\ensuremath{1.133 \pm 0.007}}
\newcommand{\BrierPdcInTEb}{\ensuremath{0.4671 \pm 0.0127}}
\newcommand{\AurcPdcInTEb}{\ensuremath{0.1632 \pm 0.0129}}
\newcommand{\AccMeanPdcInTEb}{0.6652}
\newcommand{\MacroFMeanPdcInTEb}{0.6768}
\newcommand{\AccPdcInTMn}{\ensuremath{0.5600 \pm 0.0044}}
\newcommand{\MacroFPdcInTMn}{\ensuremath{0.5876 \pm 0.0061}}
\newcommand{\BalAccPdcInTMn}{\ensuremath{0.5640 \pm 0.0030}}
\newcommand{\EcePdcInTMn}{\ensuremath{0.0868 \pm 0.0318}}
\newcommand{\NllPdcInTMn}{\ensuremath{1.467 \pm 0.059}}
\newcommand{\BrierPdcInTMn}{\ensuremath{0.5822 \pm 0.0215}}
\newcommand{\AurcPdcInTMn}{\ensuremath{0.2365 \pm 0.0154}}
\newcommand{\AccMeanPdcInTMn}{0.5600}
\newcommand{\MacroFMeanPdcInTMn}{0.5876}

% --- results: Xd ---------------------------------------------------------
\newcommand{\AccXdRn}{\ensuremath{0.2583 \pm 0.0206}}
\newcommand{\MacroFXdRn}{\ensuremath{0.2291 \pm 0.0107}}
\newcommand{\BalAccXdRn}{\ensuremath{0.2389 \pm 0.0188}}
\newcommand{\EceXdRn}{\ensuremath{0.2829 \pm 0.0459}}
\newcommand{\NllXdRn}{\ensuremath{2.944 \pm 0.106}}
\newcommand{\BrierXdRn}{\ensuremath{0.9938 \pm 0.0342}}
\newcommand{\AurcXdRn}{\ensuremath{0.6428 \pm 0.0282}}
\newcommand{\AccMeanXdRn}{0.2583}
\newcommand{\MacroFMeanXdRn}{0.2291}
\newcommand{\AccXdEb}{\ensuremath{0.2653 \pm 0.0102}}
\newcommand{\MacroFXdEb}{\ensuremath{0.2300 \pm 0.0065}}
\newcommand{\BalAccXdEb}{\ensuremath{0.2475 \pm 0.0110}}
\newcommand{\EceXdEb}{\ensuremath{0.2561 \pm 0.0186}}
\newcommand{\NllXdEb}{\ensuremath{2.868 \pm 0.009}}
\newcommand{\BrierXdEb}{\ensuremath{0.9588 \pm 0.0242}}
\newcommand{\AurcXdEb}{\ensuremath{0.6156 \pm 0.0280}}
\newcommand{\AccMeanXdEb}{0.2653}
\newcommand{\MacroFMeanXdEb}{0.2300}
\newcommand{\AccXdMn}{\ensuremath{0.2238 \pm 0.0162}}
\newcommand{\MacroFXdMn}{\ensuremath{0.1869 \pm 0.0109}}
\newcommand{\BalAccXdMn}{\ensuremath{0.2141 \pm 0.0135}}
\newcommand{\EceXdMn}{\ensuremath{0.1517 \pm 0.0139}}
\newcommand{\NllXdMn}{\ensuremath{2.790 \pm 0.028}}
\newcommand{\BrierXdMn}{\ensuremath{0.9296 \pm 0.0068}}
\newcommand{\AurcXdMn}{\ensuremath{0.6772 \pm 0.0145}}
\newcommand{\AccMeanXdMn}{0.2238}
\newcommand{\MacroFMeanXdMn}{0.1869}

% --- results: XdT --------------------------------------------------------
\newcommand{\AccXdTRn}{\ensuremath{0.2583 \pm 0.0206}}
\newcommand{\MacroFXdTRn}{\ensuremath{0.2291 \pm 0.0107}}
\newcommand{\BalAccXdTRn}{\ensuremath{0.2389 \pm 0.0188}}
\newcommand{\EceXdTRn}{\ensuremath{0.4178 \pm 0.0533}}
\newcommand{\NllXdTRn}{\ensuremath{3.588 \pm 0.228}}
\newcommand{\BrierXdTRn}{\ensuremath{1.1068 \pm 0.0529}}
\newcommand{\AurcXdTRn}{\ensuremath{0.6427 \pm 0.0282}}
\newcommand{\AccMeanXdTRn}{0.2583}
\newcommand{\MacroFMeanXdTRn}{0.2291}
\newcommand{\AccXdTEb}{\ensuremath{0.2653 \pm 0.0102}}
\newcommand{\MacroFXdTEb}{\ensuremath{0.2300 \pm 0.0065}}
\newcommand{\BalAccXdTEb}{\ensuremath{0.2475 \pm 0.0110}}
\newcommand{\EceXdTEb}{\ensuremath{0.3973 \pm 0.0192}}
\newcommand{\NllXdTEb}{\ensuremath{3.462 \pm 0.028}}
\newcommand{\BrierXdTEb}{\ensuremath{1.0665 \pm 0.0314}}
\newcommand{\AurcXdTEb}{\ensuremath{0.6152 \pm 0.0295}}
\newcommand{\AccMeanXdTEb}{0.2653}
\newcommand{\MacroFMeanXdTEb}{0.2300}
\newcommand{\AccXdTMn}{\ensuremath{0.2238 \pm 0.0162}}
\newcommand{\MacroFXdTMn}{\ensuremath{0.1869 \pm 0.0109}}
\newcommand{\BalAccXdTMn}{\ensuremath{0.2141 \pm 0.0135}}
\newcommand{\EceXdTMn}{\ensuremath{0.2938 \pm 0.0128}}
\newcommand{\NllXdTMn}{\ensuremath{3.130 \pm 0.052}}
\newcommand{\BrierXdTMn}{\ensuremath{1.0172 \pm 0.0107}}
\newcommand{\AurcXdTMn}{\ensuremath{0.6769 \pm 0.0145}}
\newcommand{\AccMeanXdTMn}{0.2238}
\newcommand{\MacroFMeanXdTMn}{0.1869}

% --- calibration: fitted temperature -------------------------------------
\newcommand{\TempPvRn}{\ensuremath{0.7028 \pm 0.0076}}
\newcommand{\TempPdcRn}{\ensuremath{0.8780 \pm 0.0447}}
\newcommand{\TempPvEb}{\ensuremath{0.7006 \pm 0.0040}}
\newcommand{\TempPdcEb}{\ensuremath{0.7796 \pm 0.0448}}
\newcommand{\TempPvMn}{\ensuremath{0.6976 \pm 0.0046}}
\newcommand{\TempPdcMn}{\ensuremath{0.8317 \pm 0.0512}}

% --- domain-shift degradation --------------------------------------------
\newcommand{\RelDropAccRn}{\ensuremath{74.0 \pm 2.1}}
\newcommand{\RelDropFRn}{\ensuremath{76.9 \pm 1.1}}
\newcommand{\AbsDropFRn}{\ensuremath{0.7636 \pm 0.0131}}
\newcommand{\RelDropFMeanRn}{76.9}
\newcommand{\RelDropAccEb}{\ensuremath{73.4 \pm 1.0}}
\newcommand{\RelDropFEb}{\ensuremath{76.9 \pm 0.7}}
\newcommand{\AbsDropFEb}{\ensuremath{0.7650 \pm 0.0064}}
\newcommand{\RelDropFMeanEb}{76.9}
\newcommand{\RelDropAccMn}{\ensuremath{77.5 \pm 1.6}}
\newcommand{\RelDropFMn}{\ensuremath{81.2 \pm 1.1}}
\newcommand{\AbsDropFMn}{\ensuremath{0.8058 \pm 0.0111}}
\newcommand{\RelDropFMeanMn}{81.2}

% --- cross-domain protocol -----------------------------------------------
\newcommand{\RetainedMassRn}{\ensuremath{0.637 \pm 0.094}}
\newcommand{\RetainedMassEb}{\ensuremath{0.659 \pm 0.009}}
\newcommand{\RetainedMassMn}{\ensuremath{0.566 \pm 0.048}}

% --- efficiency ----------------------------------------------------------
\newcommand{\ParamsRn}{23.6}
\newcommand{\LatencyRn}{\ensuremath{8.70 \pm 0.29}}
\newcommand{\ParamsEb}{4.0}
\newcommand{\LatencyEb}{\ensuremath{9.50 \pm 0.32}}
\newcommand{\ParamsMn}{1.5}
\newcommand{\LatencyMn}{\ensuremath{6.35 \pm 0.25}}
\newcommand{\ParamRatio}{15}

% --- significance --------------------------------------------------------
\newcommand{\SigSeed}{42}
\newcommand{\NBootstrap}{10\,000}

% --- significance: CIs PvIn ----------------------------------------------
\newcommand{\CiAccPvInRn}{\ensuremath{[0.9908,\, 0.9940]}}
\newcommand{\CiFPvInRn}{\ensuremath{[0.9870,\, 0.9922]}}
\newcommand{\CiAccPvInEb}{\ensuremath{[0.9956,\, 0.9978]}}
\newcommand{\CiFPvInEb}{\ensuremath{[0.9938,\, 0.9969]}}
\newcommand{\CiAccPvInMn}{\ensuremath{[0.9935,\, 0.9962]}}
\newcommand{\CiFPvInMn}{\ensuremath{[0.9901,\, 0.9948]}}

% --- significance: McNemar PvIn ------------------------------------------
\newcommand{\PMcPvInRnEb}{\ensuremath{<0.0001}}
\newcommand{\PMcHolmPvInRnEb}{\ensuremath{<0.0001}}
\newcommand{\NDiscPvInRnEb}{82}
\newcommand{\PMcPvInRnMn}{\ensuremath{0.0095}}
\newcommand{\PMcHolmPvInRnMn}{\ensuremath{0.0363}}
\newcommand{\NDiscPvInRnMn}{94}
\newcommand{\PMcPvInEbMn}{\ensuremath{0.0091}}
\newcommand{\PMcHolmPvInEbMn}{\ensuremath{0.0363}}
\newcommand{\NDiscPvInEbMn}{54}

% --- significance: CIs PdcIn ---------------------------------------------
\newcommand{\CiAccPdcInRn}{\ensuremath{[0.6311,\, 0.7511]}}
\newcommand{\CiFPdcInRn}{\ensuremath{[0.6526,\, 0.7721]}}
\newcommand{\CiAccPdcInEb}{\ensuremath{[0.6178,\, 0.7378]}}
\newcommand{\CiFPdcInEb}{\ensuremath{[0.6457,\, 0.7598]}}
\newcommand{\CiAccPdcInMn}{\ensuremath{[0.4889,\, 0.6222]}}
\newcommand{\CiFPdcInMn}{\ensuremath{[0.5352,\, 0.6675]}}

% --- significance: McNemar PdcIn -----------------------------------------
\newcommand{\PMcPdcInRnEb}{\ensuremath{0.7428}}
\newcommand{\PMcHolmPdcInRnEb}{\ensuremath{1.0000}}
\newcommand{\NDiscPdcInRnEb}{37}
\newcommand{\PMcPdcInRnMn}{\ensuremath{0.0002}}
\newcommand{\PMcHolmPdcInRnMn}{\ensuremath{0.0012}}
\newcommand{\NDiscPdcInRnMn}{65}
\newcommand{\PMcPdcInEbMn}{\ensuremath{0.0008}}
\newcommand{\PMcHolmPdcInEbMn}{\ensuremath{0.0045}}
\newcommand{\NDiscPdcInEbMn}{66}

% --- significance: CIs Xd ------------------------------------------------
\newcommand{\CiAccXdRn}{\ensuremath{[0.2584,\, 0.2978]}}
\newcommand{\CiFXdRn}{\ensuremath{[0.2253,\, 0.2595]}}
\newcommand{\CiAccXdEb}{\ensuremath{[0.2553,\, 0.2942]}}
\newcommand{\CiFXdEb}{\ensuremath{[0.2203,\, 0.2538]}}
\newcommand{\CiAccXdMn}{\ensuremath{[0.2230,\, 0.2609]}}
\newcommand{\CiFXdMn}{\ensuremath{[0.1831,\, 0.2158]}}

% --- significance: McNemar Xd --------------------------------------------
\newcommand{\PMcXdRnEb}{\ensuremath{0.7488}}
\newcommand{\PMcHolmXdRnEb}{\ensuremath{1.0000}}
\newcommand{\NDiscXdRnEb}{351}
\newcommand{\PMcXdRnMn}{\ensuremath{0.0002}}
\newcommand{\PMcHolmXdRnMn}{\ensuremath{0.0013}}
\newcommand{\NDiscXdRnMn}{344}
\newcommand{\PMcXdEbMn}{\ensuremath{0.0008}}
\newcommand{\PMcHolmXdEbMn}{\ensuremath{0.0045}}
\newcommand{\NDiscXdEbMn}{347}
```

---

## 3. Every table as markdown

### table1 — dataset statistics

| Dataset | Images | Train | Test | Classes |
|---|---|---|---|---|
| PlantVillage | 54305 | 43596 | 10709 | 38 |
| PlantDoc Core | 2561 | 2336 | 225 | 28 |

### table1b — dataset provenance and leakage control

| Quantity | Value |
|---|---|
| PlantDoc acquired (source) | 2578 |
| PlantDoc previous effective | 2564 |
| PlantDoc Core | 2561 |
| PlantDoc non-reviewed unchanged | 2554 |
| PlantDoc retained reviewed | 7 |
| PlantDoc excluded reviewed | 17 |
| Cross-dataset exact duplicates (acquired) | 0 |
| Cross-dataset near duplicates (acquired) | 16 |
| Cross-dataset exact duplicates (Core) | 0 |
| Cross-dataset near duplicates (Core) | 16 |
| Unresolved leakage pairs | 0 |
| Shared cross-domain classes | 21 |
| Cross-domain evaluation images | 1951 |

### table2 — in-domain performance (full)

| Model | Dataset | Seeds | N | Accuracy | Macro-F1 | Weighted-F1 | Balanced Acc. | Macro Prec. | Macro Rec. |
|---|---|---|---|---|---|---|---|---|---|
| ResNet-50 | PlantVillage | 3 | 10709 | 0.9945 ± 0.0021 | 0.9927 ± 0.0029 | 0.9945 ± 0.0021 | 0.9923 ± 0.0029 | 0.9934 ± 0.0028 | 0.9923 ± 0.0029 |
| EfficientNet-B0 | PlantVillage | 3 | 10709 | 0.9964 ± 0.0005 | 0.9950 ± 0.0006 | 0.9964 ± 0.0005 | 0.9945 ± 0.0008 | 0.9956 ± 0.0004 | 0.9945 ± 0.0008 |
| MobileNetV3-Small | PlantVillage | 3 | 10709 | 0.9948 ± 0.0004 | 0.9927 ± 0.0004 | 0.9948 ± 0.0004 | 0.9916 ± 0.0003 | 0.9940 ± 0.0006 | 0.9916 ± 0.0003 |
| ResNet-50 | PlantDoc Core | 3 | 225 | 0.6637 ± 0.0403 | 0.6823 ± 0.0386 | 0.6946 ± 0.0406 | 0.6551 ± 0.0393 | 0.7539 ± 0.0317 | 0.6551 ± 0.0393 |
| EfficientNet-B0 | PlantDoc Core | 3 | 225 | 0.6652 ± 0.0128 | 0.6768 ± 0.0139 | 0.6920 ± 0.0162 | 0.6569 ± 0.0087 | 0.7430 ± 0.0082 | 0.6569 ± 0.0087 |
| MobileNetV3-Small | PlantDoc Core | 3 | 225 | 0.5600 ± 0.0044 | 0.5876 ± 0.0061 | 0.5936 ± 0.0044 | 0.5640 ± 0.0030 | 0.6564 ± 0.0136 | 0.5640 ± 0.0030 |

### table2_compact — in-domain performance (paper)

_(file not present)_

### table3 — cross-domain performance (full)

| Model | Dataset | Seeds | N | Accuracy | Macro-F1 | Weighted-F1 | Balanced Acc. | Macro Prec. | Macro Rec. | Shared classes | Retained prob. mass |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ResNet-50 | PlantVillage → PlantDoc Core | 3 | 1951 | 0.2583 ± 0.0206 | 0.2291 ± 0.0107 | 0.2512 ± 0.0138 | 0.2389 ± 0.0188 | 0.3629 ± 0.0197 | 0.2389 ± 0.0188 | 21 | 0.6367 ± 0.0945 |
| EfficientNet-B0 | PlantVillage → PlantDoc Core | 3 | 1951 | 0.2653 ± 0.0102 | 0.2300 ± 0.0065 | 0.2528 ± 0.0078 | 0.2475 ± 0.0110 | 0.3455 ± 0.0257 | 0.2475 ± 0.0110 | 21 | 0.6595 ± 0.0086 |
| MobileNetV3-Small | PlantVillage → PlantDoc Core | 3 | 1951 | 0.2238 ± 0.0162 | 0.1869 ± 0.0109 | 0.2013 ± 0.0160 | 0.2141 ± 0.0135 | 0.3090 ± 0.0248 | 0.2141 ± 0.0135 | 21 | 0.5662 ± 0.0477 |

### table3_compact — cross-domain performance (paper)

_(file not present)_

### table4 — efficiency

| Model | Dataset | Seeds | Params (M) | Epochs | Train time (min) | s / epoch | Latency b1 (ms) | Throughput (img/s) | Peak mem (MB) |
|---|---|---|---|---|---|---|---|---|---|
| ResNet-50 | PlantVillage | 3 | 23.59 | 12.0 ± 2.6 | 143.9 ± 35.1 | 718.7 ± 53.1 | 8.82 ± 0.36 | 216.5 ± 5.7 | 9472.5 ± 18.5 |
| EfficientNet-B0 | PlantVillage | 3 | 4.06 | 13.0 ± 1.7 | 127.8 ± 16.1 | 590.4 ± 21.2 | 9.26 ± 0.22 | 271.7 ± 5.7 | 9241.6 ± 6.9 |
| MobileNetV3-Small | PlantVillage | 3 | 1.56 | 13.0 ± 3.5 | 30.4 ± 7.1 | 141.2 ± 7.1 | 6.42 ± 0.31 | 1286.8 ± 22.8 | 2150.0 ± 9.2 |
| ResNet-50 | PlantDoc Core | 3 | 23.57 | 10.7 ± 2.1 | 11.3 ± 2.2 | 63.9 ± 7.6 | 8.58 ± 0.21 | 209.9 ± 5.7 | 11849.1 ± 591.2 |
| EfficientNet-B0 | PlantDoc Core | 3 | 4.04 | 9.3 ± 0.6 | 10.6 ± 1.9 | 67.8 ± 11.4 | 9.75 ± 0.17 | 192.6 ± 131.2 | 11829.6 ± 339.5 |
| MobileNetV3-Small | PlantDoc Core | 3 | 1.55 | 13.0 ± 2.0 | 2.7 ± 0.4 | 12.6 ± 0.3 | 6.28 ± 0.23 | 1268.4 ± 5.1 | 2150.7 ± 5.3 |

### table5 — domain-shift degradation (full)

| Model | Seeds | Accuracy (in-domain) | Accuracy (cross-domain) | Accuracy abs. drop | Accuracy rel. drop % | Macro-F1 (in-domain) | Macro-F1 (cross-domain) | Macro-F1 abs. drop | Macro-F1 rel. drop % |
|---|---|---|---|---|---|---|---|---|---|
| ResNet-50 | 3 | 0.9945 ± 0.0021 | 0.2583 ± 0.0206 | 0.7361 ± 0.0213 | 74.02 ± 2.09 | 0.9927 ± 0.0029 | 0.2291 ± 0.0107 | 0.7636 ± 0.0131 | 76.92 ± 1.13 |
| EfficientNet-B0 | 3 | 0.9964 ± 0.0005 | 0.2653 ± 0.0102 | 0.7310 ± 0.0097 | 73.37 ± 1.01 | 0.9950 ± 0.0006 | 0.2300 ± 0.0065 | 0.7650 ± 0.0064 | 76.89 ± 0.65 |
| MobileNetV3-Small | 3 | 0.9948 ± 0.0004 | 0.2238 ± 0.0162 | 0.7710 ± 0.0162 | 77.50 ± 1.63 | 0.9927 ± 0.0004 | 0.1869 ± 0.0109 | 0.8058 ± 0.0111 | 81.17 ± 1.10 |

### table5_compact — domain-shift degradation (paper)

_(file not present)_

### table6 — calibration and selective prediction (full)

| Model | Dataset | Setting | Seeds | NLL | Brier | ECE | MCE | AURC | T |
|---|---|---|---|---|---|---|---|---|---|
| ResNet-50 | PlantVillage | in-domain | 3 | 0.1218 ± 0.0138 | 0.0195 ± 0.0042 | 0.0987 ± 0.0113 | 0.3504 ± 0.0611 | 0.0007 ± 0.0002 | 1.0000 ± 0.0000 |
| ResNet-50 | PlantVillage | in-domain (T-scaled) | 3 | 0.0283 ± 0.0041 | 0.0092 ± 0.0026 | 0.0092 ± 0.0011 | 0.3061 ± 0.0897 | 0.0006 ± 0.0002 | 0.7028 ± 0.0076 |
| ResNet-50 | PlantVillage | cross-domain | 3 | 2.9441 ± 0.1055 | 0.9938 ± 0.0342 | 0.2829 ± 0.0459 | 0.5042 ± 0.0136 | 0.6428 ± 0.0282 | 1.0000 ± 0.0000 |
| ResNet-50 | PlantVillage | cross-domain (T-scaled) | 3 | 3.5879 ± 0.2283 | 1.1068 ± 0.0529 | 0.4178 ± 0.0533 | 0.6400 ± 0.0236 | 0.6427 ± 0.0282 | 0.7028 ± 0.0076 |
| EfficientNet-B0 | PlantVillage | in-domain | 3 | 0.1195 ± 0.0075 | 0.0165 ± 0.0019 | 0.1015 ± 0.0069 | 0.5075 ± 0.1154 | 0.0009 ± 0.0003 | 1.0000 ± 0.0000 |
| EfficientNet-B0 | PlantVillage | in-domain (T-scaled) | 3 | 0.0230 ± 0.0017 | 0.0059 ± 0.0006 | 0.0095 ± 0.0013 | 0.4969 ± 0.1793 | 0.0007 ± 0.0003 | 0.7006 ± 0.0040 |
| EfficientNet-B0 | PlantVillage | cross-domain | 3 | 2.8680 ± 0.0086 | 0.9588 ± 0.0242 | 0.2561 ± 0.0186 | 0.4783 ± 0.0577 | 0.6156 ± 0.0280 | 1.0000 ± 0.0000 |
| EfficientNet-B0 | PlantVillage | cross-domain (T-scaled) | 3 | 3.4624 ± 0.0278 | 1.0665 ± 0.0314 | 0.3973 ± 0.0192 | 0.5966 ± 0.0337 | 0.6152 ± 0.0295 | 0.7006 ± 0.0040 |
| MobileNetV3-Small | PlantVillage | in-domain | 3 | 0.1213 ± 0.0032 | 0.0199 ± 0.0015 | 0.0988 ± 0.0025 | 0.6900 ± 0.1577 | 0.0003 ± 0.0000 | 1.0000 ± 0.0000 |
| MobileNetV3-Small | PlantVillage | in-domain (T-scaled) | 3 | 0.0271 ± 0.0012 | 0.0086 ± 0.0006 | 0.0091 ± 0.0003 | 0.4771 ± 0.2112 | 0.0002 ± 0.0000 | 0.6976 ± 0.0046 |
| MobileNetV3-Small | PlantVillage | cross-domain | 3 | 2.7900 ± 0.0281 | 0.9296 ± 0.0068 | 0.1517 ± 0.0139 | 0.4799 ± 0.0438 | 0.6772 ± 0.0145 | 1.0000 ± 0.0000 |
| MobileNetV3-Small | PlantVillage | cross-domain (T-scaled) | 3 | 3.1303 ± 0.0525 | 1.0172 ± 0.0107 | 0.2938 ± 0.0128 | 0.5680 ± 0.0415 | 0.6769 ± 0.0145 | 0.6976 ± 0.0046 |
| ResNet-50 | PlantDoc Core | in-domain | 3 | 1.2067 ± 0.0168 | 0.4769 ± 0.0172 | 0.1157 ± 0.0079 | 0.2413 ± 0.0669 | 0.1642 ± 0.0185 | 1.0000 ± 0.0000 |
| ResNet-50 | PlantDoc Core | in-domain (T-scaled) | 3 | 1.1890 ± 0.0150 | 0.4699 ± 0.0187 | 0.0831 ± 0.0192 | 0.2254 ± 0.0373 | 0.1649 ± 0.0181 | 0.8780 ± 0.0447 |
| EfficientNet-B0 | PlantDoc Core | in-domain | 3 | 1.1907 ± 0.0022 | 0.4858 ± 0.0065 | 0.1318 ± 0.0204 | 0.4597 ± 0.3660 | 0.1642 ± 0.0147 | 1.0000 ± 0.0000 |
| EfficientNet-B0 | PlantDoc Core | in-domain (T-scaled) | 3 | 1.1332 ± 0.0075 | 0.4671 ± 0.0127 | 0.0659 ± 0.0183 | 0.2648 ± 0.0797 | 0.1632 ± 0.0129 | 0.7796 ± 0.0448 |
| MobileNetV3-Small | PlantDoc Core | in-domain | 3 | 1.5064 ± 0.0506 | 0.5952 ± 0.0185 | 0.1456 ± 0.0100 | 0.3238 ± 0.0464 | 0.2350 ± 0.0134 | 1.0000 ± 0.0000 |
| MobileNetV3-Small | PlantDoc Core | in-domain (T-scaled) | 3 | 1.4666 ± 0.0592 | 0.5822 ± 0.0215 | 0.0868 ± 0.0318 | 0.2306 ± 0.0163 | 0.2365 ± 0.0154 | 0.8317 ± 0.0512 |

### table6_compact — calibration (paper)

_(file not present)_

### table7 — backbone ranking stability across seeds

| Setting | Seed | Ranking (macro-F1; best first) | ResNet-50 macro-F1 | EfficientNet-B0 macro-F1 | MobileNetV3-Small macro-F1 |
|---|---|---|---|---|---|
| PlantVillage in-domain | 42 | EfficientNet-B0 > MobileNetV3-Small > ResNet-50 | 0.9899 | 0.9956 | 0.9927 |
| PlantVillage in-domain | 1337 | EfficientNet-B0 > MobileNetV3-Small > ResNet-50 | 0.9925 | 0.9944 | 0.9931 |
| PlantVillage in-domain | 2026 | ResNet-50 > EfficientNet-B0 > MobileNetV3-Small | 0.9957 | 0.9951 | 0.9923 |
| PlantVillage in-domain | all | UNSTABLE: 2/3 seeds give EfficientNet-B0 > MobileNetV3-Small > ResNet-50 | 0.9927 | 0.995 | 0.9927 |
| PlantVillage → PlantDoc Core | 42 | ResNet-50 > EfficientNet-B0 > MobileNetV3-Small | 0.2414 | 0.2359 | 0.1982 |
| PlantVillage → PlantDoc Core | 1337 | EfficientNet-B0 > ResNet-50 > MobileNetV3-Small | 0.2218 | 0.2312 | 0.1764 |
| PlantVillage → PlantDoc Core | 2026 | ResNet-50 > EfficientNet-B0 > MobileNetV3-Small | 0.2242 | 0.223 | 0.1862 |
| PlantVillage → PlantDoc Core | all | UNSTABLE: 2/3 seeds give ResNet-50 > EfficientNet-B0 > MobileNetV3-Small | 0.2291 | 0.23 | 0.1869 |
| PlantDoc Core in-domain | 42 | ResNet-50 > EfficientNet-B0 > MobileNetV3-Small | 0.6994 | 0.6927 | 0.5841 |
| PlantDoc Core in-domain | 1337 | ResNet-50 > EfficientNet-B0 > MobileNetV3-Small | 0.7094 | 0.6663 | 0.5946 |
| PlantDoc Core in-domain | 2026 | EfficientNet-B0 > ResNet-50 > MobileNetV3-Small | 0.6381 | 0.6716 | 0.584 |
| PlantDoc Core in-domain | all | UNSTABLE: 2/3 seeds give ResNet-50 > EfficientNet-B0 > MobileNetV3-Small | 0.6823 | 0.6768 | 0.5876 |

### table7b — pairwise ranking margins vs seed noise

| Setting | Comparison | Seeds | Mean margin | Pooled seed SD | \|Margin\| / seed SD | Sign consistent |
|---|---|---|---|---|---|---|
| PlantVillage in-domain | ResNet-50 - EfficientNet-B0 | 3 | -0.0023 ± 0.0032 | 0.0021 | 1.11 | 2/3 |
| PlantVillage in-domain | ResNet-50 - MobileNetV3-Small | 3 | 0.0000 ± 0.0031 | 0.0021 | 0.02 | 2/3 |
| PlantVillage in-domain | EfficientNet-B0 - MobileNetV3-Small | 3 | 0.0023 ± 0.0008 | 0.0005 | 4.73 | 3/3 |
| PlantVillage → PlantDoc Core | ResNet-50 - EfficientNet-B0 | 3 | -0.0009 ± 0.0077 | 0.0089 | 0.10 | 2/3 |
| PlantVillage → PlantDoc Core | ResNet-50 - MobileNetV3-Small | 3 | 0.0422 ± 0.0038 | 0.0108 | 3.90 | 3/3 |
| PlantVillage → PlantDoc Core | EfficientNet-B0 - MobileNetV3-Small | 3 | 0.0431 ± 0.0102 | 0.0090 | 4.78 | 3/3 |
| PlantDoc Core in-domain | ResNet-50 - EfficientNet-B0 | 3 | 0.0054 ± 0.0383 | 0.0290 | 0.19 | 2/3 |
| PlantDoc Core in-domain | ResNet-50 - MobileNetV3-Small | 3 | 0.0947 ± 0.0352 | 0.0276 | 3.43 | 3/3 |
| PlantDoc Core in-domain | EfficientNet-B0 - MobileNetV3-Small | 3 | 0.0893 ± 0.0185 | 0.0108 | 8.30 | 3/3 |

### table8 — BCa bootstrap confidence intervals

| Setting | Model | N | Accuracy | Accuracy 95% CI | Macro-F1 | Macro-F1 95% CI |
|---|---|---|---|---|---|---|
| PlantVillage in-domain | ResNet-50 | 10709 | 0.9925 | [0.9908, 0.9940] | 0.9899 | [0.9870, 0.9922] |
| PlantVillage in-domain | EfficientNet-B0 | 10709 | 0.9968 | [0.9956, 0.9978] | 0.9956 | [0.9938, 0.9969] |
| PlantVillage in-domain | MobileNetV3-Small | 10709 | 0.9950 | [0.9935, 0.9962] | 0.9927 | [0.9901, 0.9948] |
| PlantDoc Core in-domain | ResNet-50 | 225 | 0.6933 | [0.6311, 0.7511] | 0.6994 | [0.6526, 0.7721] |
| PlantDoc Core in-domain | EfficientNet-B0 | 225 | 0.6800 | [0.6178, 0.7378] | 0.6927 | [0.6457, 0.7598] |
| PlantDoc Core in-domain | MobileNetV3-Small | 225 | 0.5556 | [0.4889, 0.6222] | 0.5841 | [0.5352, 0.6675] |
| PlantVillage -> PlantDoc Core | ResNet-50 | 1951 | 0.2778 | [0.2584, 0.2978] | 0.2414 | [0.2253, 0.2595] |
| PlantVillage -> PlantDoc Core | EfficientNet-B0 | 1951 | 0.2742 | [0.2553, 0.2942] | 0.2359 | [0.2203, 0.2538] |
| PlantVillage -> PlantDoc Core | MobileNetV3-Small | 1951 | 0.2419 | [0.2230, 0.2609] | 0.1982 | [0.1831, 0.2158] |

### table8b — pairwise McNemar exact tests

| Setting | Comparison | Acc. A | Acc. B | Diff. | A only | B only | Discordant | p (exact) | p (Holm) |
|---|---|---|---|---|---|---|---|---|---|
| PlantVillage in-domain | ResNet-50 vs EfficientNet-B0 | 0.9925 | 0.9968 | -0.0043 | 18 | 64 | 82 | <0.0001 | <0.0001 |
| PlantVillage in-domain | ResNet-50 vs MobileNetV3-Small | 0.9925 | 0.9950 | -0.0024 | 34 | 60 | 94 | 0.0095 | 0.0363 |
| PlantVillage in-domain | EfficientNet-B0 vs MobileNetV3-Small | 0.9968 | 0.9950 | +0.0019 | 37 | 17 | 54 | 0.0091 | 0.0363 |
| PlantDoc Core in-domain | ResNet-50 vs EfficientNet-B0 | 0.6933 | 0.6800 | +0.0133 | 20 | 17 | 37 | 0.7428 | 1.0000 |
| PlantDoc Core in-domain | ResNet-50 vs MobileNetV3-Small | 0.6933 | 0.5556 | +0.1378 | 48 | 17 | 65 | 0.0002 | 0.0012 |
| PlantDoc Core in-domain | EfficientNet-B0 vs MobileNetV3-Small | 0.6800 | 0.5556 | +0.1244 | 47 | 19 | 66 | 0.0008 | 0.0045 |
| PlantVillage -> PlantDoc Core | ResNet-50 vs EfficientNet-B0 | 0.2778 | 0.2742 | +0.0036 | 179 | 172 | 351 | 0.7488 | 1.0000 |
| PlantVillage -> PlantDoc Core | ResNet-50 vs MobileNetV3-Small | 0.2778 | 0.2419 | +0.0359 | 207 | 137 | 344 | 0.0002 | 0.0013 |
| PlantVillage -> PlantDoc Core | EfficientNet-B0 vs MobileNetV3-Small | 0.2742 | 0.2419 | +0.0323 | 205 | 142 | 347 | 0.0008 | 0.0045 |

### table9 — significance across seeds

| Setting | Comparison | Seeds | Significant (Holm) | Sign consistent | Mean acc. diff. |
|---|---|---|---|---|---|
| PlantVillage in-domain | ResNet-50 vs EfficientNet-B0 | 3 | 1/3 | no | -0.0019 |
| PlantVillage in-domain | ResNet-50 vs MobileNetV3-Small | 3 | 2/3 | no | -0.0003 |
| PlantVillage in-domain | EfficientNet-B0 vs MobileNetV3-Small | 3 | 2/3 | yes | +0.0016 |
| PlantDoc Core in-domain | ResNet-50 vs EfficientNet-B0 | 3 | 0/3 | no | -0.0015 |
| PlantDoc Core in-domain | ResNet-50 vs MobileNetV3-Small | 3 | 2/3 | yes | +0.1037 |
| PlantDoc Core in-domain | EfficientNet-B0 vs MobileNetV3-Small | 3 | 3/3 | yes | +0.1052 |
| PlantVillage -> PlantDoc Core | ResNet-50 vs EfficientNet-B0 | 3 | 0/3 | no | -0.0070 |
| PlantVillage -> PlantDoc Core | ResNet-50 vs MobileNetV3-Small | 3 | 3/3 | yes | +0.0345 |
| PlantVillage -> PlantDoc Core | EfficientNet-B0 vs MobileNetV3-Small | 3 | 3/3 | yes | +0.0415 |

---

## 4. Cross-seed significance summary

Source: `experiments/ica26/metrics/significance_all_seeds.json`

Seeds: 42, 1337, 2026. Each seed analysed independently; Holm adjustment is applied within a seed across that seed's nine pairwise tests. p-values are not pooled across seeds.

| Setting | Comparison | p Holm s42 | p Holm s1337 | p Holm s2026 | acc diff s42 | acc diff s1337 | acc diff s2026 | Mean acc diff | Sign consistent | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| PlantVillage in-domain | ResNet-50 vs EfficientNet-B0 | 0.0000 | 0.1848 | 0.9591 | -0.0043 | -0.0018 | +0.0004 | -0.0019 | no | significant in 1 of 3 seeds |
| PlantVillage in-domain | ResNet-50 vs MobileNetV3-Small | 0.0363 | 0.9784 | 0.0075 | -0.0024 | -0.0009 | +0.0024 | -0.0003 | no | significant in 2 of 3 seeds |
| PlantVillage in-domain | EfficientNet-B0 vs MobileNetV3-Small | 0.0363 | 0.9784 | 0.0321 | +0.0019 | +0.0008 | +0.0021 | +0.0016 | yes | significant in 2 of 3 seeds |
| PlantDoc Core in-domain | ResNet-50 vs EfficientNet-B0 | 1.0000 | 0.9784 | 0.7289 | +0.0133 | +0.0222 | -0.0400 | -0.0015 | no | significant in no seed |
| PlantDoc Core in-domain | ResNet-50 vs MobileNetV3-Small | 0.0012 | 0.0011 | 0.5054 | +0.1378 | +0.1200 | +0.0533 | +0.1037 | yes | significant in 2 of 3 seeds |
| PlantDoc Core in-domain | EfficientNet-B0 vs MobileNetV3-Small | 0.0045 | 0.0223 | 0.0323 | +0.1244 | +0.0978 | +0.0933 | +0.1052 | yes | significant in all seeds |
| PlantVillage -> PlantDoc Core | ResNet-50 vs EfficientNet-B0 | 1.0000 | 0.2731 | 0.9591 | +0.0036 | -0.0174 | -0.0072 | -0.0070 | no | significant in no seed |
| PlantVillage -> PlantDoc Core | ResNet-50 vs MobileNetV3-Small | 0.0013 | 0.0382 | 0.0003 | +0.0359 | +0.0261 | +0.0415 | +0.0345 | yes | significant in all seeds |
| PlantVillage -> PlantDoc Core | EfficientNet-B0 vs MobileNetV3-Small | 0.0045 | 0.0001 | 0.0000 | +0.0323 | +0.0436 | +0.0487 | +0.0415 | yes | significant in all seeds |

### Discordant item counts per seed

Counts the McNemar test is computed from.

| Setting | Comparison | discordant s42 | discordant s1337 | discordant s2026 |
|---|---|---|---|---|
| PlantVillage in-domain | ResNet-50 vs EfficientNet-B0 | 82 | 75 | 32 |
| PlantVillage in-domain | ResNet-50 vs MobileNetV3-Small | 94 | 84 | 60 |
| PlantVillage in-domain | EfficientNet-B0 vs MobileNetV3-Small | 54 | 69 | 58 |
| PlantDoc Core in-domain | ResNet-50 vs EfficientNet-B0 | 37 | 39 | 47 |
| PlantDoc Core in-domain | ResNet-50 vs MobileNetV3-Small | 65 | 49 | 52 |
| PlantDoc Core in-domain | EfficientNet-B0 vs MobileNetV3-Small | 66 | 52 | 55 |
| PlantVillage -> PlantDoc Core | ResNet-50 vs EfficientNet-B0 | 351 | 328 | 338 |
| PlantVillage -> PlantDoc Core | ResNet-50 vs MobileNetV3-Small | 344 | 337 | 379 |
| PlantVillage -> PlantDoc Core | EfficientNet-B0 vs MobileNetV3-Small | 347 | 349 | 363 |

---

## 5. Figure inventory

48 PDF files. Dimensions are the PDF MediaBox converted at 72 pt = 1 inch; figures are authored at the LNCS text width of 4.8 in and `bbox_inches="tight"` trims to content. All are vector except the confusion matrices, which embed a raster image at 300 dpi.

### 5a. Paper-facing summary figures

| Path from repo root | Plots | Size (in) | Bytes |
|---|---|---|---|
| `experiments/ica26/figures/fig_risk_coverage.pdf` | Confidence-abstention (risk-coverage) curves, seed-averaged on a common coverage grid with a +/-1 SD band; one panel per evaluation setting. | 4.78 x 1.93 | 37,787 |
| `experiments/ica26/figures/fig_seed_spread.pdf` | Backbone macro-F1: mean with seed-SD error bar plus each individual seed plotted beside it; one panel per evaluation setting. | 4.77 x 1.93 | 23,317 |
| `experiments/ica26/figures/fig_training_curves.pdf` | Training loss and validation macro-F1, 2x2 grid faceted by corpus (PlantVillage top, PlantDoc Core bottom); colour = backbone, dash = seed. | 4.75 x 3.93 | 37,403 |

#### \includegraphics lines (file placed in an Overleaf `figures/` folder)

`fig_risk_coverage.pdf`

```latex
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/fig_risk_coverage.pdf}
\caption{}
\label{fig:risk-coverage}
\end{figure}
```

`fig_seed_spread.pdf`

```latex
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/fig_seed_spread.pdf}
\caption{}
\label{fig:seed-spread}
\end{figure}
```

`fig_training_curves.pdf`

```latex
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/fig_training_curves.pdf}
\caption{}
\label{fig:training-curves}
\end{figure}
```

### 5b. Per-run diagnostic figures

| Path from repo root | Plots | Size (in) | Bytes |
|---|---|---|---|
| `experiments/ica26/figures/fig_confusion_pdc_efficientnet_b0_s1337_in_domain_test.pdf` | Row-normalised confusion matrix, run `pdc_efficientnet_b0_s1337`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.86 x 4.48 | 27,565 |
| `experiments/ica26/figures/fig_confusion_pdc_efficientnet_b0_s2026_in_domain_test.pdf` | Row-normalised confusion matrix, run `pdc_efficientnet_b0_s2026`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.86 x 4.48 | 27,549 |
| `experiments/ica26/figures/fig_confusion_pdc_efficientnet_b0_s42_in_domain_test.pdf` | Row-normalised confusion matrix, run `pdc_efficientnet_b0_s42`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.86 x 4.48 | 27,405 |
| `experiments/ica26/figures/fig_confusion_pdc_mobilenet_v3_small_s1337_in_domain_test.pdf` | Row-normalised confusion matrix, run `pdc_mobilenet_v3_small_s1337`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.86 x 4.48 | 24,439 |
| `experiments/ica26/figures/fig_confusion_pdc_mobilenet_v3_small_s2026_in_domain_test.pdf` | Row-normalised confusion matrix, run `pdc_mobilenet_v3_small_s2026`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.86 x 4.48 | 24,148 |
| `experiments/ica26/figures/fig_confusion_pdc_mobilenet_v3_small_s42_in_domain_test.pdf` | Row-normalised confusion matrix, run `pdc_mobilenet_v3_small_s42`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.86 x 4.48 | 24,491 |
| `experiments/ica26/figures/fig_confusion_pdc_resnet50_s1337_in_domain_test.pdf` | Row-normalised confusion matrix, run `pdc_resnet50_s1337`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.86 x 4.48 | 24,475 |
| `experiments/ica26/figures/fig_confusion_pdc_resnet50_s2026_in_domain_test.pdf` | Row-normalised confusion matrix, run `pdc_resnet50_s2026`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.86 x 4.48 | 23,943 |
| `experiments/ica26/figures/fig_confusion_pdc_resnet50_s42_in_domain_test.pdf` | Row-normalised confusion matrix, run `pdc_resnet50_s42`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.86 x 4.48 | 24,200 |
| `experiments/ica26/figures/fig_confusion_pv_efficientnet_b0_s1337_cross_domain_plantdoc_core.pdf` | Row-normalised confusion matrix, run `pv_efficientnet_b0_s1337`, evaluation `cross_domain_plantdoc_core`. Embedded raster at 300 dpi. | 4.76 x 4.38 | 27,496 |
| `experiments/ica26/figures/fig_confusion_pv_efficientnet_b0_s1337_in_domain_test.pdf` | Row-normalised confusion matrix, run `pv_efficientnet_b0_s1337`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.89 x 4.54 | 28,381 |
| `experiments/ica26/figures/fig_confusion_pv_efficientnet_b0_s2026_cross_domain_plantdoc_core.pdf` | Row-normalised confusion matrix, run `pv_efficientnet_b0_s2026`, evaluation `cross_domain_plantdoc_core`. Embedded raster at 300 dpi. | 4.76 x 4.38 | 26,324 |
| `experiments/ica26/figures/fig_confusion_pv_efficientnet_b0_s2026_in_domain_test.pdf` | Row-normalised confusion matrix, run `pv_efficientnet_b0_s2026`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.89 x 4.54 | 28,189 |
| `experiments/ica26/figures/fig_confusion_pv_efficientnet_b0_s42_cross_domain_plantdoc_core.pdf` | Row-normalised confusion matrix, run `pv_efficientnet_b0_s42`, evaluation `cross_domain_plantdoc_core`. Embedded raster at 300 dpi. | 4.76 x 4.38 | 26,398 |
| `experiments/ica26/figures/fig_confusion_pv_efficientnet_b0_s42_in_domain_test.pdf` | Row-normalised confusion matrix, run `pv_efficientnet_b0_s42`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.89 x 4.54 | 28,162 |
| `experiments/ica26/figures/fig_confusion_pv_mobilenet_v3_small_s1337_cross_domain_plantdoc_core.pdf` | Row-normalised confusion matrix, run `pv_mobilenet_v3_small_s1337`, evaluation `cross_domain_plantdoc_core`. Embedded raster at 300 dpi. | 4.76 x 4.38 | 23,886 |
| `experiments/ica26/figures/fig_confusion_pv_mobilenet_v3_small_s1337_in_domain_test.pdf` | Row-normalised confusion matrix, run `pv_mobilenet_v3_small_s1337`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.89 x 4.54 | 24,785 |
| `experiments/ica26/figures/fig_confusion_pv_mobilenet_v3_small_s2026_cross_domain_plantdoc_core.pdf` | Row-normalised confusion matrix, run `pv_mobilenet_v3_small_s2026`, evaluation `cross_domain_plantdoc_core`. Embedded raster at 300 dpi. | 4.76 x 4.38 | 23,112 |
| `experiments/ica26/figures/fig_confusion_pv_mobilenet_v3_small_s2026_in_domain_test.pdf` | Row-normalised confusion matrix, run `pv_mobilenet_v3_small_s2026`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.89 x 4.54 | 25,915 |
| `experiments/ica26/figures/fig_confusion_pv_mobilenet_v3_small_s42_cross_domain_plantdoc_core.pdf` | Row-normalised confusion matrix, run `pv_mobilenet_v3_small_s42`, evaluation `cross_domain_plantdoc_core`. Embedded raster at 300 dpi. | 4.76 x 4.38 | 23,532 |
| `experiments/ica26/figures/fig_confusion_pv_mobilenet_v3_small_s42_in_domain_test.pdf` | Row-normalised confusion matrix, run `pv_mobilenet_v3_small_s42`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.89 x 4.54 | 25,972 |
| `experiments/ica26/figures/fig_confusion_pv_resnet50_s1337_cross_domain_plantdoc_core.pdf` | Row-normalised confusion matrix, run `pv_resnet50_s1337`, evaluation `cross_domain_plantdoc_core`. Embedded raster at 300 dpi. | 4.76 x 4.38 | 23,896 |
| `experiments/ica26/figures/fig_confusion_pv_resnet50_s1337_in_domain_test.pdf` | Row-normalised confusion matrix, run `pv_resnet50_s1337`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.89 x 4.54 | 25,024 |
| `experiments/ica26/figures/fig_confusion_pv_resnet50_s2026_cross_domain_plantdoc_core.pdf` | Row-normalised confusion matrix, run `pv_resnet50_s2026`, evaluation `cross_domain_plantdoc_core`. Embedded raster at 300 dpi. | 4.76 x 4.38 | 23,027 |
| `experiments/ica26/figures/fig_confusion_pv_resnet50_s2026_in_domain_test.pdf` | Row-normalised confusion matrix, run `pv_resnet50_s2026`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.89 x 4.54 | 24,710 |
| `experiments/ica26/figures/fig_confusion_pv_resnet50_s42_cross_domain_plantdoc_core.pdf` | Row-normalised confusion matrix, run `pv_resnet50_s42`, evaluation `cross_domain_plantdoc_core`. Embedded raster at 300 dpi. | 4.76 x 4.38 | 23,235 |
| `experiments/ica26/figures/fig_confusion_pv_resnet50_s42_in_domain_test.pdf` | Row-normalised confusion matrix, run `pv_resnet50_s42`, evaluation `in_domain_test`. Embedded raster at 300 dpi. | 4.89 x 4.54 | 26,040 |
| `experiments/ica26/figures/fig_reliability_pdc_efficientnet_b0_s1337.pdf` | Reliability diagrams for run `pdc_efficientnet_b0_s1337`, one panel per evaluation block, with ECE printed in each panel title. | 4.78 x 1.54 | 15,640 |
| `experiments/ica26/figures/fig_reliability_pdc_efficientnet_b0_s2026.pdf` | Reliability diagrams for run `pdc_efficientnet_b0_s2026`, one panel per evaluation block, with ECE printed in each panel title. | 4.78 x 1.54 | 15,641 |
| `experiments/ica26/figures/fig_reliability_pdc_efficientnet_b0_s42.pdf` | Reliability diagrams for run `pdc_efficientnet_b0_s42`, one panel per evaluation block, with ECE printed in each panel title. | 4.78 x 1.54 | 15,821 |
| `experiments/ica26/figures/fig_reliability_pdc_mobilenet_v3_small_s1337.pdf` | Reliability diagrams for run `pdc_mobilenet_v3_small_s1337`, one panel per evaluation block, with ECE printed in each panel title. | 4.78 x 1.54 | 15,756 |
| `experiments/ica26/figures/fig_reliability_pdc_mobilenet_v3_small_s2026.pdf` | Reliability diagrams for run `pdc_mobilenet_v3_small_s2026`, one panel per evaluation block, with ECE printed in each panel title. | 4.78 x 1.54 | 15,765 |
| `experiments/ica26/figures/fig_reliability_pdc_mobilenet_v3_small_s42.pdf` | Reliability diagrams for run `pdc_mobilenet_v3_small_s42`, one panel per evaluation block, with ECE printed in each panel title. | 4.78 x 1.54 | 15,537 |
| `experiments/ica26/figures/fig_reliability_pdc_resnet50_s1337.pdf` | Reliability diagrams for run `pdc_resnet50_s1337`, one panel per evaluation block, with ECE printed in each panel title. | 4.78 x 1.54 | 15,848 |
| `experiments/ica26/figures/fig_reliability_pdc_resnet50_s2026.pdf` | Reliability diagrams for run `pdc_resnet50_s2026`, one panel per evaluation block, with ECE printed in each panel title. | 4.78 x 1.54 | 15,729 |
| `experiments/ica26/figures/fig_reliability_pdc_resnet50_s42.pdf` | Reliability diagrams for run `pdc_resnet50_s42`, one panel per evaluation block, with ECE printed in each panel title. | 4.78 x 1.54 | 15,542 |
| `experiments/ica26/figures/fig_reliability_pv_efficientnet_b0_s1337.pdf` | Reliability diagrams for run `pv_efficientnet_b0_s1337`, one panel per evaluation block, with ECE printed in each panel title. | 4.97 x 1.54 | 17,756 |
| `experiments/ica26/figures/fig_reliability_pv_efficientnet_b0_s2026.pdf` | Reliability diagrams for run `pv_efficientnet_b0_s2026`, one panel per evaluation block, with ECE printed in each panel title. | 4.97 x 1.54 | 17,713 |
| `experiments/ica26/figures/fig_reliability_pv_efficientnet_b0_s42.pdf` | Reliability diagrams for run `pv_efficientnet_b0_s42`, one panel per evaluation block, with ECE printed in each panel title. | 4.97 x 1.54 | 17,727 |
| `experiments/ica26/figures/fig_reliability_pv_mobilenet_v3_small_s1337.pdf` | Reliability diagrams for run `pv_mobilenet_v3_small_s1337`, one panel per evaluation block, with ECE printed in each panel title. | 4.97 x 1.54 | 17,836 |
| `experiments/ica26/figures/fig_reliability_pv_mobilenet_v3_small_s2026.pdf` | Reliability diagrams for run `pv_mobilenet_v3_small_s2026`, one panel per evaluation block, with ECE printed in each panel title. | 4.97 x 1.54 | 17,804 |
| `experiments/ica26/figures/fig_reliability_pv_mobilenet_v3_small_s42.pdf` | Reliability diagrams for run `pv_mobilenet_v3_small_s42`, one panel per evaluation block, with ECE printed in each panel title. | 4.97 x 1.54 | 17,748 |
| `experiments/ica26/figures/fig_reliability_pv_resnet50_s1337.pdf` | Reliability diagrams for run `pv_resnet50_s1337`, one panel per evaluation block, with ECE printed in each panel title. | 4.97 x 1.54 | 17,518 |
| `experiments/ica26/figures/fig_reliability_pv_resnet50_s2026.pdf` | Reliability diagrams for run `pv_resnet50_s2026`, one panel per evaluation block, with ECE printed in each panel title. | 4.97 x 1.54 | 17,707 |
| `experiments/ica26/figures/fig_reliability_pv_resnet50_s42.pdf` | Reliability diagrams for run `pv_resnet50_s42`, one panel per evaluation block, with ECE printed in each panel title. | 4.97 x 1.54 | 17,737 |

### 5c. PNG previews (not for LaTeX)

| Path from repo root | Bytes |
|---|---|
| `experiments/ica26/figures/fig_risk_coverage.png` | 85,630 |
| `experiments/ica26/figures/fig_seed_spread.png` | 50,681 |
| `experiments/ica26/figures/fig_training_curves.png` | 146,714 |

---

## 6. Per-class cross-domain metrics (notable cases)

Source: `evaluations.cross_domain_plantdoc_core.per_class` and `.confusion_matrix` in `experiments/ica26/metrics/pv_*_s*.json`. 1951 images over 21 shared classes. Support is identical across seeds (the evaluation set is fixed by the lock).

### 6a. Smallest test support among the 21 shared classes

| Class | Support | Share of 1,951 |
|---|---:|---:|
| `tomato__mosaic_virus` | 54 | 2.77% |
| `cherry__healthy` | 57 | 2.92% |
| `pepper__healthy` | 61 | 3.13% |
| `tomato__healthy` | 63 | 3.23% |
| `grape__black_rot` | 64 | 3.28% |
| `soybean__healthy` | 65 | 3.33% |

Zero-support classes: none.

### 6b. Classes predictions collapse onto

Predicted-class counts summed over the three seeds, against that class's true support summed over the same three seeds (support x 3).

**ResNet-50** (n=3 seeds, 5,853 predictions total)

| Predicted class | Predictions | Share | True support x3 | Ratio |
|---|---:|---:|---:|---:|
| `tomato__late_blight` | 1,731 | 29.6% | 333 | 5.20x |
| `tomato__early_blight` | 616 | 10.5% | 264 | 2.33x |
| `grape__black_rot` | 482 | 8.2% | 192 | 2.51x |
| `tomato__septoria_spot` | 400 | 6.8% | 447 | 0.89x |

**EfficientNet-B0** (n=3 seeds, 5,853 predictions total)

| Predicted class | Predictions | Share | True support x3 | Ratio |
|---|---:|---:|---:|---:|
| `tomato__late_blight` | 1,540 | 26.3% | 333 | 4.62x |
| `cherry__healthy` | 764 | 13.1% | 171 | 4.47x |
| `tomato__early_blight` | 452 | 7.7% | 264 | 1.71x |
| `tomato__septoria_spot` | 408 | 7.0% | 447 | 0.91x |

**MobileNetV3-Small** (n=3 seeds, 5,853 predictions total)

| Predicted class | Predictions | Share | True support x3 | Ratio |
|---|---:|---:|---:|---:|
| `tomato__late_blight` | 1,288 | 22.0% | 333 | 3.87x |
| `tomato__early_blight` | 905 | 15.5% | 264 | 3.43x |
| `grape__black_rot` | 567 | 9.7% | 192 | 2.95x |
| `squash__powdery_mildew` | 446 | 7.6% | 390 | 1.14x |

### 6c. Shared classes receiving zero predictions

- **ResNet-50**: 0 of 21 — none
- **EfficientNet-B0**: 0 of 21 — none
- **MobileNetV3-Small**: 0 of 21 — none

### 6d. Retained probability mass before renormalisation

| Model | s42 | s1337 | s2026 |
|---|---:|---:|---:|
| ResNet-50 | 0.7281 | 0.6425 | 0.5394 |
| EfficientNet-B0 | 0.6520 | 0.6574 | 0.6689 |
| MobileNetV3-Small | 0.6157 | 0.5624 | 0.5205 |

---

## 7. Paths in the .tex sources that point outside `paper/`

### `paper/ica2026.tex`

| Line | Command | As written | Resolves to (from repo root) |
|---:|---|---|---|
| 230 | `\input` | `../experiments/ica26/tables/table1_dataset_statistics.tex` | `experiments/ica26/tables/table1_dataset_statistics.tex` |
| 461 | `\input` | `../experiments/ica26/tables/table2_in_domain_performance_compact.tex` | `experiments/ica26/tables/table2_in_domain_performance_compact.tex` |
| 470 | `\input` | `../experiments/ica26/tables/table3_cross_domain_performance_compact.tex` | `experiments/ica26/tables/table3_cross_domain_performance_compact.tex` |
| 471 | `\input` | `../experiments/ica26/tables/table5_domain_shift_degradation_compact.tex` | `experiments/ica26/tables/table5_domain_shift_degradation_compact.tex` |
| 480 | `\input` | `../experiments/ica26/tables/table6_calibration_compact.tex` | `experiments/ica26/tables/table6_calibration_compact.tex` |

### `paper/supplementary.tex`

| Line | Command | As written | Resolves to (from repo root) |
|---:|---|---|---|
| 56 | `\input` | `../experiments/ica26/tables/table1b_dataset_provenance.tex` | `experiments/ica26/tables/table1b_dataset_provenance.tex` |
| 60 | `\input` | `../experiments/ica26/tables/table2_in_domain_performance.tex` | `experiments/ica26/tables/table2_in_domain_performance.tex` |
| 61 | `\input` | `../experiments/ica26/tables/table3_cross_domain_performance.tex` | `experiments/ica26/tables/table3_cross_domain_performance.tex` |
| 62 | `\input` | `../experiments/ica26/tables/table5_domain_shift_degradation.tex` | `experiments/ica26/tables/table5_domain_shift_degradation.tex` |
| 66 | `\input` | `../experiments/ica26/tables/table4_efficiency.tex` | `experiments/ica26/tables/table4_efficiency.tex` |
| 70 | `\input` | `../experiments/ica26/tables/table6_calibration.tex` | `experiments/ica26/tables/table6_calibration.tex` |
| 74 | `\input` | `../experiments/ica26/tables/table7_ranking_stability.tex` | `experiments/ica26/tables/table7_ranking_stability.tex` |
| 75 | `\input` | `../experiments/ica26/tables/table7b_ranking_margins.tex` | `experiments/ica26/tables/table7b_ranking_margins.tex` |
| 79 | `\input` | `../experiments/ica26/tables/table8_confidence_intervals.tex` | `experiments/ica26/tables/table8_confidence_intervals.tex` |
| 80 | `\input` | `../experiments/ica26/tables/table8b_mcnemar.tex` | `experiments/ica26/tables/table8b_mcnemar.tex` |
| 81 | `\input` | `../experiments/ica26/tables/table9_significance_across_seeds.tex` | `experiments/ica26/tables/table9_significance_across_seeds.tex` |
| 91 | `\includegraphics` | `fig_training_curves.pdf` | `experiments/ica26/figures/fig_training_curves.pdf` |
| 100 | `\includegraphics` | `fig_risk_coverage.pdf` | `experiments/ica26/figures/fig_risk_coverage.pdf` |
| 107 | `\includegraphics` | `fig_seed_spread.pdf` | `experiments/ica26/figures/fig_seed_spread.pdf` |

### Distinct files that must travel with the .tex

- `experiments/ica26/figures/fig_risk_coverage.pdf`
- `experiments/ica26/figures/fig_seed_spread.pdf`
- `experiments/ica26/figures/fig_training_curves.pdf`
- `experiments/ica26/tables/table1_dataset_statistics.tex`
- `experiments/ica26/tables/table1b_dataset_provenance.tex`
- `experiments/ica26/tables/table2_in_domain_performance.tex`
- `experiments/ica26/tables/table2_in_domain_performance_compact.tex`
- `experiments/ica26/tables/table3_cross_domain_performance.tex`
- `experiments/ica26/tables/table3_cross_domain_performance_compact.tex`
- `experiments/ica26/tables/table4_efficiency.tex`
- `experiments/ica26/tables/table5_domain_shift_degradation.tex`
- `experiments/ica26/tables/table5_domain_shift_degradation_compact.tex`
- `experiments/ica26/tables/table6_calibration.tex`
- `experiments/ica26/tables/table6_calibration_compact.tex`
- `experiments/ica26/tables/table7_ranking_stability.tex`
- `experiments/ica26/tables/table7b_ranking_margins.tex`
- `experiments/ica26/tables/table8_confidence_intervals.tex`
- `experiments/ica26/tables/table8b_mcnemar.tex`
- `experiments/ica26/tables/table9_significance_across_seeds.tex`

`\graphicspath{{../experiments/ica26/figures/}}` in both preambles is what makes the bare `\includegraphics` filenames resolve.
