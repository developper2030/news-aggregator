import io
import logging
import os
import random
import re
import ssl
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.loader import load_config
from database.db import init_db, save_article, save_articles_batch, clean_old_articles

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("scraper")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en-US;q=0.7,en;q=0.3",
}

MIN_DELAY = 0.5
MAX_DELAY = 2.0
MAX_WORKERS = 4

# ── Retry settings ─────────────────────────────────────────────────────────
_RETRY_MAX   = 2   # extra attempts after first failure (3 total)
_RETRY_DELAY = 3   # base seconds between attempts (3 s -> 6 s)

# robots.txt results are cached per run: {origin: bool}
_robots_cache: dict[str, bool] = {}


def _is_retryable_exc(exc: Exception) -> bool:
    """Return True for transient network errors that are worth retrying.

    HTTP 4xx (client errors) are *not* retried — they won't improve.
    HTTP 5xx, DNS failures, connection resets and timeouts are retried.
    """
    import urllib.error as _ue
    import socket as _sock
    if isinstance(exc, _ue.HTTPError):
        return exc.code >= 500          # server-side errors only
    return isinstance(exc, (
        _ue.URLError,                   # wraps most urllib network errors
        TimeoutError,
        ConnectionError,
        OSError,
        _sock.timeout,
    ))

# Non-article URL path patterns
_NON_ARTICLE_PATTERNS = re.compile(
    r"(login|signin|signup|register|subscribe|account|profile|settings|"
    r"privacy|terms|contact|about|careers|jobs|advertise|"
    r"coupon|deal|offer|buy|shop|store|cart|checkout|"
    r"rss|feed|newsletter|alert|notification)",
    re.IGNORECASE,
)

# Navigation-like heading text
_NAV_HEADER_RE = re.compile(
    r"^(start reading|explore now|see rewards|view all|view |browse |"
    r"my account|sign up|read more|learn more|click here|"
    r"current issue|back to top|scroll to|go to|switch to)",
    re.IGNORECASE,
)

_CSS_OR_TEMPLATE_RE = re.compile(r"[{}<>()@:]")
_HTML_ENTITY_RE = re.compile(r"&[#\w]+;")

_SECTION_LABELS_AR = {
    "مباريات اليوم", "كل المسابقات", "آخر الأخبار", "أخبار الاقتصاد",
    "صفحة أخباري", "إعدادات المستخدم", "تسجيل الدخول", "اخترنا لكم",
    "حديث الصور", "زوارنا يتصفحون الآن", "أخبار أميركا",
    "كل البطولات", "جدول المباريات", "ترتيب الدوري",
}


def _is_junk_title(title: str) -> bool:
    title = title.strip()
    if len(title) < 15:
        return True
    if title in _SECTION_LABELS_AR:
        return True
    if "{{" in title or "}}" in title or "${" in title:
        return True
    if _CSS_OR_TEMPLATE_RE.search(title):
        return True
    entity_count = len(_HTML_ENTITY_RE.findall(title))
    if entity_count > 0 and entity_count / max(len(title), 1) > 0.3:
        return True
    if _NAV_HEADER_RE.search(title):
        return True
    if _NON_ARTICLE_PATTERNS.search(title):
        return True
    digits = sum(c.isdigit() for c in title)
    if digits / max(len(title), 1) > 0.5:
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# LANGUAGE DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def _is_correct_lang(title: str, expected_lang: str) -> bool:
    """Return True if *title* appears to be in *expected_lang*.

    Strategy:
    - Arabic (ar): Unicode ratio — fast and ~100% accurate.
    - Latin langs (en/fr/es/tr): reject if clearly Arabic, then use langdetect
      to catch remaining mismatches. Lenient on ambiguity → avoids false positives.
    - Titles < 12 chars or detection errors → always pass (fail open).
    """
    if not expected_lang or not title:
        return True

    text = title.strip()
    if len(text) < 12:
        return True  # Too short to detect reliably — let it pass

    # Count Arabic-script characters (Arabic, Persian, Urdu share this block)
    alpha_chars  = sum(1 for c in text if c.isalpha())
    if alpha_chars == 0:
        return True

    arabic_chars = sum(1 for c in text if "؀" <= c <= "ۿ")
    arabic_ratio = arabic_chars / alpha_chars

    # ── Arabic feed: title must be mostly Arabic ───────────────────────────────
    if expected_lang == "ar":
        return arabic_ratio >= 0.30

    # ── Latin feed (en/fr/es/tr): reject clearly Arabic titles ────────────────
    if arabic_ratio >= 0.30:
        return False

    # Use langdetect for Latin-to-Latin contamination detection
    # Accept languages that are closely related to avoid false positives
    _LATIN_ACCEPT: dict[str, set] = {
        "en": {"en"},
        "fr": {"fr"},
        "es": {"es", "ca", "pt", "gl"},  # Catalan/Portuguese/Galician are close
        "tr": {"tr"},
    }
    try:
        from langdetect import detect
        detected = detect(text)
        if detected == "ar":
            return False
        accepted = _LATIN_ACCEPT.get(expected_lang)
        if accepted and detected not in accepted:
            return False
        return True
    except Exception:
        return True  # Can't detect → pass (fail open)


