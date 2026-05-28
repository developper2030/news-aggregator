"""
AI Article Summarizer — Atlas News
Uses Groq API (llama-3.1-8b-instant) to generate 2-sentence summaries.

- Summaries are stored in the DB and never re-generated for the same article.
- Rate-limited to stay within Groq free tier (30 req/min).
- Gracefully skips on API errors — site generation never blocked.
"""

import time
import json
import logging

try:
    import requests as _requests
    _USE_REQUESTS = True
except ImportError:
    import urllib.request as _urlreq
    import urllib.error as _urlerr
    _USE_REQUESTS = False

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.1-8b-instant"

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

# Groq free tier: 30 req/min → 1 req every 2s to be safe
_REQUEST_DELAY = 2.1


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
        import urllib.request as _ur, urllib.error as _ue
        req = _ur.Request(GROQ_API_URL,
                          data=json.dumps(payload).encode("utf-8"),
                          headers=headers, method="POST")
        with _ur.urlopen(req, timeout=15) as r:
            result = json.loads(r.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"].strip()


def summarize_articles(
    db_path: str,
    api_key: str,
    lang: str,
    batch_size: int = 200,
) -> int:
    """
    Find articles without summaries in *db_path*, call Groq, store results.
    Returns the number of articles successfully summarized.
    """
    if not api_key:
        logger.info("Summarizer: no Groq API key — skipping")
        return 0

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
            summary = _call_groq(art["title"], lang, api_key)
            update_article_summary(art["url"], summary)
            done += 1
            if (i + 1) % 10 == 0:
                logger.info("Summarizer [%s]: %d/%d done", lang, done, len(articles))
            time.sleep(_REQUEST_DELAY)
        except Exception as http_e:
            # Handle both requests.HTTPError and urllib.error.HTTPError
            status = getattr(getattr(http_e, "response", None), "status_code",
                             getattr(http_e, "code", 0))
            body = ""
            try:
                if hasattr(http_e, "response") and http_e.response is not None:
                    body = http_e.response.text[:200]
                elif hasattr(http_e, "read"):
                    body = http_e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            logger.warning("Summarizer [%s]: HTTP %s — %s", lang, status, body)
            errors += 1
            if status == 429:
                logger.info("Summarizer: rate-limited, sleeping 60s…")
                time.sleep(60)
            elif errors >= 5:
                logger.warning("Summarizer: too many errors, aborting batch")
                break
        except Exception as e:
            logger.warning("Summarizer [%s]: error on '%s': %s", lang, art["title"][:60], e)
            errors += 1
            if errors >= 5:
                logger.warning("Summarizer: too many errors, aborting batch")
                break

    logger.info("Summarizer [%s]: finished — %d summarized, %d errors", lang, done, errors)
    return done
