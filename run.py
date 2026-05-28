#!/usr/bin/env python3
import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

import json as _json
from scraper.scrape import run as run_scraper, fill_article_descriptions
from generate_site import generate_html
from summarizer.summarize import summarize_articles
from clustering.cluster import run_clustering

_ROOT = os.path.dirname(os.path.abspath(__file__))
_AR_CONFIG = os.path.join(_ROOT, "config", "sources.json")
_EN_CONFIG = os.path.join(_ROOT, "config", "sources-en.json")
_FR_CONFIG = os.path.join(_ROOT, "config", "sources-fr.json")
_ES_CONFIG = os.path.join(_ROOT, "config", "sources-es.json")
_TR_CONFIG = os.path.join(_ROOT, "config", "sources-tr.json")
_AR_DB     = os.path.join(_ROOT, "data", "news.db")
_EN_DB     = os.path.join(_ROOT, "data", "news-en.db")
_FR_DB     = os.path.join(_ROOT, "data", "news-fr.db")
_ES_DB     = os.path.join(_ROOT, "data", "news-es.db")
_TR_DB     = os.path.join(_ROOT, "data", "news-tr.db")
_AR_OUT    = os.path.join(_ROOT, "static", "ar")
_EN_OUT    = os.path.join(_ROOT, "static")
_FR_OUT    = os.path.join(_ROOT, "static", "fr")
_ES_OUT    = os.path.join(_ROOT, "static", "es")
_TR_OUT    = os.path.join(_ROOT, "static", "tr")


def _load_api_keys() -> dict:
    """Return {'gemini': '...', 'groq': '...'} from config file + env vars."""
    _keys_path = os.path.join(_ROOT, "config", "api_keys.json")
    file_keys: dict = {}
    try:
        with open(_keys_path, "r", encoding="utf-8") as f:
            file_keys = _json.load(f)
    except (FileNotFoundError, _json.JSONDecodeError):
        pass
    return {
        "gemini": (file_keys.get("gemini") or os.environ.get("GEMINI_API_KEY", "")).strip(),
        "groq":   (file_keys.get("groq")   or os.environ.get("GROQ_API_KEY",   "")).strip(),
    }


def scrape_all():
    print("\n[AR] Scraping Arabic sources...")
    run_scraper(config_path=_AR_CONFIG, db_path=_AR_DB)
    print("\n[EN] Scraping English sources...")
    run_scraper(config_path=_EN_CONFIG, db_path=_EN_DB)
    print("\n[FR] Scraping French sources...")
    run_scraper(config_path=_FR_CONFIG, db_path=_FR_DB)
    print("\n[ES] Scraping Spanish sources...")
    run_scraper(config_path=_ES_CONFIG, db_path=_ES_DB)
    print("\n[TR] Scraping Turkish sources...")
    run_scraper(config_path=_TR_CONFIG, db_path=_TR_DB)


def fill_descriptions_all(batch_size: int = 300) -> None:
    """Fill og:description for all articles that still have no summary.

    Runs after scraping and before AI summarisation so Gemini only handles
    the small remainder that genuinely has no meta description.
    """
    print("\n[DESC] Filling article descriptions from og:description…")
    langs = [
        ("AR", _AR_DB), ("EN", _EN_DB), ("FR", _FR_DB),
        ("ES", _ES_DB), ("TR", _TR_DB),
    ]
    for label, db_path in langs:
        n = fill_article_descriptions(db_path, batch_size=batch_size)
        if n:
            print(f"  [{label}] {n} descriptions filled")


