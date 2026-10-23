"""LLM integration for NUMIDIA EYE — natural verdict explanations and incident briefings.

Uses Groq (free tier, OpenAI-compatible API). The API key comes from the
GROQ_API_KEY environment variable (set in Azure app settings by the operator).

Design principles:
- GROUNDED: The LLM only describes data we provide. The prompt explicitly
  forbids inventing values, locations, or facts not in the input.
- CACHED: Explanations are cached in SQLite by detection/incident ID + model
  version. Repeat views cost nothing.
- FALLBACK: If the LLM is unavailable (no key, API error, timeout), the
  caller gets None and the frontend uses the template explanations.
- BILINGUAL: Explanations generated in English and Arabic (two calls, cached
  separately).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")  # GPT OSS 20B on Groq
# Hugging Face fallback (free inference API)
HF_API_URL = "https://api-inference.huggingface.co/models/meta-llama/Llama-3.3-70B-Instruct"
TIMEOUT_S = 15
CACHE_TABLE = "llm_cache"


def is_configured() -> bool:
    """True if a Groq or Hugging Face API key is available."""
    return bool(os.environ.get("GROQ_API_KEY", "").strip()) or bool(
        os.environ.get("HF_API_KEY", "").strip()
    )


def _call_hf(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Call Hugging Face Inference API. Returns text or None on failure."""
    api_key = os.environ.get("HF_API_KEY", "").strip()
    if not api_key:
        return None
    payload = {
        "inputs": f"<|system|>{system_prompt}<|user|>{user_prompt}<|assistant|>",
        "parameters": {"max_new_tokens": 250, "temperature": 0.3},
    }
    req = urllib.request.Request(
        HF_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
            # HF returns a list with generated_text
            if isinstance(data, list) and data:
                text = data[0].get("generated_text", "")
                # Extract only the assistant's reply (after the last <|assistant|>)
                if "<|assistant|>" in text:
                    text = text.split("<|assistant|>")[-1].strip()
                return text.strip() or None
            return None
    except Exception:
        return None


def _cache_path(db_path: Path) -> Path:
    return Path(db_path)


def _init_cache(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(f"""CREATE TABLE IF NOT EXISTS {CACHE_TABLE} (
            cache_key TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            created_at REAL NOT NULL
        )""")
        con.commit()
    finally:
        con.close()


def _cache_key(kind: str, item_id: str, lang: str, data_hash: str) -> str:
    raw = f"{kind}:{item_id}:{lang}:{data_hash}:{GROQ_MODEL}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _get_cached(db_path: Path, key: str) -> Optional[str]:
    try:
        con = sqlite3.connect(str(db_path))
        try:
            row = con.execute(
                f"SELECT response FROM {CACHE_TABLE} WHERE cache_key = ?", (key,)
            ).fetchone()
            return row[0] if row else None
        finally:
            con.close()
    except Exception:
        return None


def _set_cached(db_path: Path, key: str, response: str) -> None:
    try:
        _init_cache(db_path)
        con = sqlite3.connect(str(db_path))
        try:
            con.execute(
                f"INSERT OR REPLACE INTO {CACHE_TABLE} (cache_key, response, created_at) VALUES (?, ?, ?)",
                (key, response, time.time()),
            )
            con.commit()
        finally:
            con.close()
    except Exception:
        pass  # Cache is best-effort; never break the request


def _call_groq(system_prompt: str, user_prompt: str) -> Optional[str]:
    """Call Groq API (with HF fallback). Returns text or None on failure."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        # Try Hugging Face as fallback
        return _call_hf(system_prompt, user_prompt)

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,  # Low temp for factual, consistent output
        "max_tokens": 300,
    }

    req = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TimeoutError):
        return None
    except Exception:
        return None


# ── Verdict explanations ──────────────────────────────────────────

EXPLAIN_SYSTEM_EN = """You explain AI wildfire-verdicts for NUMIDIA EYE, an Algeria fire-monitoring dashboard.

RULES:
- Only describe the data provided. Never invent values, locations, or facts.
- The "model score" is the AI's output (0.0-1.0). ≥0.52 = FIRE, ≤0.33 = NON_FIRE, between = UNCERTAIN.
- FIRMS confidence is the satellite's observation quality (low/nominal/high), NOT a fire probability.
- Be concise: 2-3 sentences. Plain language, no jargon.
- If confidence is low but verdict is FIRE, briefly note that the observation was unclear but the thermal signature was strong."""

EXPLAIN_SYSTEM_AR = """أنت تشرح قرارات الذكاء الاصطناعي لرصد حرائق الغابات في منصة NUMIDIA EYE الجزائرية.

القواعد:
- صف البيانات المقدمة فقط. لا تخترع قيماً أو مواقع أو حقائق.
- "نموذج النقاط" هو ناتج الذكاء الاصطناعي (0.0-1.0). ≥0.52 = حريق، ≤0.33 = ليس حريقاً، بينهما = غير مؤكد.
- ثقة FIRMS هي جودة رصد القمر الصناعي، وليست احتمال الحريق.
- كن موجزاً: 2-3 جمل. لغة بسيطة."""


def explain_verdict(
    db_path: Path,
    detection: dict,
    ai_result: dict,
    lang: str = "en",
) -> Optional[str]:
    """Generate an LLM explanation for a single detection's AI verdict.

    Returns the explanation text, or None if the LLM is unavailable
    (caller should fall back to templates).
    """
    if not is_configured():
        return None

    # Build a data hash so cache invalidates if the detection data changes
    data_str = json.dumps(detection, sort_keys=True, default=str)
    data_hash = hashlib.sha256(data_str.encode()).hexdigest()[:16]
    det_id = str(detection.get("id", "unknown"))

    key = _cache_key("explain", det_id, lang, data_hash)
    cached = _get_cached(db_path, key)
    if cached:
        return cached

    # Extract the fields the LLM needs (grounded, no invention)
    verdict = ai_result.get("prediction", "UNKNOWN")
    score = ai_result.get("probability")
    frp = detection.get("frp")
    t4 = detection.get("bright_ti4")
    t5 = detection.get("bright_ti5")
    conf = detection.get("confidence")
    lat = detection.get("lat")
    lon = detection.get("lon")
    acq = detection.get("acq_datetime") or detection.get("acquired")

    bt_diff = (t4 - t5) if (t4 is not None and t5 is not None) else None
    conf_pct = round(conf * 100) if isinstance(conf, (int, float)) else None

    if lang == "ar":
        system = EXPLAIN_SYSTEM_AR
        user = f"""اشرح هذا القرار:
- القرار: {verdict}
- نقاط النموذج: {score:.2f} إن وجدت
- القدرة الإشعاعية (FRP): {frp} ميغاواط إن وجدت
- درجة حرارة السطح: {t4} كلفن إن وجدت
- التباين الحراري: {bt_diff:.0f} كلفن إن وجد
- ثقة القمر الصناعي: {conf_pct}% إن وجدت
- الموقع: خط عرض {lat}، خط طول {lon}"""
    else:
        system = EXPLAIN_SYSTEM_EN
        user = f"""Explain this verdict:
- Verdict: {verdict}
- Model score: {score:.2f} if available
- Fire radiative power (FRP): {frp} MW if available
- Surface temperature: {t4} K if available
- Thermal contrast: {bt_diff:.0f} K if available
- Satellite confidence: {conf_pct}% if available
- Location: lat {lat}, lon {lon}"""

    result = _call_groq(system, user)
    if result:
        _set_cached(db_path, key, result)
    return result


# ── Incident summaries ────────────────────────────────────────────

SUMMARY_SYSTEM_EN = """You write briefings for Algerian civil protection units about wildfire incidents detected by NUMIDIA EYE.

RULES:
- Only use the data provided. Never invent locations, numbers, or facts.
- Structure: 1) What/where (wilaya, coordinates), 2) Severity (detection count, max FRP, AI verdicts), 3) Recommended action.
- Be concise: 3-4 sentences. Professional tone, actionable.
- If the data is limited, say so honestly."""

SUMMARY_SYSTEM_AR = """أنت تكتب إحاطات لوحدات الحماية المدنية الجزائرية حول حوادث حرائق الغابات التي رصدتها منصة NUMIDIA EYE.

