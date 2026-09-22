# numidia_ml - trained AI verifier (NEXT PHASE — explicitly not started)

This directory will hold `numidia_ml`: a real, evaluated classifier that
flags VIIRS fire detections as confirmed-fire vs non-fire (gas flares,
thermometers, noise) **given a valid labeled dataset**.

## Why it is intentionally empty right now

Training an honest verifier requires labeled examples of confirmed fires
(and confirmed non-fires) over Algeria. That dataset does not exist yet.
Per the project's Data & AI integrity rule, the system reports
`AI_UNAVAILABLE` in the API and UI rather than fabricating probabilities.

## Path to a real model (labeling decision — pending user sign-off)

1. **Positives:** curate real confirmed 2026 wildfire events in Algeria
   (Civil Protection announcements, wilaya governorate reports, media with
   dates/coordinates; NOT invented). Extract FIRMS detections matching those
   events.
2. **Negatives:** Algerian gas-flare sites (Hassi Messaoud, In Amenas,
   Hassi R'Mel, Berkine ...) are real recurring FIRMS hotspots — they are
   flares, not wildfires; they form a legitimate non-fire class.
3. Train + evaluate a small model (random forest / gradient boosting) on
   `data/processed/firms_features.csv`-style features with time-based split.
4. Commit the evaluation report to `data/evaluation/` and only then wire the
   model into the API `/detections/{id}/ai` endpoint (removing 503).

Artifacts: models/ and artifacts/ are gitignored until they exist.