def summarize_all():
    keys = _load_api_keys()
    gemini_key = keys["gemini"]
    groq_key   = keys["groq"]

    if not gemini_key and not groq_key:
        print("\n[AI] No Gemini or Groq API key — skipping summaries")
        return

    provider = "Gemini" if gemini_key else "Groq"
    print(f"\n[AI] Generating summaries with {provider}…")

    langs = [
        ("ar", _AR_DB), ("en", _EN_DB), ("fr", _FR_DB),
        ("es", _ES_DB), ("tr", _TR_DB),
    ]
    # Gemini free tier: 1500 req/day total.
    # With 5 languages × 4 CI runs/day → max 75 per language per run to stay under limit.
    # Groq free tier: 14 400 req/day → can use higher batch if Gemini quota is exceeded.
    _batch = 75 if gemini_key else 250
    for lang, db_path in langs:
        n = summarize_articles(
            db_path=db_path,
            lang=lang,
            batch_size=_batch,
            gemini_key=gemini_key,
            groq_key=groq_key,
        )
        if n:
            print(f"  [{lang.upper()}] {n} articles summarized")


_DATA_DIR = os.path.join(_ROOT, "data")


def cluster_all():
    """Cluster articles per language and save results to data/clusters_*.json."""
    print("\n[Clustering] Building story clusters…")
    run_clustering("ar", _AR_DB, _DATA_DIR)
    run_clustering("en", _EN_DB, _DATA_DIR)
    run_clustering("fr", _FR_DB, _DATA_DIR)
    run_clustering("es", _ES_DB, _DATA_DIR)
    run_clustering("tr", _TR_DB, _DATA_DIR)


def generate_all():
    print("\n[AR] Generating Arabic site...")
    ar = generate_html(config_path=_AR_CONFIG, db_path=_AR_DB,
                       output_dir=_AR_OUT, lang="ar")
    print("\n[EN] Generating English site...")
    en = generate_html(config_path=_EN_CONFIG, db_path=_EN_DB,
                       output_dir=_EN_OUT, lang="en")
    print("\n[FR] Generating French site...")
    fr = generate_html(config_path=_FR_CONFIG, db_path=_FR_DB,
                       output_dir=_FR_OUT, lang="fr")
    print("\n[ES] Generating Spanish site...")
    es = generate_html(config_path=_ES_CONFIG, db_path=_ES_DB,
                       output_dir=_ES_OUT, lang="es")
    print("\n[TR] Generating Turkish site...")
    tr = generate_html(config_path=_TR_CONFIG, db_path=_TR_DB,
                       output_dir=_TR_OUT, lang="tr")
    return ar, en, fr, es, tr


def main():
    parser = argparse.ArgumentParser(description="News aggregator pipeline")
    parser.add_argument("--scrape-only",   action="store_true", help="Scrape only (both languages)")
    parser.add_argument("--generate-only", action="store_true", help="Generate only (both languages)")
    parser.add_argument("--fill-desc",     action="store_true",
                        help="Backfill og:description for all unsummarised articles (large batch)")
    args = parser.parse_args()

    print("=" * 50)
    print("News Aggregator - Full Pipeline")
    print("=" * 50)

    if args.fill_desc:
        fill_descriptions_all(batch_size=2000)
        print("\n" + "=" * 50)
        print("Description backfill done!")
        print("=" * 50)
        return

    if args.scrape_only:
        scrape_all()
        print("\n" + "=" * 50)
        print("Scraping done!")
        print("=" * 50)
        return

    if args.generate_only:
        cluster_all()
        outputs = generate_all()
        print("\n" + "=" * 50)
        print("Generation done!")
        for path in outputs:
            print(f"  Open: {path}")
        print("=" * 50)
        return

    # Default: full pipeline
    # Note: fill_descriptions_all() is NOT run here — use --fill-desc separately.
    # Homepage-level excerpt extraction (_find_excerpt) runs inside scrape_all()
    # with zero extra HTTP requests and gives ~30-50% coverage at scrape time.
    # The manual --fill-desc flag does a larger og:description backfill when needed.
    scrape_all()
    summarize_all()   # Gemini/Groq for articles still missing summaries
    cluster_all()
    outputs = generate_all()
    print("\n" + "=" * 50)
    print("Done!")
    for path in outputs:
        print(f"  Open: {path}")
    print("=" * 50)


if __name__ == "__main__":
    main()
