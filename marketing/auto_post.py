#!/usr/bin/env python3
"""
Atlas News — Social Auto-Poster  (legitimate, official APIs only)
================================================================

Reads the site's own RSS feed and posts the newest articles to:
  • Telegram channel   — via the official Bot API (free, built for this)
  • Mastodon instance  — via the official REST API (open, free)

This is 100% compliant automation:
  - Uses ONLY official, documented platform APIs with YOUR OWN bot/app tokens.
  - Posts links back to our own content (no scraping, no spam, no ToS abuse).
  - De-duplicated: never posts the same article twice (state file).
  - Rate-limited: posts at most --max items per run with a polite delay.

It does NOT (and will never):
  - Log into anyone's personal account or store passwords.
  - Bypass platform limits, captchas, or anti-bot systems.
  - Mass-DM, follow/unfollow farm, or any growth-hacking abuse.

──────────────────────────────────────────────────────────────────────────────
SETUP  (set these as environment variables — never hard-code secrets)

  Telegram (recommended — easiest, fully free):
    1. Open @BotFather on Telegram → /newbot → get a token.
    2. Create a public channel, add the bot as an administrator.
    TELEGRAM_BOT_TOKEN    = "123456:ABC-DEF..."
    TELEGRAM_CHANNEL_ID   = "@atlasnews"        (or numeric -100xxxxxxxxxx)

  Mastodon (open-source social network):
    1. Your instance → Preferences → Development → New application.
    2. Scopes: write:statuses. Copy the access token.
    MASTODON_BASE_URL     = "https://mastodon.social"
    MASTODON_ACCESS_TOKEN = "xxxxxxxx"

USAGE
  # Post up to 3 newest English items to whichever platforms are configured:
  python marketing/auto_post.py --lang en --max 3

  # Use a specific feed URL:
  python marketing/auto_post.py --feed https://atlasnews.solvixi.com/rss.xml

  # Preview without posting anything:
  python marketing/auto_post.py --lang en --max 3 --dry-run
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────
SITE_ROOT = "https://atlasnews.solvixi.com"

# Known feed URLs per language (root = English, others under /<lang>/)
FEEDS = {
    "en": f"{SITE_ROOT}/rss.xml",
    "ar": f"{SITE_ROOT}/ar/rss.xml",
    "fr": f"{SITE_ROOT}/fr/rss.xml",
    "es": f"{SITE_ROOT}/es/rss.xml",
    "tr": f"{SITE_ROOT}/tr/rss.xml",
}

# Per-language hashtags (kept short and relevant — no hashtag stuffing)
HASHTAGS = {
    "en": "#News #WorldNews #BreakingNews",
    "ar": "#أخبار #العالم #عاجل",
    "fr": "#Actualités #Monde #Info",
    "es": "#Noticias #Mundo #Última",
    "tr": "#Haber #Dünya #SonDakika",
}

STATE_FILE = Path(__file__).parent / ".posted.json"
USER_AGENT = "AtlasNewsAutoPoster/1.0 (+https://atlasnews.solvixi.com)"
POST_DELAY_SECONDS = 4  # polite pause between posts


# ── State (dedup) ───────────────────────────────────────────────────────────
def _load_state() -> set[str]:
    if STATE_FILE.exists():
        try:
            return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def _save_state(posted: set[str]) -> None:
    # Keep only the most recent 2000 GUIDs to bound the file size
    trimmed = list(posted)[-2000:]
    STATE_FILE.write_text(json.dumps(trimmed, ensure_ascii=False, indent=0),
                          encoding="utf-8")


# ── RSS fetching/parsing (stdlib only) ────────────────────────────────────────
def _fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _clean_title(raw: str, max_len: int = 200) -> str:
    """RSS titles in this site can concatenate title+excerpt; trim sensibly."""
    text = html.unescape(" ".join((raw or "").split()))
    # Cut at a natural sentence boundary if the title is very long
    if len(text) > max_len:
        cut = text[:max_len]
        for sep in (". ", "! ", "? ", " — ", " - "):
            idx = cut.rfind(sep)
            if idx > 60:
                cut = cut[: idx + 1]
                break
        text = cut.rstrip() + "…"
    return text


def parse_feed(xml_bytes: bytes, limit: int = 10) -> list[dict]:
    """Return a list of {guid, title, link} for the newest items."""
    items: list[dict] = []
    root = ET.fromstring(xml_bytes)
    # RSS 2.0: rss > channel > item
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        if not link:
            continue
        items.append({
            "guid": guid,
            "title": _clean_title(title),
            "link": link,
        })
        if len(items) >= limit:
            break
    return items


# ── Platform posters ──────────────────────────────────────────────────────────
def _http_post(url: str, data: bytes, headers: dict, timeout: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except urllib.error.URLError as e:
        return 0, str(e)


def post_telegram(text: str, token: str, channel: str) -> bool:
    """Send a message to a Telegram channel via the official Bot API."""
    import urllib.parse
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": channel,
        "text": text,
        "disable_web_page_preview": "false",
        "parse_mode": "HTML",
    }).encode("utf-8")
    status, body = _http_post(
        url, payload,
        {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT},
    )
    if status == 200:
        return True
    print(f"   ⚠️ Telegram HTTP {status}: {body}", file=sys.stderr)
    return False


def post_mastodon(text: str, base_url: str, access_token: str) -> bool:
    """Publish a status on Mastodon via the official REST API."""
    import urllib.parse
    url = f"{base_url.rstrip('/')}/api/v1/statuses"
    payload = urllib.parse.urlencode({"status": text}).encode("utf-8")
    status, body = _http_post(
        url, payload,
        {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": USER_AGENT,
        },
    )
    if status in (200, 201):
        return True
    print(f"   ⚠️ Mastodon HTTP {status}: {body}", file=sys.stderr)
    return False


# ── Message formatting ─────────────────────────────────────────────────────────
def build_message(item: dict, lang: str, platform: str) -> str:
    tags = HASHTAGS.get(lang, HASHTAGS["en"])
    title = item["title"]
    link = item["link"]
    if platform == "telegram":
        # HTML parse_mode: bold title + link on its own line
        safe = html.escape(title)
        return f"<b>{safe}</b>\n\n{link}\n\n{tags}"
    # Mastodon / plain
    return f"{title}\n\n{link}\n\n{tags}"


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Atlas News legitimate social auto-poster")
    ap.add_argument("--lang", choices=list(FEEDS), default="en",
                    help="Language feed to use (default: en)")
    ap.add_argument("--feed", default="", help="Explicit RSS feed URL (overrides --lang)")
    ap.add_argument("--max", type=int, default=3, help="Max items to post this run")
    ap.add_argument("--dry-run", action="store_true", help="Print only; do not post")
    args = ap.parse_args()

    feed_url = args.feed or FEEDS[args.lang]
    lang = args.lang

    print(f"📡 Fetching feed: {feed_url}")
    try:
        xml_bytes = _fetch(feed_url)
    except Exception as exc:
        print(f"❌ Could not fetch feed: {exc}", file=sys.stderr)
        return 1

    items = parse_feed(xml_bytes, limit=max(args.max * 3, 10))
    if not items:
        print("ℹ️ No items found in feed.")
        return 0

    posted = _load_state()
    new_items = [it for it in items if it["guid"] not in posted][: args.max]
    if not new_items:
        print("✅ Nothing new to post (all recent items already shared).")
        return 0

    # Which platforms are configured?
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chan = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    md_base = os.environ.get("MASTODON_BASE_URL", "").strip()
    md_tok = os.environ.get("MASTODON_ACCESS_TOKEN", "").strip()
    have_tg = bool(tg_token and tg_chan)
    have_md = bool(md_base and md_tok)

    if not (have_tg or have_md) and not args.dry_run:
        print("⚠️ No platform configured. Set TELEGRAM_* and/or MASTODON_* env vars,\n"
              "   or use --dry-run to preview messages.", file=sys.stderr)
        return 2

    targets = []
    if have_tg:
        targets.append("Telegram")
    if have_md:
        targets.append("Mastodon")
    mode = "DRY-RUN (no posting)" if args.dry_run else f"posting to: {', '.join(targets) or 'none'}"
    print(f"🚀 {len(new_items)} new item(s) — {mode}\n")

    ok = 0
    for i, item in enumerate(new_items, 1):
        print(f"[{i}/{len(new_items)}] {item['title'][:80]}")
        if args.dry_run:
            print("   ── preview ──")
            print("   " + build_message(item, lang, "mastodon").replace("\n", "\n   "))
            posted.add(item["guid"])
            ok += 1
            print()
            continue

        sent_any = False
        if have_tg:
            if post_telegram(build_message(item, lang, "telegram"), tg_token, tg_chan):
                print("   ✓ Telegram")
                sent_any = True
        if have_md:
            if post_mastodon(build_message(item, lang, "mastodon"), md_base, md_tok):
                print("   ✓ Mastodon")
                sent_any = True

        if sent_any:
            posted.add(item["guid"])
            ok += 1
        # Polite delay between articles to respect rate limits
        if i < len(new_items):
            time.sleep(POST_DELAY_SECONDS)
        print()

    if not args.dry_run:
        _save_state(posted)
    else:
        # In dry-run we still persist so a follow-up real run isn't a surprise?
        # No — keep dry-run side-effect-free. Do not save.
        pass

    print(f"✅ Done — {ok}/{len(new_items)} item(s) {'previewed' if args.dry_run else 'posted'} "
          f"at {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
