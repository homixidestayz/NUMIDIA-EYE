# NUMIDIA verifier â€” model experiment exp-v1

**Experimental V2 model â€” NOT YET REGISTERED FOR PRODUCTION**

Model: `hgb` (HistGradientBoostingClassifier) Â· threshold 0.6 Â· seed 42 Â· sklearn 1.9.1
Dataset: `C:\Users\Admin\Documents\NUMIDIA-EYE\data\labels\firms_labels_v2.csv` (sha256 `d8e9fbb3fd18â€¦`, read-only) Â· fit rows: 21845 (fire/non-fire only (uncertain/excluded excluded))
Features (exact): bright_ti4, bright_ti5, f_bt_diff, frp, f_frp, confidence, f_confidence, scan, track, satellite, type

## Selection (validation only â€” fire-only val, recall can be measured, precision cannot)

Rule (predeclared): higher val recall at chosen threshold; tie-break train PR-AUC.
Ranking: hgb > rf.
- rf: train sweep [0.3:F1=0.975,R=1.000,P=0.951 | 0.4:F1=0.979,R=0.999,P=0.959 | 0.5:F1=0.983,R=0.998,P=0.969 | 0.6:F1=0.988,R=0.996,P=0.980 | 0.7:F1=0.989,R=0.988,P=0.990] â†’ chosen 0.7 (max train F1 â€” optimistic, documented).
  val (n=201, fire-only): recall@thr={'0.3': 1.0, '0.4': 0.995, '0.5': 0.99, '0.6': 0.9602, '0.7': 0.9502}, mean_proba=0.9409, train PR-AUC=0.9996.
- hgb: train sweep [0.3:F1=0.981,R=0.999,P=0.964 | 0.4:F1=0.984,R=0.999,P=0.970 | 0.5:F1=0.987,R=0.997,P=0.977 | 0.6:F1=0.989,R=0.993,P=0.984 | 0.7:F1=0.987,R=0.986,P=0.988] â†’ chosen 0.6 (max train F1 â€” optimistic, documented).
  val (n=201, fire-only): recall@thr={'0.3': 0.9751, '0.4': 0.9652, '0.5': 0.9652, '0.6': 0.9602, '0.7': 0.9303}, mean_proba=0.9336, train PR-AUC=0.9992.

## Test (evaluated ONCE after freeze â€” no tuning on test)

- ROC-AUC **0.9175** Â· PR-AUC **0.9353** Â· accuracy 0.6852 Â· Brier 0.2440 Â· ECE 0.2840
- precision 0.6187 Â· recall 0.9597 Â· F1 0.7524
- confusion: TP 9907 / TN 4288 / FP 6105 / FN 416 (n=20716)

### Stratified test metrics (grouping only â€” never features)

**lat_band**
- north: n=10847, acc=0.925, P=0.961, R=0.960, F1=0.961, ROC-AUC=0.897, TP/TN/FP/FN=9907/126/398/416
- south: n=9869, acc=0.422, P=0.000, R=0.000, F1=0.000, ROC-AUC=None, TP/TN/FP/FN=0/4162/5707/0

**daynight**
- D: n=5644, acc=0.987, P=1.000, R=0.987, F1=0.993, ROC-AUC=None, TP/TN/FP/FN=5569/0/0/75
- N: n=15072, acc=0.572, P=0.415, R=0.927, F1=0.574, ROC-AUC=0.844, TP/TN/FP/FN=4338/4288/6105/341

**satellite**
- N: n=7036, acc=0.697, P=0.609, R=0.977, F1=0.750, ROC-AUC=0.932, TP/TN/FP/FN=3195/1710/2055/76
- N20: n=7480, acc=0.695, P=0.632, R=0.960, F1=0.762, ROC-AUC=0.925, TP/TN/FP/FN=3647/1552/2128/153
- N21: n=6200, acc=0.660, P=0.615, R=0.942, F1=0.744, ROC-AUC=0.89, TP/TN/FP/FN=3065/1026/1922/187

**cohort**
- 2026: n=20716, acc=0.685, P=0.619, R=0.960, F1=0.752, ROC-AUC=0.918, TP/TN/FP/FN=9907/4288/6105/416

### Fire-event level (test)

- events: 140 Â· median recall 1.0 Â· min 0.0 Â· p10 0.7464
- worst 5 events: EFFIS:DZ:651196 R=0.0 (n=1); EFFIS:DZ:637281 R=0.0 (n=1); EFFIS:DZ:637265 R=0.0 (n=1); EFFIS:DZ:673078 R=0.3333 (n=3); EFFIS:DZ:662769 R=0.5 (n=2)

## Limitations (must-read before any registration discussion)

- Validation holds ONE fire event (AOI02) and zero non-fire rows: model/threshold choice rests on recall-only evidence plus optimistic train F1. The test score below is the first honest number.
- Latitude/daynight shortcuts were excluded by feature contract, not by data: verify stratified rows above (north-band and night-only slices) before trusting aggregates.
- No uncertain/excluded rows were used for fitting; calibration is reported on supervised test rows only.
- This artifact is LOCAL (gitignored) and UNREGISTERED: the live API still returns 503 AI_UNAVAILABLE.

## Post-fit leakage verification

- X columns == approved contract: True
- banned columns in X: NONE — clean
- X columns: bright_ti4, bright_ti5, f_bt_diff, frp, f_frp, confidence, f_confidence, scan, track, satellite, type
