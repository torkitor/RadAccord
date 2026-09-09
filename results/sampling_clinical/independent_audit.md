# Auditoría independiente de la ejecución sobre imágenes clínicas públicas

9 de septiembre de 2026. Lectura de los registros finales de `sampling_clinical_v1/`, ejecución del mismo resumidor descriptivo ya probado y cotejo independiente de aritmética, estados y hashes. No se regeneró ningún operador, imagen o resultado. No se modificó código congelado, datos ni umbrales.

**PASS de contabilidad e integridad:** se conservaron los **4214/4214 casos previstos**, procedentes de **301/301 volúmenes liberados**: 260 de Task04_Hippocampus (MRI) y 41 de Task09_Spleen (CT), cada uno con 14 casos. No hay duplicados, no disponibles, casos no alcanzados ni exclusiones posteriores al resultado. La unidad es volumen liberado; no se presupone que corresponda a 301 pacientes independientes. La máscara evaluada es la unión binaria de etiquetas positivas, no cada clase anatómica por separado.

## Resultados principales y denominadores

| Grupo | MRI: previstos y ejecutados | CT: previstos y ejecutados | Total y resultado |
|---|---:|---:|---|
| Siete controles válidos | 1820 | 287 | 2107: **2096 satisfechos, 11 indeterminados, 0 violaciones** |
| Seis mutaciones propias | 1560 | 246 | 1806: **1605 activas y violadas; 201 inactivas y satisfechas** |
| Control de pérdida de soporte | 260 | 41 | 301: muestreo satisfecho, cobertura violada, reutilización bloqueada |
| Todos los casos | 3640 | 574 | **4214: 2598 satisfechos, 1605 violados, 11 indeterminados** en el componente de muestreo |

Los 2598 estados de muestreo satisfecho incluyen 301 controles que pierden soporte y 201 mutantes inactivos. **No son 2598 aprobaciones de reutilización.**

| Operación/caso | MRI: satisfecho / violado / indeterminado | CT: satisfecho / violado / indeterminado |
|---|---:|---:|
| Crop con margen de ROI | 260 / 0 / 0 | 41 / 0 / 0 |
| Identidad | 260 / 0 / 0 | 41 / 0 / 0 |
| Padding | 260 / 0 / 0 | 41 / 0 / 0 |
| Permutación y flips | 260 / 0 / 0 | 41 / 0 / 0 |
| Isotrópico 0.8 mm | 260 / 0 / 0 | 40 / 0 / 1 |
| Isotrópico 1 mm | 260 / 0 / 0 | 36 / 0 / 5 |
| Isotrópico 2 mm | 260 / 0 / 0 | 36 / 0 / 5 |
| Origen anterior tras crop | 201 / 59 / 0 | 0 / 41 / 0 |
| Desplazamiento compartido del origen | 0 / 260 / 0 | 0 / 41 / 0 |
| Desplazamiento de muestreo de medio vóxel | 0 / 260 / 0 | 0 / 41 / 0 |
| Kernel incorrecto de imagen | 0 / 260 / 0 | 0 / 41 / 0 |
| Máscara lineal seguida de umbral | 0 / 260 / 0 | 0 / 41 / 0 |
| Almacenamiento entero prematuro | 0 / 260 / 0 | 0 / 41 / 0 |
| Truncamiento declarado de ROI | 260 / 0 / 0 | 41 / 0 / 0 |

Los 201 mutantes inactivos pertenecen a `stale_crop_origin` de MRI. En todos ellos son cero los cambios exactos registrados de intensidad, pertenencia de ROI y geometría: el origen no cambia. Se mantienen en los 1806 intentos de mutación y se separan del denominador de 1605 mutantes activos. La actividad se volvió a calcular a partir de las métricas retenidas y las tolerancias declaradas para cada caso.

## Once abstenciones conservadoras, sin discrepancia nominal

Los once casos indeterminados pertenecen a cinco volúmenes CT. Sus checks son `candidate_shape=true`, `position=true`, `intensity=true`, `roi=null`. En todos ellos:

- `strict_nominal_status=satisfied`, con **cero diferencias nominales de ROI** y cero diferencias nominales de intensidad por encima del umbral;
- cero vóxeles incompatibles de ROI o intensidad y cero vóxeles de intensidad ambigua;
- cobertura de centros fuente satisfecha, sin centros ciertamente fuera del FOV ni cerca de su límite;
- reutilización **bloqueada**, porque la banda de incertidumbre de índices fijada antes del estudio permite vecinos NN con distinta pertenencia a la ROI.

