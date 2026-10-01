# 05 — Fire forecast (predictive model)

Phase 2. Detections tell the user where a fire is now. The forecast tells him how likely a fire is
near each field in the next days, so he can plan work and watch the right fields.

## Question

For each territory and horizon h ∈ {1, 2, 3} days: what is the probability of at least one
satellite fire detection within 10 km of the territory during the next h days?

The label is a satellite detection, not an ignition. Many fires in the region are stubble and pasture
burns set by people, and clouds hide some fires. The model predicts what FIRMS will see, and the UI
says so.

## Data

| Input | Source | Period |
|---|---|---|
| Labels | FIRMS VIIRS S-NPP archive, vegetation fires only ([07-fire-history](07-fire-history.md)) | 2015–2024 |
| Daily weather | NASA POWER (MERRA-2 reanalysis, 0.5° × 0.625°): max temperature, specific humidity, surface pressure, 10 m wind, rain | 2015–2024 |
| Fire Weather Index | Canadian FWI system (Van Wagner 1987): FFMC, DMC, DC, ISI, BUI, FWI, run day by day | derived |
| Fire history | Fire days of the cell in the same month in earlier years; days since the last fire in the cell; fire days around the cell in the last 7 days | derived from labels |

- Why NASA POWER and not the Open-Meteo archive: POWER returns ten years of one point in one request
  and needs no key. The Open-Meteo free tier counts every two weeks of data as a call, so the same
  history would take days of the daily limit.
- The FWI wants noon temperature and humidity. Daily maximum temperature stands for noon, and the
  humidity at that temperature is computed from specific humidity and pressure (the air holds the
  same water all day; relative humidity is lowest when it is hottest).
- Each weather point is a 0.5° cell; a forecast cell uses its nearest point.

Training area: the region bounding box on a 0.1° grid (about 10 km cells), keeping only cells whose
center is in Argentina. The archive is per country, so Uruguayan cells would have no labels and
would teach the model that they never burn. Larroque alone has too few fires to learn from; the
Delta burns every year and shares weather with it.

## Model

- One row per cell and day; the label is a detection in the cell during the next h days. Features:
  the FWI components, max temperature, humidity at max temperature, wind, days since rain ≥ 5 mm,
  rain in the last 7 and 30 days, day of year (sin/cos), and the cell's fire history.
- Gradient boosted trees: scikit-learn `HistGradientBoostingClassifier`, the same family as
  LightGBM, with no native library to install. One model per horizon.
- Positives are rare (well under 1 % of cell-days). Probabilities are calibrated on the validation
  years with isotonic regression.
- A territory's probability combines the cells within 10 km: `1 - Π(1 - p_cell)`.

## Evaluation

- Temporal split, never random: train 2015–2021, validate 2022–2023, test 2024. Random splits leak
  weather from the same days into both sides.
- Metrics: PR-AUC (ROC-AUC looks good on rare events even for weak models), Brier score, and the
  share of fires caught in the top 5 % of cell-days by predicted risk.
- The model ships only if it beats all three baselines on the test year:
  1. climatology: fire days of the cell in the same month in earlier years;
  2. FWI alone, calibrated;
  3. persistence: fire around the cell in the last 7 days.
- `make forecast-train` writes the report to `docs/reports/fire-forecast.md`; it is committed with
  each retrain.

## In the product

- Shown as a band, not a raw number: `LOW`, `MODERATE`, `HIGH`, `VERY_HIGH`, with the probability and
  the main factors ("dry for 18 days", "FWI 32", "fires around in the last week").
- The factors are the features with the most weight in the model whose value today is far from
  usual for the cell. It is a plain explanation, not SHAP.
- Stored in a `fire_forecast` table with territory, horizon, issued_at, probability, band, factors,
  model version and processing version. Serving starts only after the report shows the model
  beats the baselines.

## Code

- `backend/app/forecast/`: `fwi.py` (Fire Weather Index), `weather_history.py` (NASA POWER),
  `dataset.py`, `train.py` and the report. Same package as the backend, so inference later uses the
  same feature code as training.
- Models are saved to `data/models/` (not committed).