def _element_in_excluded_area(el, exclude_classes: list, exclude_id_patterns: list) -> bool:
    for parent in el.parents:
        if parent is None:
            continue
        css_classes = parent.get("class") or []
        for cls in css_classes:
            if cls.lower() in exclude_classes:
                return True
        parent_id = (parent.get("id") or "").lower()
        for pat in exclude_id_patterns:
            if pat in parent_id:
                return True
    return False


def can_fetch(url: str) -> bool:
    """Check robots.txt, with per-run in-memory caching."""
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    if origin in _robots_cache:
        return _robots_cache[origin]

    try:
        robots_url = f"{origin}/robots.txt"
        ctx = ssl.create_default_context()
        req = Request(robots_url, headers=HEADERS)
        resp = urlopen(req, timeout=10, context=ctx)
        raw = resp.read().decode("utf-8", errors="replace")

        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(raw.splitlines())

        if rp.can_fetch("*", url):
            _robots_cache[origin] = True
            return True

        # Fallback: manually check Disallow rules for * agent
        path = parsed.path or "/"
        agent = None
        for line in raw.splitlines():
            line = line.split("#")[0].strip()
            if not line:
                continue
            low = line.lower()
            if low.startswith("user-agent"):
                agent = line.split(":", 1)[1].strip()
                continue
            if agent == "*" and low.startswith("disallow"):
                rule = line.split(":", 1)[1].strip()
                if rule and path.startswith(rule):
                    logger.warning("Blocked by robots.txt: %s", url)
                    _robots_cache[origin] = False
                    return False

        _robots_cache[origin] = True
        return True

    except Exception:
        # Network error fetching robots.txt — allow by default
        _robots_cache[origin] = True
        return True


def _encode_url(url: str) -> str:
    """Percent-encode non-ASCII characters in a URL while preserving structure."""
    parts = urlsplit(url)
    # encode path and query only — scheme/netloc must stay ASCII
    encoded = parts._replace(
        path=quote(parts.path, safe="/:@!$&'()*+,;="),
        query=quote(parts.query, safe="=&+%"),
    )
    return urlunsplit(encoded)


def fetch_html(url: str, timeout: int = 20) -> str:
    ctx = ssl.create_default_context()
    req = Request(_encode_url(url), headers=HEADERS)
    resp = urlopen(req, timeout=timeout, context=ctx)
    charset = resp.headers.get_content_charset() or "utf-8"
    return resp.read().decode(charset, errors="replace")


def fetch_html_browser(url: str, timeout: int = 30) -> str:
    """Fetch via a real Chromium browser to bypass Cloudflare / JS-heavy sites."""
    if not _PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("playwright not installed — run: pip install playwright && playwright install chromium")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="ar",
                extra_http_headers={"Accept-Language": "ar,en-US;q=0.7,en;q=0.3"},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(2000)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        if "Executable doesn't exist" in str(e) or "chromium" in str(e).lower():
            raise RuntimeError("Chromium not installed — run: python -m playwright install chromium") from e
        raise


