# 🔥 NUMIDIA EYE

**Algeria's fire alarm, from space.** AI-powered wildfire intelligence on live NASA satellite data.

## The problem

In August 2026, Algeria lost 12 lives and saw 54 injured in a single day of wildfires — 154 fires burning at once (Source: Reuters). Satellite detections exist, but nobody turns them into verified, actionable incident information. NUMIDIA EYE does.

## Live demo

🌐 **https://numidia-eye-budxbrcabueshrdz.francecentral-01.azurewebsites.net**

Bilingual dashboard (English/العربية): live detections, AI-verified incidents, priority ranking.

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

- **Mohamed Houssem Eddine Boucif** — everything: data pipeline, API, AI verifier, dashboard, pitch.
- **Milissa Temmam** — vision track: satellite burn-scar validation prototype.

## Roadmap

Evacuation routes per incident, closing the southern label gap, wiring the validated flare-persistence filter into the verifier, and a live DGPC pilot in one wilaya.
