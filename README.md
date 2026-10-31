# 🔥 NUMIDIA EYE

**Algeria's fire alarm, from space.** AI-powered wildfire intelligence on live NASA satellite data.

## The problem

In August 2026, Algeria lost 12 lives and saw 54 injured in a single day of wildfires — 154 fires burning at once (Source: Reuters). Satellite detections exist, but nobody turns them into verified, actionable incident information. NUMIDIA EYE does.

## Live demo

🌐 **https://numidiaeye.me** (mirror: https://numidia-eye-budxbrcabueshrdz.francecentral-01.azurewebsites.net)

Bilingual dashboard (English/العربية): live detections, AI-verified incidents, priority ranking.

## About

### Every year, Algeria burns

Every summer, the same story comes back. Heat, drought and wind turn the forests of the north — Kabylia, the Tell Atlas, the coastal wilayas — into tinder, and fires return year after year. Villages are threatened, homes and olive groves and forests are lost, and civil protection teams are stretched across many fronts at once. It is not a one-off disaster; it is a season Algeria lives through, again and again.

That is why early detection matters so much. A fire spotted hours earlier is a fire that can still be contained before it reaches a village or jumps a road. A fire spotted late is already a rescue. NUMIDIA EYE exists for that gap: to see the fire from space, verify it honestly, and put it on the map while there is still time to act.

### Understand

Tap any dot for the AI verdict card and its explanation. Open an incident report for the full picture. The environment panel (wind, heat, dryness from Open-Meteo) is human context only — it never feeds the AI verdict.

Detections close in space and time are grouped into incidents — a spatiotemporal cluster, not a confirmed fire. Priority is rule-based and never uses model output.

### Honest limits

The north is **LIVE**. The south reads **UNAVAILABLE**: there are no confirmed southern wildfire labels, so the system shows gray rather than guessing. If the model is unavailable, the verifier fails closed instead of inventing a verdict. NUMIDIA EYE is an independent research prototype, not an official alert system and never a dispatch service — for a real emergency, call Protection Civile on 14 or 1021.

### Data and sources

Detections: NASA FIRMS VIIRS, via the NUMIDIA EYE API. Map: the project's own wilaya boundaries on a custom map style, no external tile server. Environment: Open-Meteo. Code is MIT; data terms are stated per layer. No site-wide data license is declared.

### What happens next

Next, we integrate a smarter AI model: upgrade the verifier into a weather-aware model trained on more labeled data, including southern wildfires, so the south stops reading UNAVAILABLE. Then Arabic alerts to wilaya civil protection units, backed by the DGF director's public October 2026 statement that the directorate needs new technologies for early detection, monitoring and rapid intervention. The satellite burn-scar vision track (Sentinel-2 dNBR prototype, already built and tested) stays on the post-submission roadmap.

## How it works

1. **Ingest** — fresh fire detections from NASA FIRMS, every 30 minutes
2. **Locate** — each detection mapped to its wilaya (69 units)
3. **Verify** — a trained AI verifier scores every detection: FIRE / NON-FIRE / UNCERTAIN
4. **Serve** — dashboard, incidents, priority ranking, reports

## The AI

A random-forest verifier (400 trees, 10 satellite features), trained on 12,847 labeled detections and tested on a held-out set of 20,716: **94% precision / 81% recall**.

**Scope (honest):** the test set measures fire-vs-flare separation — the negative class is mostly catalogued gas flares. There are no independently confirmed southern-Algerian wildfire positives in the labels, so the south reads UNAVAILABLE. This is an experimental verifier, not a validated nationwide wildfire detector. It fails closed: if the model is unavailable, the API returns 503, never a fabricated verdict.

## Quick start

```bash
cp .env.example .env   # set FIRMS_MAP_KEY (free NASA key, server-side only)
uv sync --extra api --extra dev
uv run python -m numidia_worker.cli fetch
uv run uvicorn numidia_api.app:app --host 0.0.0.0 --port 8010
cd apps/web && npm install && npm run dev
```

Full setup: `docs/SETUP.md`.

## Who built what

- **BOUCIF MOHAMED HOUSSEM EDDINE** — Founder. Built everything: data pipeline, API, AI verifier, dashboard, pitch.
- **Imen Benelhadj Djelloul** — Fetched the fire data.
- **Sofiane Khelfaoui** — Civil protection advisor.
- **Amir Boughomd** — Web Application Tester & Ai Specialist.
- **Milissa Temam** — Vision track: satellite burn-scar validation prototype, AI specialist.

## Roadmap

Evacuation routes per incident, closing the southern label gap, wiring the validated flare-persistence filter into the verifier, and a live DGPC pilot in one wilaya.
