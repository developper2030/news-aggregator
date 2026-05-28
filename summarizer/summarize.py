"""
AI Article Summarizer — Atlas News
Supports two backends (auto-detected from available API keys):

  1. Google Gemini 2.0 Flash-Lite (preferred)
       Free tier: 30 req/min, 1 500 req/day
       No Cloudflare blocking, fastest responses.

  2. Groq llama-3.1-8b-instant (fallback)
       Free tier: 30 req/min, 14 400 req/day
       Needs `requests` library to bypass Cloudflare TLS fingerprinting.

Priority: Gemini > Groq.  If neither key is present the step is silently skipped.

- Summaries are stored in the DB and never re-generated for the same article.
- RSS descriptions scraped at scrape-time already fill most ai_summary fields;
  this module upgrades only articles that still have no summary.
- Rate-limited to stay within free-tier limits.
- Gracefully skips on API errors — site generation is never blocked.
"""

import time
import json
import logging

try:
    import requests as _requests
    _USE_REQUESTS = True
except ImportError:
    _USE_REQUESTS = False

logger = logging.getLogger(__name__)

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

# Rate limits (per-request sleep to stay under free-tier caps)
# Groq:   30 req/min → 2.1 s/req
# Gemini: 30 req/min → 2.1 s/req  (flash-lite has 30 RPM on free tier)
_REQUEST_DELAY = 2.1

# Language names for the prompt
_LANG_NAMES = {
    "ar": "Arabic",
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "tr": "Turkish",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ru": "Russian",
    "fa": "Persian",
    "hi": "Hindi",
    "zh": "Chinese",
}


def _build_prompt(title: str, lang: str) -> str:
    lang_name = _LANG_NAMES.get(lang, "English")
    return (
        f"You are a professional news summarizer. "
        f"Given the following news headline, write exactly 2 concise, informative sentences "
        f"that provide context and summarize the topic. "
        f"Write in {lang_name}. Do not repeat the headline. "
        f"Do not start with 'The article' or 'This article'. "
        f"Be factual and neutral.\n\n"
        f"Headline: {title}"
    )


# ── Gemini call ───────────────────────────────────────────────────────────────

def _call_gemini(title: str, lang: str, api_key: str) -> str:
    """Call Google Gemini API and return the summary text. Raises on failure."""
    payload = {
        "contents": [{"parts": [{"text": _build_prompt(title, lang)}]}],
        # maxOutputTokens 800 gives Gemini 2.5 enough room for internal
        # thinking tokens + the 2-sentence output (~150 visible tokens).
        "generationConfig": {
            "maxOutputTokens": 800,
            "temperature": 0.4,
        },
    }
    url = f"{GEMINI_API_URL}?key={api_key}"

    if _USE_REQUESTS:
        resp = _requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    else:
        import urllib.request as _ur
        req = _ur.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with _ur.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))

    # Parse Gemini response — skip any "thought" parts (internal reasoning)
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(
            p["text"] for p in parts if not p.get("thought", False)
        ).strip()
        if not text:
            raise ValueError("Empty text in Gemini response")
        return text
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Unexpected Gemini response structure: {data}") from exc


# ── Groq call ─────────────────────────────────────────────────────────────────

def _call_groq(title: str, lang: str, api_key: str) -> str:
    """Call Groq API and return the summary text. Raises on failure."""
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": _build_prompt(title, lang)}],
        "max_tokens": 150,
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "python-requests/2.31.0",
        "Accept": "application/json",
    }

    if _USE_REQUESTS:
        resp = _requests.post(GROQ_API_URL, json=payload,
                              headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    else:
        import urllib.request as _ur
        req = _ur.Request(
            GROQ_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with _ur.urlopen(req, timeout=15) as r:
            result = json.loads(r.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"].strip()


# ── Unified caller ────────────────────────────────────────────────────────────

def _call_api(title: str, lang: str,
              gemini_key: str = "", groq_key: str = "") -> str:
    """Try Gemini first, fall back to Groq. Raises if both fail."""
    if gemini_key:
        return _call_gemini(title, lang, gemini_key)
    if groq_key:
        return _call_groq(title, lang, groq_key)
    raise ValueError("No API key provided (gemini or groq)")


# ── Public entry-point ────────────────────────────────────────────────────────

def summarize_articles(
    db_path: str,
    lang: str,
    batch_size: int = 200,
    api_key: str = "",        # Groq key (legacy param kept for back-compat)
    gemini_key: str = "",
    groq_key: str = "",
) -> int:
    """
    Find articles without summaries in *db_path*, call AI API, store results.
    Returns the number of articles successfully summarized.

    Key priority: gemini_key > groq_key > api_key (legacy).
    RSS descriptions from the scraper already fill most ai_summary fields;
    this function handles the remainder.
    """
    # Resolve keys (back-compat: positional api_key treated as groq_key)
    _groq  = groq_key or api_key
    _gemini = gemini_key

    if not _gemini and not _groq:
        logger.info("Summarizer [%s]: no API key (Gemini or Groq) — skipping", lang)
        return 0

    provider = "Gemini" if _gemini else "Groq"
    logger.info("Summarizer [%s]: using %s", lang, provider)

    # Import here to allow the module to load even before db is set up
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from database.db import set_db_path, get_unsummarized_articles, update_article_summary

    set_db_path(db_path)
    articles = get_unsummarized_articles(limit=batch_size)

    if not articles:
        logger.info("Summarizer [%s]: all articles already summarized", lang)
        return 0

    logger.info("Summarizer [%s]: summarizing %d articles…", lang, len(articles))
    done = 0
    errors = 0

    for i, art in enumerate(articles):
        try:
            summary = _call_api(art["title"], lang,
                                 gemini_key=_gemini, groq_key=_groq)
            update_article_summary(art["url"], summary)
            done += 1
            if (i + 1) % 10 == 0:
                logger.info("Summarizer [%s]: %d/%d done", lang, done, len(articles))
            time.sleep(_REQUEST_DELAY)

        except Exception as exc:
            # Extract HTTP status code from requests or urllib errors
            status = getattr(getattr(exc, "response", None), "status_code",
                             getattr(exc, "code", 0))
            body = ""
            try:
                if hasattr(exc, "response") and exc.response is not None:
                    body = exc.response.text[:200]
                elif hasattr(exc, "read"):
                    body = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass

            if body:
                logger.warning("Summarizer [%s]: HTTP %s — %s", lang, status, body)
            else:
                logger.warning("Summarizer [%s]: error on '%s': %s",
                               lang, art["title"][:60], exc)

            errors += 1
            if status == 429:
                logger.info("Summarizer: rate-limited, sleeping 60s…")
                time.sleep(60)
            elif errors >= 5:
                logger.warning("Summarizer: too many errors, aborting batch")
                break

    logger.info("Summarizer [%s]: finished — %d summarized, %d errors",
                lang, done, errors)
    return done