def _process_link(
    href, title, source_url, seen_urls,
    exclude_classes, exclude_id_patterns, min_title_length,
) -> bool:
    if not title or not href:
        return False
    if href.startswith("#") or href.startswith("javascript:"):
        return False
    if len(title) < min_title_length:
        return False
    if _is_junk_title(title):
        return False
    full_url = urljoin(source_url, href)
    if full_url in seen_urls:
        return False
    if _NON_ARTICLE_PATTERNS.search(urlparse(full_url).path):
        return False
    seen_urls.add(full_url)
    return True


def _find_image(container, source_url: str) -> str:
    """Extract the best image URL from a container element."""
    for img in container.find_all("img", limit=5):
        src = (
            img.get("data-src")
            or img.get("data-original")
            or img.get("data-lazy-src")
            or img.get("src")
            or ""
        )
        src = src.strip()
        if not src or src.startswith("data:") or "spacer" in src or "blank" in src:
            continue
        if "logo" in src.lower() or "icon" in src.lower() or "avatar" in src.lower():
            continue
        return urljoin(source_url, src)
    return ""


def _find_og_image(soup, source_url: str) -> str:
    """Get og:image from page meta as fallback."""
    tag = soup.find("meta", property="og:image")
    if tag and tag.get("content", "").strip():
        return urljoin(source_url, tag["content"].strip())
    return ""


def extract_articles_bs4(
    html: str, source_url: str, source_name: str, max_articles: int, selectors: dict | None = None
) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    articles: list[dict] = []
    seen_urls: set = set()
    og_image = _find_og_image(soup, source_url)

    if selectors is None:
        selectors = {}

    article_selector  = selectors.get("article_selector", "")
    heading_tags      = selectors.get("heading_tags", ["h1", "h2", "h3", "h4"])
    exclude_classes   = [c.lower() for c in selectors.get("exclude_classes", [])]
    exclude_id_pats   = [p.lower() for p in selectors.get("exclude_id_patterns", [])]
    min_title_length  = selectors.get("min_title_length", 12)

    # Strategy 1: scoped article containers
    if article_selector:
        try:
            containers = soup.select(article_selector)
        except Exception:
            containers = []

        for container in containers:
            for tag in heading_tags:
                for heading in container.find_all(tag):
                    a = heading.find("a") or heading
                    href  = a.get("href")
                    title = heading.get_text(strip=True)
                    if _process_link(href, title, source_url, seen_urls, exclude_classes, exclude_id_pats, min_title_length):
                        image = _find_image(container, source_url) or og_image
                        articles.append({"title": title[:300], "url": urljoin(source_url, href), "source": source_name, "image_url": image})
                        if len(articles) >= max_articles:
                            return articles

    # Strategy 2: heading links across the whole page
    heading_selectors = [f"{t} a" for t in heading_tags] + heading_tags
    for sel in heading_selectors:
        for el in soup.select(sel):
            if _element_in_excluded_area(el, exclude_classes, exclude_id_pats):
                continue
            a_tag = el.find("a") if el.name != "a" else el
            if a_tag is None:
                continue
            href  = a_tag.get("href")
            title = (el.get_text(strip=True) if el.name != "a" else a_tag.get_text(strip=True))
            if _process_link(href, title, source_url, seen_urls, exclude_classes, exclude_id_pats, min_title_length):
                parent = el.find_parent("article") or el.find_parent("div")
                image = _find_image(parent, source_url) if parent else og_image
                articles.append({"title": title[:300], "url": urljoin(source_url, href), "source": source_name, "image_url": image or og_image})
                if len(articles) >= max_articles:
                    return articles

    return articles