القواعد:
- استخدم البيانات المقدمة فقط. لا تخترع مواقع أو أرقام أو حقائق.
- الهيكل: 1) ماذا/أين (الولاية، الإحداثيات)، 2) الخطورة (عدد الرصدات، أقصى قدرة إشعاعية، قرارات الذكاء الاصطناعي)، 3) الإجراء الموصى به.
- كن موجزاً: 3-4 جمل. نبرة مهنية قابلة للتنفيذ."""


def summarize_incident(
    db_path: Path,
    incident: dict,
    detections: list[dict],
    lang: str = "en",
) -> Optional[str]:
    """Generate an LLM briefing for a fire incident.

    Returns the briefing text, or None if the LLM is unavailable.
    """
    if not is_configured():
        return None

    inc_id = str(incident.get("id", "unknown"))
    data_str = json.dumps({"inc": incident, "dets": detections}, sort_keys=True, default=str)
    data_hash = hashlib.sha256(data_str.encode()).hexdigest()[:16]

    key = _cache_key("summary", inc_id, lang, data_hash)
    cached = _get_cached(db_path, key)
    if cached:
        return cached

    # Aggregate the data (grounded)
    n = len(detections)
    frps = [d.get("frp") for d in detections if isinstance(d.get("frp"), (int, float))]
    max_frp = max(frps) if frps else None
    wilaya = incident.get("wilaya_name") or incident.get("wilaya_code") or "unknown"
    lat = incident.get("lat") or incident.get("center_lat")
    lon = incident.get("lon") or incident.get("center_lon")

    # Count verdicts if available
    verdicts = {}
    for d in detections:
        v = (d.get("ai") or {}).get("prediction") if isinstance(d.get("ai"), dict) else None
        if v:
            verdicts[v] = verdicts.get(v, 0) + 1

    if lang == "ar":
        system = SUMMARY_SYSTEM_AR
        user = f"""اكتب إحاطة عن هذا الحادث:
- الولاية: {wilaya}
- الموقع: خط عرض {lat}، خط طول {lon}
- عدد الرصدات: {n}
- أقصى قدرة إشعاعية: {max_frp} ميغاواط إن وجدت
- قرارات الذكاء الاصطناعي: {verdicts}"""
    else:
        system = SUMMARY_SYSTEM_EN
        user = f"""Write a briefing for this incident:
- Wilaya: {wilaya}
- Location: lat {lat}, lon {lon}
- Detection count: {n}
- Max FRP: {max_frp} MW if available
- AI verdicts: {verdicts}"""

    result = _call_groq(system, user)
    if result:
        _set_cached(db_path, key, result)
    return result
