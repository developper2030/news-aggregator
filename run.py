#!/usr/bin/env python3
"""
News Aggregator — Pipeline Runner
==================================

Usage examples
--------------
Full pipeline (CI / before deployment):
    python run.py

Quick local test — scrape Arabic only, then generate all:
    python run.py --lang ar

Scrape two languages:
    python run.py --lang ar,fr

Just regenerate HTML from existing DB (no scraping, ~30 sec):
    python run.py --generate-only

Scrape without AI summaries (faster locally):
    python run.py --lang ar --no-summary

Backfill og:description for articles with no summary:
    python run.py --fill-desc
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))

import json as _json
from scraper.scrape import run as run_scraper, fill_article_descriptions
from generate_site import generate_html
from summarizer.summarize import summarize_articles
from clustering.cluster import run_clustering

_ROOT = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_ROOT, "data")

# ── Language configuration table ──────────────────────────────────────────────
LANGS = {
    "ar": {
        "config": os.path.join(_ROOT, "config", "sources.json"),
        "db":     os.path.join(_DATA, "news.db"),
        "out":    os.path.join(_ROOT, "static", "ar"),
        "label":  "Arabic",
    },
    "en": {
        "config": os.path.join(_ROOT, "config", "sources-en.json"),
        "db":     os.path.join(_DATA, "news-en.db"),
        "out":    os.path.join(_ROOT, "static"),
        "label":  "English",
    },
    "fr": {
        "config": os.path.join(_ROOT, "config", "sources-fr.json"),
        "db":     os.path.join(_DATA, "news-fr.db"),
        "out":    os.path.join(_ROOT, "static", "fr"),
        "label":  "French",
    },
    "es": {
        "config": os.path.join(_ROOT, "config", "sources-es.json"),
        "db":     os.path.join(_DATA, "news-es.db"),
        "out":    os.path.join(_ROOT, "static", "es"),
        "label":  "Spanish",
    },
    "tr": {
        "config": os.path.join(_ROOT, "config", "sources-tr.json"),
        "db":     os.path.join(_DATA, "news-tr.db"),
        "out":    os.path.join(_ROOT, "static", "tr"),
        "label":  "Turkish",
    },
}
ALL_LANGS = list(LANGS.keys())   # ["ar","en","fr","es","tr"]


def _load_api_keys() -> dict:
    """Return API keys from config file + env var overrides."""
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


# ── Pipeline steps ────────────────────────────────────────────────────────────

def scrape(langs: list[str]) -> None:
    """Scrape the given language(s)."""
    for code in langs:
        cfg = LANGS[code]
        print(f"\n[{code.upper()}] Scraping {cfg['label']} sources...")
        run_scraper(config_path=cfg["config"], db_path=cfg["db"])


def summarize(langs: list[str]) -> None:
    """Run AI summarization for the given language(s)."""
    keys = _load_api_keys()
    gemini_key = keys["gemini"]
    groq_key   = keys["groq"]

    if not gemini_key and not groq_key:
        print("\n[AI] No Gemini or Groq API key — skipping summaries")
        return

    provider = "Gemini" if gemini_key else "Groq"
    print(f"\n[AI] Generating summaries with {provider}…")

    # Gemini free tier: 1500 req/day ÷ (5 langs × 4 CI runs) = 75/lang/run
    _batch = 75 if gemini_key else 250
    for code in langs:
        n = summarize_articles(
            db_path=LANGS[code]["db"],
            lang=code,
            batch_size=_batch,
            gemini_key=gemini_key,
            groq_key=groq_key,
        )
        if n:
            print(f"  [{code.upper()}] {n} articles summarized")


def cluster(langs: list[str]) -> None:
    """Build story clusters for the given language(s)."""
    print("\n[Clustering] Building story clusters…")
    for code in langs:
        run_clustering(code, LANGS[code]["db"], _DATA)


def generate(langs: list[str]) -> list[str]:
    """Generate HTML for the given language(s). Returns output paths."""
    outputs = []
    for code in langs:
        cfg = LANGS[code]
        print(f"\n[{code.upper()}] Generating {cfg['label']} site...")
        path = generate_html(
            config_path=cfg["config"],
            db_path=cfg["db"],
            output_dir=cfg["out"],
            lang=code,
        )
        outputs.append(path)
    return outputs


def fill_desc(batch_size: int = 2000) -> None:
    """Backfill og:description for articles with no summary (manual use)."""
    print("\n[DESC] Backfilling og:description…")
    for code in ALL_LANGS:
        n = fill_article_descriptions(LANGS[code]["db"], batch_size=batch_size)
        if n:
            print(f"  [{code.upper()}] {n} descriptions filled")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="News aggregator pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                      Full pipeline — all 5 languages (CI)
  python run.py --lang ar            Quick: scrape Arabic only, generate all
  python run.py --lang ar,fr         Scrape Arabic + French, generate all
  python run.py --generate-only      Regenerate HTML only (~30 sec)
  python run.py --lang ar --no-summary  Scrape without AI (fastest local test)
  python run.py --fill-desc          Backfill og:description for old articles
        """,
    )
    parser.add_argument(
        "--lang",
        default="",
        metavar="CODES",
        help="Comma-separated language codes to scrape (e.g. ar  or  ar,fr). "
             "Omit to scrape all 5 languages.",
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Skip scraping — only cluster + generate HTML from existing DB.",
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Scrape only, do not generate HTML.",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip AI summarization step (faster for local testing).",
    )
    parser.add_argument(
        "--fill-desc",
        action="store_true",
        help="Backfill og:description for articles with no summary, then exit.",
    )
    args = parser.parse_args()

    # Resolve which languages to scrape
    if args.lang:
        scrape_langs = [c.strip().lower() for c in args.lang.split(",") if c.strip()]
        invalid = [c for c in scrape_langs if c not in LANGS]
        if invalid:
            parser.error(f"Unknown language code(s): {', '.join(invalid)}. Choose from: {', '.join(ALL_LANGS)}")
    else:
        scrape_langs = ALL_LANGS

    print("=" * 50)
    print("News Aggregator Pipeline")
    print("=" * 50)

    # ── Special modes ──────────────────────────────────────────────────────
    if args.fill_desc:
        fill_desc()
        print("\n" + "=" * 50)
        print("Description backfill done!")
        print("=" * 50)
        return

    if args.scrape_only:
        scrape(scrape_langs)
        print("\n" + "=" * 50)
        print(f"Scraping done! ({', '.join(scrape_langs)})")
        print("=" * 50)
        return

    if args.generate_only:
        cluster(ALL_LANGS)
        outputs = generate(ALL_LANGS)
        print("\n" + "=" * 50)
        print("Generation done!")
        for p in outputs:
            print(f"  {p}")
        print("=" * 50)
        return

    # ── Default / --lang mode ──────────────────────────────────────────────
    scrape(scrape_langs)

    if not args.no_summary:
        summarize(scrape_langs)

    cluster(ALL_LANGS)          # always cluster all (cross-language story links)
    outputs = generate(ALL_LANGS)  # always generate all (consistent site)

    print("\n" + "=" * 50)
    print("Done!")
    for p in outputs:
        print(f"  {p}")
    print("=" * 50)


if __name__ == "__main__":
    main()