def extract_articles_fallback(html: str, source_url: str, source_name: str, max_articles: int) -> list[dict]:
    """Broad fallback: scan every link with heavy filtering."""
    soup = BeautifulSoup(html, "lxml")
    articles: list[dict] = []
    seen_urls: set = set()
    og_image = _find_og_image(soup, source_url)

    for a in soup.find_all("a", href=True):
        href  = a["href"]
        title = a.get_text(strip=True)
        if not title or not href:
            continue
        if href.startswith("#") or href.startswith("javascript:"):
            continue
        if len(title) < 20 or _is_junk_title(title):
            continue
        full_url = urljoin(source_url, href)
        if full_url in seen_urls:
            continue
        if _NON_ARTICLE_PATTERNS.search(urlparse(full_url).path):
            continue
        seen_urls.add(full_url)
        parent = a.find_parent("article") or a.find_parent("div")
        image = _find_image(parent, source_url) if parent else og_image
        articles.append({"title": title[:300], "url": full_url, "source": source_name, "image_url": image or og_image})
        if len(articles) >= max_articles:
            break

    return articles


def _is_yt_feed_url(url: str) -> bool:
    """Return True if *url* is a YouTube channel/playlist RSS feed."""
    return "youtube.com/feeds/videos.xml" in url


def _is_rss_feed_url(url: str) -> bool:
    """Return True if *url* looks like a generic RSS/Atom feed (non-YouTube)."""
    if "youtube.com/feeds" in url:
        return False
    low = url.lower()
    return any(x in low for x in (
        "feeds.feedburner.com", "feeds.bbci.co.uk",
        "/feed/", "/rss/", ".rss",
        "/rss", "?format=rss", "?type=rss",
        "sondakika.rss",
    ))


def _clean_rss_desc(raw: str, title: str = "") -> str:
    """Strip HTML tags, decode entities, truncate to ≤2 sentences (max 280 chars).

    Returns empty string if the description is too short or just repeats the title.
    """
    import re as _re, html as _html
    if not raw or len(raw.strip()) < 20:
        return ""
    # Decode HTML entities (&amp; &lt; &nbsp; …)
    text = _html.unescape(raw)
    # Strip HTML tags
    text = _re.sub(r"<[^>]+>", " ", text)
    # Collapse whitespace
    text = " ".join(text.split())
    if len(text) < 30:
        return ""
    # If description just repeats the title, strip the duplicated prefix
    if title:
        t_lower = title.lower().strip()[:60]
        if text.lower().startswith(t_lower):
            text = text[len(t_lower):].lstrip(" .—–-")
    if len(text) < 30:
        return ""
    # Truncate to 2 sentences
    sentence_ends: list[int] = []
    for m in _re.finditer(r"[.!?][\s\"')\]]+", text):
        sentence_ends.append(m.end())
        if len(sentence_ends) >= 2:
            break
    if len(sentence_ends) >= 2:
        text = text[:sentence_ends[1]].strip()
    elif len(text) > 280:
        cut = text.rfind(" ", 0, 280)
        text = text[:cut if cut > 80 else 280] + "…"
    return text[:300]