Por tanto, estos casos son abstenciones de la política conservadora previamente fijada, **no once fallos observados de SimpleITK**. La concordancia nominal por sí sola no elimina la ambigüedad de vecindario declarada.

| Volumen CT | Rejilla | Posiciones candidatas con ROI ambigua | Diferencias nominales de ROI |
|---|---:|---:|---:|
| spleen_16 | 0.8 mm | 14294 | 0 |
| spleen_16 | 1 mm | 9232 | 0 |
| spleen_16 | 2 mm | 2306 | 0 |
| spleen_27 | 1 mm | 7896 | 0 |
| spleen_27 | 2 mm | 1978 | 0 |
| spleen_45 | 1 mm | 9442 | 0 |
| spleen_45 | 2 mm | 2370 | 0 |
| spleen_49 | 1 mm | 15040 | 0 |
| spleen_49 | 2 mm | 3764 | 0 |
| spleen_52 | 1 mm | 8058 | 0 |
| spleen_52 | 2 mm | 2012 | 0 |

Las 76392 posiciones ambiguas sumadas entre estos once casos no representan vóxeles ni pacientes independientes. El máximo error de intensidad en los once casos fue 2.290789780090563e-11 unidades; no se relajó la tolerancia de 1e-4.

## Comparadores, soporte y reutilización

| Comparador, sólo 1605 mutantes activos | Violado | Satisfecho | No aplicable |
|---|---:|---:|---:|
| QA de emparejamiento imagen–máscara | 0 | 1605 | 0 |
| Geometría referida a fuente y B | 401 | 1204 | 0 |
| Testigo histórico de rejilla completa | 301 | 0 | 1304 |
| Testigo de muestreo | 1605 | 0 | 0 |

Los 401 rechazos geométricos corresponden a los 100 cambios activos de origen tras crop (59 MRI + 41 CT) y los 301 desplazamientos compartidos del origen. El testigo histórico detecta los 301 desplazamientos compartidos; la no aplicabilidad a los otros 1304 casos se conserva como tal, no se convierte en detección. Los 1204 mutantes activos restantes son cuatro familias por 301 volúmenes, con geometría declarada correcta pero contenido de imagen o ROI alterado. No se infiere sensibilidad clínica a partir de estas intervenciones propias.

Entre los controles válidos, 1204 operaciones integrales (1040 MRI + 164 CT) conservan la correspondencia de inputs ROI. Los 903 remuestreos previstos se dividen en **892 satisfechos que requieren reextracción** (780 MRI + 112 CT) y **11 indeterminados bloqueados**. Los 301 crops de truncamiento ejecutan correctamente la operación declarada, pero pierden soporte de ROI y bloquean la reutilización. La conservación de inputs ROI no demuestra igualdad universal de características ni validez clínica.

Referencias de las mutaciones: el origen anterior tras crop se compara contra el crop correcto, manteniendo como fuente el volumen original; el desplazamiento compartido se compara contra el crop de trabajo correcto. Las otras cuatro mutaciones se comparan contra el resultado correcto a **0.8 mm** del mismo volumen. Las diferencias `candidate_minus_source` tienen otro denominador y se conservan por separado. Para controles, `correct_operation` es el propio resultado observado: sus diferencias cero frente a esa referencia son **por construcción** y no una validación independiente.

## Frontera NIfTI y checkpoints

El subconjunto prefijado contiene `hippocampus_001`, `hippocampus_003`, `hippocampus_004` y `spleen_10`, `spleen_12`, `spleen_13`, con 14 casos por volumen. Se completaron **84/84 roundtrips**: **50 satisfechos y 34 violados**, exactamente iguales a sus estados en memoria. Los 34 violados son **16 MRI + 18 CT**. No hay desacuerdos en estado de muestreo, checks de componentes, estado de cobertura o decisión de reutilización. Los otros 4130 casos permanecen `not_selected`; no se sustituyen ni se les atribuye verificación de archivo.

Los once CT indeterminados están **fuera** de los tres volúmenes CT seleccionados. La concordancia de 84/84 no demuestra estabilidad de esas abstenciones a la serialización ni equivale a haber verificado en NIfTI todos los 4214 casos.

Los registros de checkpoints se conservan como demostraciones de estados suministrados. No diagnostican causas internas no observadas. La tabla `checkpoint_rows.csv` mantiene IDs, estado de endpoint y primer estado observado que falla.

## Tiempos observados

Cada tiempo total de volumen incluye los 14 casos y su sobrecarga registrada. Los primeros tres volúmenes de cada conjunto añaden roundtrips y exportación de inputs nativos; el primero añade la demostración de checkpoints. Por tanto, no se presenta como tiempo puro de un único testigo. La extracción de características nativas es un estudio separado y no está incluida aquí.

