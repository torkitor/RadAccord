# Auditoría independiente del conjunto reservado de muestreo

9 de septiembre de 2026. Archivos leídos: `sampling_reserved_v1/cases.jsonl`, `volumes.jsonl`, `checkpoint_demo.jsonl` y `run_summary.json`. No se regeneraron operadores, imágenes ni resultados. El conjunto clínico no forma parte de este informe.

**Contabilidad completa y verificaciones PASS:** 32 volúmenes sintéticos reservados, semillas 31000–31031, con 14 casos por volumen: **448 previstos y 448 registros ejecutados**. Cero duplicados, casos ausentes, no disponibles, no alcanzados o indeterminados. Las etiquetas `satisfied` de muestreo no se confunden con preservación de soporte ni permiso universal de reutilización de características.

| Grupo | Previstos/ejecutados | Resultado |
|---|---:|---|
| Siete controles válidos | 224/224 | 224 `satisfied` |
| Seis mutaciones propias | 192/192 | 190 activas: 190 `violated`; 2 inactivas: 2 `satisfied` |
| Control de truncamiento de ROI | 32/32 | 32 muestreos `satisfied`, 32 coberturas `violated`, 32 reutilizaciones `blocked` |

Los dos mutantes inactivos son `stale_crop_origin` en `synthetic_31001` y `synthetic_31023`: sus métricas de actividad no muestran cambio de intensidad, pertenencia de ROI ni origen. Se conservaron tanto en los 192 casos previstos como en el estrato inactivo. No son falsos negativos de una mutación activa.

Los 96 remuestreos correctos a 0.8, 1 y 2 mm requieren reextracción. Los otros 128 controles válidos tienen correspondencia integral de las muestras seleccionadas (`input_roi_preserved`), sujeta a requisitos de características, configuración y contexto; no se afirma igualdad de cualquier característica.

| Comparador en los 190 mutantes activos | `violated` | `satisfied` | `not_applicable` |
|---|---:|---:|---:|
| QA de emparejamiento imagen–máscara | 0 | 190 | 0 |
| Geometría referida a la fuente y a B | 62 | 128 | 0 |
| Testigo histórico de rejilla completa | 32 | 0 | 158 |
| Nuevo testigo de muestreo | 190 | 0 | 0 |

La detección geométrica corresponde a 30 mutantes activos de origen de crop y 32 desplazamientos de origen compartido. La no aplicabilidad del testigo histórico se conserva como tal; no se cuenta como detección. Estas son comparaciones de casos construidos, no sensibilidad clínica ni observaciones independientes de pacientes.

**Frontera de archivos:** los 448 casos tienen roundtrip NIfTI evaluable. No hay desacuerdos entre memoria y archivo en estado del muestreo, checks de componentes, estado de cobertura o decisión de reutilización. Los errores físicos numéricos de escritura pueden ser no nulos; la comparación no exige identidad de esos números.

**Verificación independiente:** el script privado `audit_sampling_results.py` confirmó 448 relaciones lógicas de estados, 192 clasificaciones de actividad, 3584 diferencias escalares ya registradas y 448 relaciones de volumen de vóxel derivadas de `det(B) det(L)`. Las diferencias escalares se cotejaron exactamente con la resta de sus operandos decodificados; la relación geométrica de volumen se comprobó con tolerancia relativa y absoluta 1e-12 como comprobación auxiliar, sin modificar criterios del testigo. Los 16 archivos del freeze conservan sus SHA-256; los hashes de fuentes registrados por el harness concuerdan con ese freeze.

El tiempo total registrado por volumen para los 14 casos, incluidos sus roundtrips, tuvo mediana **1.564 s**, intervalo intercuartílico **1.343–1.788 s** y rango **0.679–2.138 s**. El run completo registró 49.706 s. Son tiempos de esta ejecución sintética y este entorno; no se extrapolan al rendimiento clínico. Los tiempos de operador, testigo, I/O y volumen están separados en los CSV.

## Artefactos y reproducción

- `RadAccord/scripts/summarize_sampling_study.py`, SHA-256 `570a96ee3ec2f4b6b7dea79731edb9c1221b825594cb087eb03525a10d5a594f`.
- `work/sampling_summary_sanity.py` y `sampling_summary_sanity.json`: **10/10 pruebas PASS**, fixtures derivados únicamente de desarrollo. Cubren duplicados, registros ausentes, ledger parcial 5+1+8, abstenciones separadas, discrepancia de archivo, manipulación numérica y preservación de los archivos originales.
- `work/sampling_reserved_v1_summary/`: 11 CSV en total, JSON con IDs contribuyentes y hashes de entrada. `case_rows.csv` conserva los resultados por caso y `execution_ledger.csv` todos los IDs previstos.
- `work/sampling_reserved_v1_independent_audit.json`: comprobaciones y contadores leídos independientemente de los CSV.
- Freeze SHA-256: `1618ecf0b48772dead25256a68049e6f9cae5fb5a1996b6ac8d8b89576a23059`.
- `cases.jsonl` SHA-256: `4beb4d8ca341be3612b6c14b3df5625e5ac0669c448ca80d5df7a13211f6e05d`.
- `run_summary.json` SHA-256: `b05b65c49caa07dee8dd269407b7d980395f1a39633f50e92f79f9a344b00f74`.

Desde `RadAccord/`, usar una ruta de salida nueva:

```text
python -B scripts/summarize_sampling_study.py --input ../work/sampling_reserved_v1 --output ../work/reserved_summary_reproduced
```

El resumidor es posterior al freeze y descriptivo: registra su propio hash, no altera datos ni umbrales, no vuelve a ejecutar testigos y no calcula intervalos de confianza basados en independencia de casos.
