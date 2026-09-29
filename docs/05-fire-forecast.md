# 05 — Fire forecast (predictive model)

Phase 2. Detections tell the user where a fire is now. The forecast tells him how likely a fire is
near each field in the next days, so he can plan work and watch the right fields.

## Question

For each territory and horizon h ∈ {24 h, 48 h, 72 h}: what is the probability of at least one
satellite fire detection within 10 km of the territory during the next h hours?

The label is a satellite detection, not an ignition. Many fires in the region are stubble and pasture
burns set by people, and clouds hide some fires. The model predicts what FIRMS will see, and the UI
says so.

## Data

| Input | Source | Period |
|---|---|---|
| Labels | FIRMS VIIRS S-NPP archive (one sensor, so the label does not change when satellites are added) | 2012 to today |
| Weather, hourly | Open-Meteo historical API (ERA5) for training; Open-Meteo forecast for prediction | 2012 to today, next 3 days |
| Fire Weather Index | Canadian FWI system (FFMC, DMC, DC, ISI, BUI, FWI) computed daily from noon temperature, RH, wind and 24 h rain | derived |
| Fire history | Detections per cell and month in previous years, days since last detection in the cell | derived from labels |
| Vegetation (later) | Sentinel-2 NDVI anomaly per cell from Phase 1 | 2017 to today |

Training area: Entre Ríos and the Paraná Delta, on a 0.05° grid (about 5 km cells). Larroque alone
has too few fires to learn from; the Delta burns every year and shares weather with it.

## Model

- One row per cell and day. Features: FWI components, max temperature, min RH, max wind, days since
  rain ≥ 5 mm, rain in the last 7 and 30 days, day of year (sin/cos), cell fire history.
- Gradient boosted trees (LightGBM). Positives are rare (well under 1 % of cell-days), so class weights
  are tuned on validation and probabilities are calibrated afterwards (isotonic regression).
- A territory's probability combines the cells within 10 km: `1 - Π(1 - p_cell)`.

## Evaluation

- Temporal split, never random: train 2012–2021, validate 2022–2023, test 2024–2025. Random splits
  leak weather from the same days into both sides.
- Metrics: PR-AUC (ROC-AUC looks good on rare events even for weak models), Brier score, reliability
  curve per horizon.
- The model ships only if it beats both baselines on the test years:
  1. climatology: detection rate of the cell in the same month in previous years;
  2. FWI alone, calibrated.

## In the product

- Shown as a band, not a raw number: `LOW`, `MODERATE`, `HIGH`, `VERY_HIGH`, with the probability and
  the top three drivers from SHAP ("dry for 18 days", "FWI 32", "burns common here in August").
- Stored in a `fire_forecast` table with territory, horizon, issued_at, probability, band, drivers,
  model version and processing version.
- Retrained monthly; the model version is part of the processing version.

## Code

- `ml/fire_forecast/`: dataset builder, training and evaluation scripts, the evaluation report.
- `backend/app/services/fire_forecast.py`: daily inference in the worker with the exported model.