| Volúmenes | Mediana total (s) | Q1–Q3 (s) | Rango (s) |
|---|---:|---:|---:|
| MRI, n=260 | 0.399192 | 0.358086–0.454851 | 0.211844–1.789016 |
| CT, n=41 | 8.327169 | 6.044286–13.034124 | 3.756496–47.882834 |

Tiempo total del run: **550.1897376 s**. Las siguientes cifras son medianas por operación, en segundos; los CSV mantienen valores y cuantiles completos.

| Operación | MRI productor | MRI testigo | CT productor | CT testigo |
|---|---:|---:|---:|---:|
| crop_roi_margin | 0.000832 | 0.011509 | 0.001424 | 0.312629 |
| stale_crop_origin | 0.000442 | 0.011173 | 0.000848 | 0.318058 |
| identity | 0.000000 | 0.011316 | 0.000000 | 0.087121 |
| pad | 0.001522 | 0.013791 | 0.003682 | 0.097005 |
| orient | 0.003502 | 0.011233 | 0.016742 | 0.088928 |
| isotropic_0p8mm | 0.005787 | 0.041786 | 0.063357 | 0.960681 |
| isotropic_1mm | 0.003555 | 0.023191 | 0.031143 | 0.495450 |
| isotropic_2mm | 0.002188 | 0.003165 | 0.006436 | 0.073568 |
| shared_origin_shift | 0.000467 | 0.011305 | 0.000949 | 0.072137 |
| half_voxel_sampling_displacement | 0.005416 | 0.042811 | 0.058886 | 0.935335 |
| wrong_image_kernel | 0.004344 | 0.042976 | 0.049078 | 0.968840 |
| linear_mask_threshold | 0.008502 | 0.043441 | 0.101935 | 0.922973 |
| premature_integer_storage | 0.001523 | 0.042844 | 0.008413 | 0.875334 |
| roi_truncation | 0.001039 | 0.002496 | 0.001032 | 0.024499 |

El productor de identidad registra cero porque no ejecuta un nuevo operador. Los tiempos son descriptivos de esta máquina, datos y ejecución, sin intervalos de confianza ni extrapolación a otros volúmenes.

## Verificación independiente y artefactos

Se verificaron **16/16 hashes congelados**, **4214 relaciones lógicas de estados**, **1806 clasificaciones de actividad**, **33712 diferencias escalares exactas** y **4214 relaciones geométricas del volumen de vóxel mediante det(B)det(L)**. Esta última comprobación auxiliar usa tolerancia relativa y absoluta 1e-12; no modifica las tolerancias del testigo. Los hashes de las fuentes registrados por el harness concuerdan con el freeze local previo a la evaluación. El freeze es interno, no un registro público prospectivo.

- `work/sampling_clinical_v1_summary/summary.json` y sus **11 CSV** contienen todos los IDs y los denominadores, comparadores, soporte, reutilización, acuerdos NIfTI, tiempos y diferencias de estadísticas directas.
- `work/sampling_clinical_v1_independent_audit.json` contiene los checks y conteos independientes.
- El resumidor sin cambios tiene SHA-256 `570a96ee3ec2f4b6b7dea79731edb9c1221b825594cb087eb03525a10d5a594f`; sus 10 pruebas de desarrollo pasaron antes de resumir el conjunto reservado y clínico.
- Freeze: `1618ecf0b48772dead25256a68049e6f9cae5fb5a1996b6ac8d8b89576a23059`.
- `cases.jsonl`: `946342347683afbdd4d9c2a20b8c782fa1462a6dc7390366d837ad9f08a9a453`.
- `volumes.jsonl`: `fec49a685175c6f9adf72e21dab99f668d632bd8d13c3a2f592594fceae040c4`.
- `run_summary.json`: `16a75b4e45b583a36dbe5cb95138cbcfc0f449e8faf9dd4e43a20a0f193a5970`.
- `checkpoint_demo.jsonl`: `fb076d29ca14b2a17bd3dbcbef240e3b0ab5144bae2e88cd6d79f0f4be9f689a`.

Desde `RadAccord/`, con una ruta de salida nueva:

```text
python -B scripts/summarize_sampling_study.py --input ../work/sampling_clinical_v1 --output ../work/clinical_summary_reproduced
```

El resumidor no modifica los registros ni recalcula testigos. Las estadísticas directas son número de vóxeles, volumen ocupado, media y varianza poblacional de intensidad; no son por sí mismas validación de características radiométricas nativas, diagnóstico, beneficio clínico ni transportabilidad entre pacientes.
