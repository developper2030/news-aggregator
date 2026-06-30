"""
AI Article Summarizer — Solvixi News
Supports four backends (auto-selected by available API keys):

  1. Google Gemini 2.5 Flash  (GEMINI_API_KEY)
       Free tier: 30 req/min, 1 500 req/day
       Fastest + highest quality.  batch=75/lang/run

  2. OpenRouter               (OPENROUTER_API_KEY)
       Free tier: models marked :free (Llama 3.3-70B, etc.)
       Higher quality than Groq 8B.  batch=50/lang/run

  3. NVIDIA NIM               (NVIDIA_API_KEY)
       Free starter credits, then pay-per-use.
       High quality 70B models.  batch=100/lang/run

  4. Groq llama-3.1-8b-instant (GROQ_API_KEY)
       Free tier: 30 req/min, 14 400 req/day
       Best free daily quota.  batch=100/lang/run

Priority: Gemini > OpenRouter > NVIDIA > Groq
If no key is present the step is silently skipped.

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

# ── Gemini ────────────────────────────────────────────────────────────────────
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

# ── OpenRouter (OpenAI-compatible) ────────────────────────────────────────────
OPENROUTER_API_URL   = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL     = "meta-llama/llama-3.3-70b-instruct:free"
OPENROUTER_SITE_URL  = "https://news.solvixi.com"
OPENROUTER_SITE_NAME = "Solvixi News"

# ── NVIDIA NIM (OpenAI-compatible) ────────────────────────────────────────────
NVIDIA_API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL   = "meta/llama-3.1-8b-instruct"

# ── Groq (OpenAI-compatible) ──────────────────────────────────────────────────
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"

# Rate limits — conservative sleep to stay under free-tier caps
# All OpenAI-compat providers: ~30 req/min → 2.1 s/req
# Gemini: 30 req/min → 2.1 s/req
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


# ── Generic OpenAI-compatible caller (Groq / OpenRouter / NVIDIA) ─────────────

def _call_openai_compat(
    title: str, lang: str, api_key: str,
    url: str, model: str,
    extra_headers: dict | None = None,
) -> str:
    """Call any OpenAI-compatible /v1/chat/completions endpoint."""
    payload = {
        "model":       model,
        "messages":    [{"role": "user", "content": _build_prompt(title, lang)}],
        "max_tokens":  150,
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
        "User-Agent":    "python-requests/2.31.0",
        "Accept":        "application/json",
        **(extra_headers or {}),
    }
    if _USE_REQUESTS:
        resp = _requests.post(url, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    else:
        import urllib.request as _ur
        _req = _ur.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with _ur.urlopen(_req, timeout=20) as r:
            result = json.loads(r.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"].strip()


# ── Unified caller ────────────────────────────────────────────────────────────

def _call_api(
    title: str, lang: str,
    gemini_key: str = "",
    openrouter_key: str = "",
    nvidia_key: str = "",
    groq_key: str = "",
) -> str:
    """Try providers in priority order: Gemini > OpenRouter > NVIDIA > Groq."""
    if gemini_key:
        return _call_gemini(title, lang, gemini_key)
    if openrouter_key:
        return _call_openai_compat(
            title, lang, openrouter_key,
            url=OPENROUTER_API_URL, model=OPENROUTER_MODEL,
            extra_headers={
                "HTTP-Referer": OPENROUTER_SITE_URL,
                "X-Title":      OPENROUTER_SITE_NAME,
            },
        )
    if nvidia_key:
        return _call_openai_compat(
            title, lang, nvidia_key,
            url=NVIDIA_API_URL, model=NVIDIA_MODEL,
        )
    if groq_key:
        return _call_openai_compat(
            title, lang, groq_key,
            url=GROQ_API_URL, model=GROQ_MODEL,
        )
    raise ValueError("No API key provided")


# ── Public entry-point ────────────────────────────────────────────────────────

def summarize_articles(
    db_path: str,
    lang: str,
    batch_size: int = 200,
    api_key: str = "",          # legacy: Groq key
    gemini_key: str = "",
    openrouter_key: str = "",
    nvidia_key: str = "",
    groq_key: str = "",
) -> int:
    """
    Find articles without summaries in *db_path*, call AI API, store results.
    Returns the number of articles successfully summarized.

    Key priority: Gemini > OpenRouter > NVIDIA > Groq > api_key (legacy).
    """
    _groq       = groq_key or api_key
    _gemini     = gemini_key
    _openrouter = openrouter_key
    _nvidia     = nvidia_key

    if not any([_gemini, _openrouter, _nvidia, _groq]):
        logger.info("Summarizer [%s]: no API key — skipping", lang)
        return 0

    if _gemini:         provider = "Gemini"
    elif _openrouter:   provider = "OpenRouter"
    elif _nvidia:       provider = "NVIDIA NIM"
    else:               provider = "Groq"
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

    # Mutable provider keys — on quota exhaustion (429) we clear the failing
    # provider and cascade to the next one without sleeping.
    _active_gemini     = _gemini
    _active_openrouter = _openrouter
    _active_nvidia     = _nvidia
    _active_groq       = _groq

    for i, art in enumerate(articles):
        try:
            summary = _call_api(
                art["title"], lang,
                gemini_key=_active_gemini,
                openrouter_key=_active_openrouter,
                nvidia_key=_active_nvidia,
                groq_key=_active_groq,
            )
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

            if status == 429:
                # Quota exhausted — cascade to next provider immediately (no sleep)
                if _active_gemini:
                    logger.warning("Summarizer [%s]: Gemini quota exhausted → switching to OpenRouter", lang)
                    _active_gemini = ""
                elif _active_openrouter:
                    logger.warning("Summarizer [%s]: OpenRouter quota exhausted → switching to NVIDIA", lang)
                    _active_openrouter = ""
                elif _active_nvidia:
                    logger.warning("Summarizer [%s]: NVIDIA quota exhausted → switching to Groq", lang)
                    _active_nvidia = ""
                elif _active_groq:
                    logger.warning("Summarizer [%s]: all providers exhausted — sleeping 60s", lang)
                    _active_groq = ""
                    time.sleep(60)
                else:
                    logger.warning("Summarizer [%s]: no providers left — aborting batch", lang)
                    break
            else:
                errors += 1
                if errors >= 5:
                    logger.warning("Summarizer: too many errors, aborting batch")
                    break

    logger.info("Summarizer [%s]: finished — %d summarized, %d errors",
                lang, done, errors)
    return done