def extract_articles_rss(feed_text: str, source_name: str, max_articles: int) -> list[dict]:
    """Parse a generic RSS 2.0 or Atom feed and return article dicts."""
    import xml.etree.ElementTree as ET
    NS_MEDIA   = "http://search.yahoo.com/mrss/"
    NS_ATOM    = "http://www.w3.org/2005/Atom"
    NS_CONTENT = "http://purl.org/rss/1.0/modules/content/"
    NS_DC      = "http://purl.org/dc/elements/1.1/"
    articles: list[dict] = []
    try:
        root = ET.fromstring(feed_text)
        # ── Atom ────────────────────────────────────────────────────────────
        if NS_ATOM in root.tag or root.tag.lower() == "feed":
            for entry in (root.findall(f"{{{NS_ATOM}}}entry") or root.findall("entry"))[:max_articles]:
                def _a(el, n): return el.find(f"{{{NS_ATOM}}}{n}") or el.find(n)
                t = _a(entry, "title")
                l = entry.find(f"{{{NS_ATOM}}}link[@rel='alternate']") or _a(entry, "link")
                m = entry.find(f"{{{NS_MEDIA}}}thumbnail")
                s = _a(entry, "summary") or _a(entry, "content")
                title = (t.text or "").strip() if t is not None else ""
                href  = (l.get("href") or l.text or "").strip() if l is not None else ""
                image = m.get("url", "") if m is not None else ""
                desc  = _clean_rss_desc((s.text or ""), title) if s is not None else ""
                if title and href and len(title) >= 5:
                    articles.append({"title": title[:300], "url": href,
                                     "source": source_name, "image_url": image,
                                     "ai_summary": desc})
        # ── RSS 2.0 ─────────────────────────────────────────────────────────
        else:
            channel = root.find("channel") or root
            for item in channel.findall("item")[:max_articles]:
                t   = item.find("title")
                l   = item.find("link")
                enc = item.find("enclosure")
                m   = item.find(f"{{{NS_MEDIA}}}thumbnail") or item.find(f"{{{NS_MEDIA}}}content")
                d   = item.find("description")
                ce  = item.find(f"{{{NS_CONTENT}}}encoded")
                title = (t.text or "").strip() if t is not None else ""
                href  = (l.text or "").strip() if l is not None else ""
                image = ""
                if enc is not None and (enc.get("type", "")).startswith("image"):
                    image = enc.get("url", "")
                if not image and m is not None:
                    image = m.get("url", "")
                # Prefer <description>, fall back to <content:encoded> (first 500 chars)
                raw_desc = ""
                if d is not None and d.text:
                    raw_desc = d.text
                elif ce is not None and ce.text:
                    raw_desc = ce.text[:500]
                desc = _clean_rss_desc(raw_desc, title)
                if title and href and len(title) >= 5:
                    articles.append({"title": title[:300], "url": href,
                                     "source": source_name, "image_url": image,
                                     "ai_summary": desc})
    except ET.ParseError as exc:
        logger.warning("RSS feed XML parse error (%s): %s", source_name, exc)
    return articles


def extract_articles_yt_feed(feed_text: str, source_name: str, max_articles: int) -> list[dict]:
    """Parse a YouTube Atom RSS feed and return article dicts with thumbnails.

    YouTube feed format (Atom):
      <entry>
        <yt:videoId>ID</yt:videoId>
        <title>Title</title>
        <link rel="alternate" href="https://www.youtube.com/watch?v=ID"/>
        <media:group>
          <media:thumbnail url="https://i.ytimg.com/vi/ID/mqdefault.jpg" …/>
        </media:group>
      </entry>
    """
    import xml.etree.ElementTree as ET  # stdlib — always available
    NS = {
        "a":     "http://www.w3.org/2005/Atom",
        "yt":    "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    articles: list[dict] = []
    try:
        root = ET.fromstring(feed_text)
        for entry in root.findall("a:entry", NS)[:max_articles]:
            title_el = entry.find("a:title", NS)
            link_el  = entry.find("a:link[@rel='alternate']", NS)
            vid_el   = entry.find("yt:videoId", NS)
            thumb_el = entry.find("media:group/media:thumbnail", NS)

            title = (title_el.text or "").strip() if title_el is not None else ""
            href  = (link_el.get("href") or "") if link_el is not None else ""
            vid   = (vid_el.text or "").strip() if vid_el is not None else ""

            if thumb_el is not None:
                image = thumb_el.get("url", "")
            elif vid:
                image = f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
            else:
                image = ""

            if title and href and len(title) >= 5:
                articles.append({
                    "title":     title[:300],
                    "url":       href,
                    "source":    source_name,
                    "image_url": image,
                })
    except ET.ParseError as exc:
        logger.warning("YT feed XML parse error (%s): %s", source_name, exc)
    return articles


# ── RSS auto-discovery ─────────────────────────────────────────────────────
_RSS_FEED_PATHS = (
    "/feed", "/feed.xml", "/rss", "/rss.xml", "/rss/news",
    "/atom.xml", "/feed/atom", "/index.xml",
    "/en/rss", "/ar/rss", "/fr/rss", "/es/rss", "/tr/rss",
    "/news/rss", "/news/feed", "/feeds/posts/default",   # Blogger
)


def _discover_rss(base_url: str) -> str | None:
    """Auto-discover an RSS/Atom feed for the site at *base_url*.

    Strategy:
      1. Fetch the page and scan <link rel="alternate" type="application/rss+xml"> tags.
      2. Probe the most common feed paths.

    Returns the first working feed URL, or None if nothing is found.
    """
    parsed   = urlparse(base_url)
    origin   = f"{parsed.scheme}://{parsed.netloc}"
    candidates: list[str] = []

    # ── Try declared feed links from page HTML ──────────────────────────────
    try:
        html = fetch_html(base_url)
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all("link"):
            rel  = tag.get("rel") or []
            mime = tag.get("type", "")
            if "alternate" not in rel:
                continue
            if "rss" not in mime and "atom" not in mime:
                continue
            href = (tag.get("href") or "").strip()
            if not href:
                continue
            if href.startswith("//"):
                href = f"{parsed.scheme}:{href}"
            elif href.startswith("/"):
                href = origin + href
            elif not href.startswith("http"):
                href = f"{origin}/{href}"
            candidates.append(href)
    except Exception:
        pass  # page unreachable; fall through to common-path probing

    # ── Probe common feed paths ─────────────────────────────────────────────
    for path in _RSS_FEED_PATHS:
        candidates.append(origin + path)

    seen: set[str] = set()
    for feed_url in candidates:
        if feed_url in seen:
            continue
        seen.add(feed_url)
        try:
            content = fetch_html(feed_url)
            snippet = content.lstrip()[:300]
            if "<rss" in snippet or "<feed" in snippet or "<atom:feed" in snippet:
                logger.info("RSS auto-discovered: %s -> %s", base_url, feed_url)
                return feed_url
        except Exception:
            continue

    return None


def scrape_source(source: dict, category_name: str, category_slug: str, max_articles: int) -> list[dict]:
    """Scrape one source. Called from a thread pool — adds a small random delay.

    Transient network errors (5xx, timeouts, connection resets) are retried up to
    _RETRY_MAX extra times with linear back-off (_RETRY_DELAY * attempt seconds).
    Non-retryable errors (4xx, parse errors, robots.txt block) give up immediately.
    """
    articles: list[dict] = []
    url         = source.get("url", "")
    selectors   = source.get("selectors")
    use_browser = source.get("use_browser", False)
    src_name    = source.get("name", url)
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    for attempt in range(_RETRY_MAX + 1):
        # ── Wait before each retry (not before the first attempt) ──────────
        if attempt:
            wait = _RETRY_DELAY * attempt
            logger.warning(
                "Retrying %s (attempt %d/%d) in %ds...", src_name, attempt, _RETRY_MAX, wait
            )
            time.sleep(wait)

        try:
            # ── YouTube RSS feeds — parse as Atom XML, no robots.txt check ──
            if _is_yt_feed_url(url):
                logger.info("Fetching YT feed %s (%s)...", src_name, url)
                xml_text = fetch_html(url)
                articles = extract_articles_yt_feed(xml_text, src_name, max_articles)
                logger.info("-> %d videos from %s", len(articles), src_name)
                return articles

            # ── Generic RSS / Atom feeds ────────────────────────────────────
            if _is_rss_feed_url(url):
                logger.info("Fetching RSS feed %s (%s)...", src_name, url)
                xml_text = fetch_html(url)
                articles = extract_articles_rss(xml_text, src_name, max_articles)
                logger.info("-> %d articles from %s", len(articles), src_name)
                return articles

            if not can_fetch(url):
                # ── Step 1: auto-discover an RSS feed (not subject to robots.txt) ──
                rss_url = _discover_rss(url)
                if rss_url:
                    logger.info(
                        "Robots.txt blocked %s — using auto-discovered feed: %s",
                        src_name, rss_url,
                    )
                    try:
                        xml_text = fetch_html(rss_url)
                        articles = extract_articles_rss(xml_text, src_name, max_articles)
                        logger.info("-> %d articles from %s (auto-RSS)", len(articles), src_name)
                        return articles
                    except Exception as exc:
                        logger.warning("Auto-RSS fetch failed for %s: %s", src_name, exc)

                # ── Step 2: honour ignore_robots override in source config ──────
                if not source.get("ignore_robots", False):
                    logger.info("Skipping %s (disallowed by robots.txt)", src_name)
                    return articles
                logger.info(
                    "Bypassing robots.txt for %s (ignore_robots=true in config)", src_name
                )
                # fall through to normal HTML scraping

            logger.info("Fetching %s (%s)...", src_name, url)
            if use_browser:
                if not _PLAYWRIGHT_AVAILABLE:
                    logger.error("FAILED %s: playwright not installed", src_name)
                    return articles
                logger.info("Using browser for %s", src_name)
                html = fetch_html_browser(url)
            else:
                html = fetch_html(url)
            logger.debug("Got %d bytes from %s", len(html), src_name)

            articles = extract_articles_bs4(html, url, src_name, max_articles, selectors)

            if not articles:
                logger.info("No articles via selectors — trying fallback for %s", src_name)
                articles = extract_articles_fallback(html, url, src_name, max_articles)

            logger.info("-> %d articles from %s", len(articles), src_name)
            return articles  # ← success, exit retry loop

        except Exception as exc:
            if _is_retryable_exc(exc):
                if attempt < _RETRY_MAX:
                    logger.warning("TRANSIENT ERROR %s: %s", src_name, exc)
                    continue          # will retry
                # All attempts exhausted
                logger.error(
                    "FAILED %s after %d attempt(s): %s", src_name, _RETRY_MAX + 1, exc
                )
            else:
                # Non-retryable (4xx, parse error, etc.) — log and give up
                logger.error("FAILED %s: %s", src_name, exc)
                break

    return articles


def run(config_path: str | None = None, db_path: str | None = None) -> None:
    import json
    from database.db import set_db_path

    if config_path:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = load_config()

    if db_path:
        set_db_path(db_path)

    settings      = config.get("settings", {})
    max_per       = int(settings.get("max_articles_per_source", 10))
    keep_days     = int(settings.get("oldest_days", 7))
    expected_lang = settings.get("lang_code", "")  # e.g. "ar", "en", "fr", "es", "tr"

    if expected_lang:
        logger.info("Language filter active: expected_lang='%s'", expected_lang)

    init_db()
    _robots_cache.clear()  # fresh cache for this run

    # Build task list
    all_tasks: list[tuple] = []
    for category in config["categories"]:
        for source in category["sources"]:
            all_tasks.append((source, category["name"], category["slug"], max_per))

    all_articles: list[dict] = []
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {
            executor.submit(scrape_source, src, cname, cslug, max_a): (src, cname, cslug)
            for src, cname, cslug, max_a in all_tasks
        }
        for future in as_completed(future_map):
            src, cname, cslug = future_map[future]
            completed += 1
            try:
                arts = future.result()
            except Exception as exc:
                logger.error("!! %s threw: %s", src["name"], exc)
                arts = []

            # Language filter — reject articles not matching expected_lang
            if expected_lang:
                filtered = [a for a in arts if _is_correct_lang(a["title"], expected_lang)]
                rejected = len(arts) - len(filtered)
                if rejected:
                    logger.info(
                        "Lang filter [%s]: removed %d/%d wrong-lang articles from %s",
                        expected_lang, rejected, len(arts), src["name"],
                    )
            else:
                filtered = arts

            # Batch insert for efficiency
            batch = [
                {
                    "title":         a["title"],
                    "url":           a["url"],
                    "image_url":     a.get("image_url", ""),
                    "source":        a["source"],
                    "category_name": cname,
                    "category_slug": cslug,
                    "ai_summary":    a.get("ai_summary", ""),
                }
                for a in filtered
            ]
            save_articles_batch(batch)
            all_articles.extend(filtered)

    print(f"\n{'=' * 50}")
    print("Summary by source:")
    for src, cnt in Counter(a["source"] for a in all_articles).most_common():
        print(f"  {src}: {cnt}")
    print(f"Total: {len(all_articles)} articles from {completed} sources")

    removed = clean_old_articles(days=keep_days * 4)
    if removed:
        logger.info("Cleaned %d old articles (older than %d days)", removed, keep_days * 4)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="News scraper")
    parser.add_argument("--config", default=None, help="Path to sources JSON config (default: config/sources.json)")
    parser.add_argument("--db", default=None, help="Path to SQLite database (default: data/news.db)")
    args = parser.parse_args()
    run(config_path=args.config, db_path=args.db)
