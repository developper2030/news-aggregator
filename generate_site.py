import html as _html_lib
import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.loader import load_config
from database.db import get_articles_by_category, init_db as _init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("generator")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# ──────────────────────────────────────────────────────────────────────────────
# LANGUAGE ISOLATION GUARD
# Each config file declares lang_code in its settings block.
# This guard logs a WARNING if the generator lang argument doesn't match
# the config's declared lang_code — preventing cross-language contamination.
# ──────────────────────────────────────────────────────────────────────────────
def _check_lang_isolation(config: dict, requested_lang: str) -> None:
    """Warn if config lang_code doesn't match the requested generation language."""
    declared = config.get("settings", {}).get("lang_code", "")
    if declared and declared != requested_lang:
        logger.warning(
            "LANG ISOLATION: config declares lang_code='%s' but generator "
            "was called with lang='%s'. Check your config assignment in run.py.",
            declared, requested_lang,
        )

# Category colour palette — used for card top-bar and section borders
CATEGORY_COLORS: dict[str, str] = {
    "politics":  "#6366f1",
    "economy":   "#059669",
    "tech":      "#0ea5e9",
    "sports":    "#f59e0b",
    "health":    "#10b981",
    "society":   "#7c3aed",
    "education": "#0d9488",
    "arts":      "#db2777",
    "morocco":   "#ef4444",
    "islamic":   "#0d9488",
    "diaspora":  "#be185d",
    "middleeast":"#f97316",
    "asia":      "#06b6d4",
    "americas":  "#3b82f6",
    "europe":    "#8b5cf6",
    "africa":      "#16a34a",
    # New universal categories
    "environment": "#15803d",
    "business":    "#1d4ed8",
    "travel":      "#ea580c",
    # Media (vid-*) thematic categories
    "vid-news":          "#e11d48",
    "vid-business":      "#0369a1",
    "vid-science":       "#7c3aed",
    "vid-sports":        "#ea580c",
    "vid-politics":      "#4338ca",
    "vid-cooking":       "#d97706",
    "vid-entertainment": "#db2777",
}
CATEGORY_GRADIENTS: dict[str, str] = {
    "politics":  "linear-gradient(135deg, #6366f1, #8b5cf6)",
    "economy":   "linear-gradient(135deg, #059669, #34d399)",
    "tech":      "linear-gradient(135deg, #0ea5e9, #38bdf8)",
    "sports":    "linear-gradient(135deg, #f59e0b, #fbbf24)",
    "health":    "linear-gradient(135deg, #10b981, #6ee7b7)",
    "society":   "linear-gradient(135deg, #7c3aed, #a78bfa)",
    "education": "linear-gradient(135deg, #0d9488, #2dd4bf)",
    "arts":      "linear-gradient(135deg, #db2777, #f472b6)",
    "morocco":   "linear-gradient(135deg, #ef4444, #f87171)",
    "islamic":   "linear-gradient(135deg, #0d9488, #2dd4bf)",
    "diaspora":  "linear-gradient(135deg, #be185d, #ec4899)",
    "middleeast":"linear-gradient(135deg, #f97316, #fb923c)",
    "asia":      "linear-gradient(135deg, #06b6d4, #67e8f9)",
    "americas":  "linear-gradient(135deg, #3b82f6, #93c5fd)",
    "europe":    "linear-gradient(135deg, #8b5cf6, #c4b5fd)",
    "africa":      "linear-gradient(135deg, #16a34a, #4ade80)",
    # New universal categories
    "environment": "linear-gradient(135deg, #15803d, #4ade80)",
    "business":    "linear-gradient(135deg, #1d4ed8, #60a5fa)",
    "travel":      "linear-gradient(135deg, #ea580c, #fb923c)",
    # Media (vid-*) thematic categories
    "vid-news":          "linear-gradient(135deg, #e11d48, #fb7185)",
    "vid-business":      "linear-gradient(135deg, #0369a1, #38bdf8)",
    "vid-science":       "linear-gradient(135deg, #7c3aed, #a78bfa)",
    "vid-sports":        "linear-gradient(135deg, #ea580c, #fb923c)",
    "vid-politics":      "linear-gradient(135deg, #4338ca, #818cf8)",
    "vid-cooking":       "linear-gradient(135deg, #d97706, #fbbf24)",
    "vid-entertainment": "linear-gradient(135deg, #db2777, #f472b6)",
}

# Slugs treated as world-regions (shown in world subnav, hidden from main nav & home sections)
REGION_SLUGS: set[str] = {"morocco", "islamic", "diaspora", "middleeast", "asia", "americas", "europe", "africa"}

# Slugs treated as media-regions (shown in media subnav, hidden from main nav & home sections)
MEDIA_SLUGS: set[str] = {
    "vid-news", "vid-business", "vid-science",
    "vid-sports", "vid-politics", "vid-cooking", "vid-entertainment"
}


def _is_yt_url(url: str) -> bool:
    """Return True if *url* is a YouTube watch or short link.

    Used to filter vid-* sections so only real video entries (not article
    links accidentally stored under a vid-* category) are displayed.
    """
    return "youtube.com/watch" in url or "youtu.be/" in url


# Slugs that are economy sub-sections (hidden from main nav & home — accessible only via economy strip)
ECON_SUB_SLUGS: set[str] = {"business", "travel"}

# Ordered world-region display data
WORLD_REGIONS = [
    {"slug": "morocco",    "name": "المغرب وشمال أفريقيا", "icon": "🇲🇦"},
    {"slug": "islamic",    "name": "العالم الإسلامي",       "icon": "☪️"},
    {"slug": "diaspora",   "name": "شؤون المهاجرين",        "icon": "👥"},
    {"slug": "middleeast", "name": "الشرق الأوسط",         "icon": "🕌"},
    {"slug": "asia",       "name": "آسيا",                  "icon": "🌏"},
    {"slug": "americas",   "name": "الأمريكتين",            "icon": "🌎"},
    {"slug": "europe",     "name": "أوروبا",                "icon": "🏰"},
    {"slug": "africa",     "name": "أفريقيا",               "icon": "🌍"},
]

# Ordered media-region display data (صوت وصورة) — thematic video categories
MEDIA_REGIONS = [
    {"slug": "vid-news",          "name": "أحداث",             "icon": "📰"},
    {"slug": "vid-business",      "name": "مال وأعمال",         "icon": "💼"},
    {"slug": "vid-science",       "name": "علوم وتكنولوجيا",   "icon": "🔬"},
    {"slug": "vid-sports",        "name": "رياضة",             "icon": "⚽"},
    {"slug": "vid-politics",      "name": "تحليلات سياسية",     "icon": "🎙️"},
    {"slug": "vid-cooking",       "name": "مطبخ",               "icon": "🍳"},
    {"slug": "vid-entertainment", "name": "ترفيه",             "icon": "🎬"},
]

# Live TV channels per language — YouTube channel live-stream links
LIVE_CHANNELS: dict[str, list[dict]] = {
    "ar": [
        {"name": "الجزيرة مباشر",   "flag": "🇶🇦", "url": "https://www.youtube.com/@AlJazeeraArabic/live"},
        {"name": "BBC عربي",         "flag": "🇬🇧", "url": "https://www.youtube.com/@BBCArabic/live"},
        {"name": "العربية",          "flag": "🇸🇦", "url": "https://www.youtube.com/@AlArabiya/live"},
        {"name": "سكاي نيوز عربية", "flag": "🇦🇪", "url": "https://www.youtube.com/@skynewsarabia/live"},
        {"name": "France 24 عربي",   "flag": "🇫🇷", "url": "https://www.youtube.com/@France24Arabic/live"},
        {"name": "RT عربي",          "flag": "🇷🇺", "url": "https://www.youtube.com/@RTArabic/live"},
        {"name": "الميادين",         "flag": "🇱🇧", "url": "https://www.youtube.com/@AlMayadeenNews/live"},
        {"name": "الحرة",            "flag": "🇺🇸", "url": "https://www.youtube.com/@Alhurra/live"},
    ],
    "en": [
        {"name": "Al Jazeera",      "flag": "🇶🇦", "url": "https://www.youtube.com/@AlJazeeraEnglish/live"},
        {"name": "BBC News",        "flag": "🇬🇧", "url": "https://www.youtube.com/@BBCNews/live"},
        {"name": "France 24",       "flag": "🇫🇷", "url": "https://www.youtube.com/@France24English/live"},
        {"name": "DW News",         "flag": "🇩🇪", "url": "https://www.youtube.com/@dwnews/live"},
        {"name": "Sky News",        "flag": "🇬🇧", "url": "https://www.youtube.com/@SkyNews/live"},
        {"name": "Euronews",        "flag": "🇪🇺", "url": "https://www.youtube.com/@euronews/live"},
        {"name": "RT",              "flag": "🇷🇺", "url": "https://www.youtube.com/@RT/live"},
        {"name": "DW Arabic",       "flag": "🇩🇪", "url": "https://www.youtube.com/@dwarabia/live"},
    ],
    "fr": [
        {"name": "France 24",       "flag": "🇫🇷", "url": "https://www.youtube.com/@France24/live"},
        {"name": "BFM TV",          "flag": "🇫🇷", "url": "https://www.youtube.com/@bfmtv/live"},
        {"name": "LCI",             "flag": "🇫🇷", "url": "https://www.youtube.com/@LCI/live"},
        {"name": "Euronews FR",     "flag": "🇪🇺", "url": "https://www.youtube.com/@euronewsfrancais/live"},
        {"name": "RFI",             "flag": "🇫🇷", "url": "https://www.youtube.com/@RFI_Officiel/live"},
        {"name": "Al Jazeera AR",   "flag": "🇶🇦", "url": "https://www.youtube.com/@AlJazeeraArabic/live"},
        {"name": "DW Français",     "flag": "🇩🇪", "url": "https://www.youtube.com/@dwfrancais/live"},
    ],
    "es": [
        {"name": "DW Español",      "flag": "🇩🇪", "url": "https://www.youtube.com/@dw_espanol/live"},
        {"name": "RTVE Noticias",   "flag": "🇪🇸", "url": "https://www.youtube.com/@rtvenoticias/live"},
        {"name": "CNN en Español",  "flag": "🇺🇸", "url": "https://www.youtube.com/@CNNenEspanol/live"},
        {"name": "France 24 ES",    "flag": "🇫🇷", "url": "https://www.youtube.com/@France24espanol/live"},
        {"name": "Euronews ES",     "flag": "🇪🇺", "url": "https://www.youtube.com/@euronewses/live"},
        {"name": "Al Jazeera",      "flag": "🇶🇦", "url": "https://www.youtube.com/@AlJazeeraEnglish/live"},
        {"name": "TeleSUR",         "flag": "🌎", "url": "https://www.youtube.com/@teleSURtv/live"},
    ],
    "tr": [
        {"name": "TRT Haber",       "flag": "🇹🇷", "url": "https://www.youtube.com/@trthaber/live"},
        {"name": "NTV",             "flag": "🇹🇷", "url": "https://www.youtube.com/@ntvturkiye/live"},
        {"name": "CNN Türk",        "flag": "🇹🇷", "url": "https://www.youtube.com/@cnnturk/live"},
        {"name": "A Haber",         "flag": "🇹🇷", "url": "https://www.youtube.com/@ahaber/live"},
        {"name": "Euronews TR",     "flag": "🇪🇺", "url": "https://www.youtube.com/@euronewsturkce/live"},
        {"name": "DW Türkçe",       "flag": "🇩🇪", "url": "https://www.youtube.com/@dwturkce/live"},
        {"name": "Al Jazeera",      "flag": "🇶🇦", "url": "https://www.youtube.com/@AlJazeeraEnglish/live"},
    ],
}

DEFAULT_COLOR = "#6366f1"
DEFAULT_GRADIENT = "linear-gradient(135deg, #6366f1, #8b5cf6)"

# Path to keyword blacklist managed by the admin panel
BLACKLIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "blacklist.json")

# Currency metadata: code → multilingual dict with flag
CURRENCY_META: dict[str, dict] = {
    "MAD": {"ar": "الدرهم المغربي",    "en": "Moroccan Dirham",    "fr": "Dirham marocain",      "es": "Dírham marroquí",    "tr": "Fas Dirhemi",          "flag": "🇲🇦"},
    "DZD": {"ar": "الدينار الجزائري",  "en": "Algerian Dinar",     "fr": "Dinar algérien",       "es": "Dinar argelino",     "tr": "Cezayir Dinarı",       "flag": "🇩🇿"},
    "TND": {"ar": "الدينار التونسي",   "en": "Tunisian Dinar",     "fr": "Dinar tunisien",       "es": "Dinar tunecino",     "tr": "Tunus Dinarı",         "flag": "🇹🇳"},
    "EGP": {"ar": "الجنيه المصري",     "en": "Egyptian Pound",     "fr": "Livre égyptienne",     "es": "Libra egipcia",      "tr": "Mısır Poundu",         "flag": "🇪🇬"},
    "SAR": {"ar": "الريال السعودي",    "en": "Saudi Riyal",        "fr": "Riyal saoudien",       "es": "Riyal saudí",        "tr": "Suudi Riyali",         "flag": "🇸🇦"},
    "AED": {"ar": "الدرهم الإماراتي",  "en": "UAE Dirham",         "fr": "Dirham des EAU",       "es": "Dírham de EAU",      "tr": "BAE Dirhemi",          "flag": "🇦🇪"},
    "KWD": {"ar": "الدينار الكويتي",   "en": "Kuwaiti Dinar",      "fr": "Dinar koweïtien",      "es": "Dinar kuwaití",      "tr": "Kuveyt Dinarı",        "flag": "🇰🇼"},
    "QAR": {"ar": "الريال القطري",     "en": "Qatari Riyal",       "fr": "Riyal qatari",         "es": "Riyal catarí",       "tr": "Katar Riyali",         "flag": "🇶🇦"},
    "BHD": {"ar": "الدينار البحريني",  "en": "Bahraini Dinar",     "fr": "Dinar bahreïni",       "es": "Dinar bareiní",      "tr": "Bahreyn Dinarı",       "flag": "🇧🇭"},
    "OMR": {"ar": "الريال العُماني",   "en": "Omani Rial",         "fr": "Rial omanais",         "es": "Rial omaní",         "tr": "Umman Riyali",         "flag": "🇴🇲"},
    "JOD": {"ar": "الدينار الأردني",   "en": "Jordanian Dinar",    "fr": "Dinar jordanien",      "es": "Dinar jordano",      "tr": "Ürdün Dinarı",         "flag": "🇯🇴"},
    "LYD": {"ar": "الدينار الليبي",    "en": "Libyan Dinar",       "fr": "Dinar libyen",         "es": "Dinar libio",        "tr": "Libya Dinarı",         "flag": "🇱🇾"},
    "IQD": {"ar": "الدينار العراقي",   "en": "Iraqi Dinar",        "fr": "Dinar irakien",        "es": "Dinar iraquí",       "tr": "Irak Dinarı",          "flag": "🇮🇶"},
    "SYP": {"ar": "الليرة السورية",    "en": "Syrian Pound",       "fr": "Livre syrienne",       "es": "Libra siria",        "tr": "Suriye Lirası",        "flag": "🇸🇾"},
    "LBP": {"ar": "الليرة اللبنانية", "en": "Lebanese Pound",     "fr": "Livre libanaise",      "es": "Libra libanesa",     "tr": "Lübnan Lirası",        "flag": "🇱🇧"},
    "YER": {"ar": "الريال اليمني",     "en": "Yemeni Rial",        "fr": "Rial yéménite",        "es": "Rial yemení",        "tr": "Yemen Riyali",         "flag": "🇾🇪"},
    "EUR": {"ar": "اليورو",            "en": "Euro",               "fr": "Euro",                 "es": "Euro",               "tr": "Euro",                 "flag": "🇪🇺"},
    "GBP": {"ar": "الجنيه الإسترليني","en": "British Pound",      "fr": "Livre sterling",       "es": "Libra esterlina",    "tr": "İngiliz Sterlini",     "flag": "🇬🇧"},
    "JPY": {"ar": "الين الياباني",     "en": "Japanese Yen",       "fr": "Yen japonais",         "es": "Yen japonés",        "tr": "Japon Yeni",           "flag": "🇯🇵"},
    "CNY": {"ar": "اليوان الصيني",     "en": "Chinese Yuan",       "fr": "Yuan chinois",         "es": "Yuan chino",         "tr": "Çin Yuanı",            "flag": "🇨🇳"},
    "CHF": {"ar": "الفرنك السويسري",   "en": "Swiss Franc",        "fr": "Franc suisse",         "es": "Franco suizo",       "tr": "İsviçre Frangı",       "flag": "🇨🇭"},
    "CAD": {"ar": "الدولار الكندي",    "en": "Canadian Dollar",    "fr": "Dollar canadien",      "es": "Dólar canadiense",   "tr": "Kanada Doları",        "flag": "🇨🇦"},
    "AUD": {"ar": "الدولار الأسترالي", "en": "Australian Dollar",  "fr": "Dollar australien",    "es": "Dólar australiano",  "tr": "Avustralya Doları",    "flag": "🇦🇺"},
    "INR": {"ar": "الروبية الهندية",   "en": "Indian Rupee",       "fr": "Roupie indienne",      "es": "Rupia india",        "tr": "Hint Rupisi",          "flag": "🇮🇳"},
    "TRY": {"ar": "الليرة التركية",    "en": "Turkish Lira",       "fr": "Livre turque",         "es": "Lira turca",         "tr": "Türk Lirası",          "flag": "🇹🇷"},
    "BRL": {"ar": "الريال البرازيلي",  "en": "Brazilian Real",     "fr": "Real brésilien",       "es": "Real brasileño",     "tr": "Brezilya Reali",       "flag": "🇧🇷"},
    "RUB": {"ar": "الروبل الروسي",     "en": "Russian Ruble",      "fr": "Rouble russe",         "es": "Rublo ruso",         "tr": "Rus Rublesi",          "flag": "🇷🇺"},
    "KRW": {"ar": "الوون الكوري",      "en": "South Korean Won",   "fr": "Won sud-coréen",       "es": "Won surcoreano",     "tr": "Güney Kore Wonu",      "flag": "🇰🇷"},
    "MXN": {"ar": "البيزو المكسيكي",   "en": "Mexican Peso",       "fr": "Peso mexicain",        "es": "Peso mexicano",      "tr": "Meksika Pesosu",       "flag": "🇲🇽"},
    "SGD": {"ar": "الدولار السنغافوري","en": "Singapore Dollar",   "fr": "Dollar singapourien",  "es": "Dólar de Singapur",  "tr": "Singapur Doları",      "flag": "🇸🇬"},
}

# Precious metal / commodity codes (from exchange rate API, value = oz per USD → invert for USD/oz)
METAL_META: dict[str, dict] = {
    "XAU": {"ar": "ذهب",     "en": "Gold",      "fr": "Or",        "es": "Oro",      "tr": "Altın",    "icon": "🥇"},
    "XAG": {"ar": "فضة",     "en": "Silver",    "fr": "Argent",    "es": "Plata",    "tr": "Gümüş",    "icon": "🥈"},
    "XPT": {"ar": "بلاتين",  "en": "Platinum",  "fr": "Platine",   "es": "Platino",  "tr": "Platin",   "icon": "🔘"},
    "XPD": {"ar": "بلاديوم", "en": "Palladium", "fr": "Palladium", "es": "Paladio",  "tr": "Paladyum", "icon": "⬜"},
}


def _lighten(hex_color: str, factor: float = 0.35) -> str:
    """Mix *hex_color* with white by *factor* (0 = original, 1 = white).
    Used to auto-generate a gradient end-color when only one color is stored."""
    try:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = h[0]*2 + h[1]*2 + h[2]*2
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        r2 = int(r + (255 - r) * factor)
        g2 = int(g + (255 - g) * factor)
        b2 = int(b + (255 - b) * factor)
        return f"#{r2:02x}{g2:02x}{b2:02x}"
    except Exception:
        return hex_color


def _fetch_market_data(api_keys: dict, cache_path: str = "",
                       force_refresh: bool = False) -> dict:
    """Fetch exchange rates, gold price, and Brent oil at build time.

    Returns a dict: {"rates": {...}, "gold": float|None, "oil": float|None, "ts": str}
    On any failure returns whatever partial data was collected (never raises).
    Results are cached to *cache_path* (6-hour TTL) unless force_refresh is True.
    """
    import urllib.request as _urlreq
    import json as _json
    from datetime import timezone

    empty: dict = {"rates": {}, "gold": None, "oil": None, "ts": ""}

    # ── Try cache first ────────────────────────────────────────────────────────
    if cache_path and not force_refresh and os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as _f:
                cached = _json.load(_f)
            age_h = (datetime.now(timezone.utc).timestamp() -
                     cached.get("_fetched_at", 0)) / 3600
            if age_h < 6:
                cached.pop("_fetched_at", None)
                logger.info("Market data: using cache (%.1fh old)", age_h)
                return cached
        except Exception:
            pass

    data: dict = dict(empty)

    # ── Exchange rates (no API key needed) ────────────────────────────────────
    try:
        with _urlreq.urlopen(
            "https://open.er-api.com/v6/latest/USD", timeout=8
        ) as _r:
            obj = _json.loads(_r.read())
        data["rates"] = obj.get("rates", {})
        data["ts"] = obj.get("time_last_update_utc", "")[:16]
        logger.info("Market data: %d exchange rates fetched", len(data["rates"]))
    except Exception as _e:
        logger.warning("Market data: currency fetch failed: %s", _e)

    # ── Gold price via MetalpriceAPI (optional) ────────────────────────────────
    key_m = (api_keys.get("metalpriceapi") or "").strip()
    if key_m:
        try:
            _url = (f"https://api.metalpriceapi.com/v1/latest"
                    f"?api_key={key_m}&base=USD&currencies=XAU")
            with _urlreq.urlopen(_url, timeout=8) as _r:
                obj = _json.loads(_r.read())
            xau = obj.get("rates", {}).get("XAU")
            data["gold"] = round(1.0 / xau, 2) if xau else None
            logger.info("Market data: gold $%s/oz", data["gold"])
        except Exception as _e:
            logger.warning("Market data: gold fetch failed: %s", _e)

    # ── Brent crude via Alpha Vantage (optional) ──────────────────────────────
    key_a = (api_keys.get("alphavantage") or "").strip()
    if key_a:
        try:
            _url = (f"https://www.alphavantage.co/query"
                    f"?function=BRENT&interval=daily&apikey={key_a}")
            with _urlreq.urlopen(_url, timeout=8) as _r:
                obj = _json.loads(_r.read())
            entries = obj.get("data", [])
            data["oil"] = float(entries[0]["value"]) if entries else None
            logger.info("Market data: Brent $%s/bbl", data["oil"])
        except Exception as _e:
            logger.warning("Market data: oil fetch failed: %s", _e)

    # ── Persist cache ─────────────────────────────────────────────────────────
    if cache_path:
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            payload = dict(data, _fetched_at=datetime.now(timezone.utc).timestamp())
            with open(cache_path, "w", encoding="utf-8") as _f:
                _json.dump(payload, _f, ensure_ascii=False)
        except Exception as _e:
            logger.warning("Market data: cache write failed: %s", _e)

    return data


def _economy_widget(s: dict, active_tab: str = "") -> str:
    """Build the tabbed economy navigation widget (language-aware).

    active_tab: "prices" | "business" | "travel" to highlight the active link tab.
    """
    prices_cls   = "econ-tab active" if active_tab == "prices"   else "econ-tab"
    business_cls = "econ-tab active" if active_tab == "business" else "econ-tab"
    travel_cls   = "econ-tab active" if active_tab == "travel"   else "econ-tab"

    # ── Tab panels (coming-soon placeholders) ────────────────────────────────
    stats_panel  = f'<div class="econ-soon">{esc(s["econ_stats_soon"])}</div>'
    bourse_panel = f'<div class="econ-soon">{esc(s["econ_bourse_soon"])}</div>'
    biz_panel    = f'<div class="econ-soon">{esc(s["econ_biz_soon"])}</div>'

    return (
        f'<div class="econ-widget" role="complementary" aria-label="{esc(s["econ_widget_label"])}">'
        f'<div class="econ-tab-nav">'
        f'<div class="econ-tab-nav-inner">'
        f'<a href="prices.html"   class="{prices_cls}">{esc(s["econ_prices"])}</a>'
        f'<a href="business.html" class="{business_cls}">{esc(s["econ_business_btn"])}</a>'
        f'<a href="travel.html"   class="{travel_cls}">{esc(s["econ_travel_btn"])}</a>'
        f'<button class="econ-tab" data-panel="econ-stats">{esc(s["econ_stats_btn"])}</button>'
        f'<button class="econ-tab" data-panel="econ-bourse">{esc(s["econ_bourse_btn"])}</button>'
        f'<button class="econ-tab" data-panel="econ-biz">{esc(s["econ_biz_btn"])}</button>'
        f'</div>'
        f'</div>'
        f'<div class="econ-panels">'
        f'<div class="econ-panel" id="econ-stats">{stats_panel}</div>'
        f'<div class="econ-panel" id="econ-bourse">{bourse_panel}</div>'
        f'<div class="econ-panel" id="econ-biz">{biz_panel}</div>'
        f'</div>'
        f'</div>'
    )


# ── Market strip — shown only on economy.html ─────────────────────────────────

# (code, display_symbol) — USD is the base, all rates are "1 USD = X code"
DEFAULT_MARKET_PAIRS = [
    # Arab currencies
    ("MAD", "MAD"), ("DZD", "DZD"), ("TND", "TND"), ("EGP", "EGP"),
    ("SAR", "SAR"), ("AED", "AED"), ("KWD", "KWD"), ("QAR", "QAR"),
    ("BHD", "BHD"), ("OMR", "OMR"), ("JOD", "JOD"),
    # Major economies
    ("EUR", "EUR"), ("GBP", "GBP"), ("JPY", "JPY"), ("CNY", "CNY"),
    ("CHF", "CHF"), ("CAD", "CAD"), ("AUD", "AUD"),
]



# Arabic display names override (for any remaining non-Arabic source names)
SOURCE_AR_NAME: dict[str, str] = {
    "Le360":    "لو 360",
    "MAP News": "وكالة ماب",
}

# UI strings per language — loaded dynamically from config/strings/*.json
# To add a new language: drop a new <lang>.json file in that folder — no code change needed.
def _load_strings() -> dict[str, dict]:
    """Auto-discover and load all language string files from config/strings/."""
    import json as _json
    _strings_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config", "strings"
    )
    result: dict[str, dict] = {}
    if not os.path.isdir(_strings_dir):
        logger.warning("Strings directory not found: %s", _strings_dir)
        return result
    for _fname in sorted(os.listdir(_strings_dir)):
        if not _fname.endswith(".json"):
            continue
        _lang = _fname[:-5]
        _fpath = os.path.join(_strings_dir, _fname)
        try:
            with open(_fpath, "r", encoding="utf-8") as _f:
                result[_lang] = _json.load(_f)
            logger.debug("Strings: loaded %s (%d keys)", _fname, len(result[_lang]))
        except Exception as _e:
            logger.warning("Strings: failed to load %s — %s", _fname, _e)
    if result:
        logger.info("Strings: loaded %d language(s): %s", len(result), ", ".join(sorted(result)))
    return result


STRINGS: dict[str, dict] = _load_strings()

# ── LEGACY FALLBACK (kept for safety — remove after full migration confirmed) ──
_STRINGS_FALLBACK: dict[str, dict] = {
    "ar": {
        "lang": "ar", "dir": "rtl",
        "font_family": "'Cairo','Segoe UI',Tahoma,system-ui,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap",
        "og_locale": "ar_AR", "in_language": "ar",
        "slide": "الشريحة", "highlights": "أبرز الأخبار",
        "prev": "السابق", "next": "التالي",
        "world_regions_label": "مناطق العالم",
        "media_regions_label": "صوت وصورة",
        "home": "🏠 الرئيسية", "home_bare": "الرئيسية",
        "world": "📺 صوت وصورة",
        "stats": "📊 الإحصائيات",
        "articles_unit": "خبر", "sources_unit": "مصدر", "cats_unit": "تصنيف",
        "sections_widget": "🗂️ الأقسام", "links_widget": "📎 روابط",
        "about": "من نحن", "privacy": "سياسة الخصوصية", "ad": "إعلان",
        "contact": "اتصل بنا", "terms": "شروط الاستخدام", "advertise": "أعلن معنا",
        "theme_btn_label": "تبديل الوضع", "live_label": "مباشر",
        "nav_label": "الأقسام", "header_label": "عنوان الموقع",
        "back_to_top": "العودة للأعلى", "theme_color": "#1d4ed8",
        "updated": "آخر تحديث", "footer_links": "روابط", "footer_cats_title": "الأقسام",
        "rss_feeds": "تغذيات RSS", "rss_all": "كل الأخبار",
        "search_label": "بحث", "search_placeholder": "ابحث في العناوين...",
        "search_no_results": "لا نتائج للبحث",
        "more_from": "المزيد من", "arrow": "←",
        "no_news": "لا توجد أخبار حالياً",
        "run_hint": "يرجى تشغيل: <code>python run.py</code>",
        "coming_soon": "قريباً ✦",
        "coming_desc": "سيتم إضافة مصادر لهذا القسم قريباً",
        "cat_desc_tpl": "آخر أخبار {name} من مصادر موثوقة",
        "world_coming_tpl": "سيتم إضافة مصادر لهذا القسم قريباً — <a href=\"{href}\" style=\"color:{color}\">تصفح القسم</a>",
        "body_class": "lang-rtl",
        "econ_prices": "💱 أسعار",
        "econ_stats_btn": "📊 إحصاءات وأرقام",
        "econ_bourse_btn": "📈 بورصات",
        "econ_biz_btn": "🏢 دليل الشركات",
        "econ_business_btn": "💼 مال وأعمال",
        "econ_travel_btn": "✈️ سياحة وسفر",
        "econ_widget_label": "أقسام الاقتصاد",
        "market_strip_label": "بيانات السوق",
        "econ_stats_soon": "📊 إحصاءات وأرقام — قريباً",
        "econ_bourse_soon": "📈 بورصات — قريباً",
        "econ_biz_soon": "🏢 دليل الشركات — قريباً",
        "prices_fx_hdr": "💱 أسعار الصرف",
        "prices_metals_hdr": "🥇 المعادن",
        "prices_oil_hdr": "🛢️ النفط والطاقة",
        "prices_commodities_hdr": "🌾 السلع الأساسية",
        "prices_col_currency": "العملة",
        "prices_col_price": "السعر",
        "prices_col_compare": "المقارنة",
        "prices_col_metal": "المعدن",
        "prices_col_type": "النوع",
        "prices_col_unit": "الوحدة",
        "prices_oz_unit": "/ أوقية",
        "prices_bbl_unit": "/ برميل",
        "prices_brent_name": "خام برنت",
        "prices_fx_error": "⚠️ تعذّر جلب بيانات أسعار الصرف",
        "prices_metals_hint": "🥇 أضف مفتاح MetalpriceAPI في config/api_keys.json لعرض أسعار المعادن",
        "prices_oil_hint": "🛢️ أضف مفتاح Alpha Vantage في config/api_keys.json لعرض أسعار النفط",
        "prices_commodities_soon": "🌾 سيتم ربط أسعار السلع الأساسية قريباً",
        "prices_updated": "آخر تحديث",
        "prices_home_bc": "الرئيسية",
        "prices_economy_bc": "اقتصاد",
        "prices_prices_bc": "أسعار",
        "src_all": "الكل",
        "src_no_results": "لا توجد مقالات من هذا المصدر حالياً",
        "gdpr_title": "نستخدم ملفات تعريف الارتباط",
        "gdpr_body": "نستخدم ملفات تعريف الارتباط لتحسين تجربتك وتحليل حركة الزوار. اختر ما يناسبك.",
        "gdpr_accept": "قبول الكل",
        "gdpr_reject": "الضروري فقط",
        "gdpr_customize": "تخصيص",
        "gdpr_policy": "سياسة الخصوصية",
        "gdpr_modal_title": "تفضيلات الخصوصية",
        "gdpr_necessary": "ضروري دائماً",
        "gdpr_necessary_desc": "مطلوب لعمل الموقع. لا يمكن تعطيله.",
        "gdpr_analytics": "التحليلات والأداء",
        "gdpr_analytics_desc": "يساعدنا على فهم كيفية استخدام الزوار للموقع. بيانات مجهولة الهوية فقط.",
        "gdpr_always_on": "مفعّل دائماً",
        "gdpr_save": "حفظ التفضيلات",
        "art_read_orig":    "📖 اقرأ المقال الأصلي",
        "art_related":      "مقالات ذات صلة",
        "art_browse_cat":   "المزيد من أخبار",
        "art_from_source":  "خبر من",
        "art_summary_lbl":  "ملخص",
        "art_by_source":    "المصدر",
        "art_back":         "→ العودة",
        "art_disclaimer":   "للتفاصيل الكاملة زر المصدر الأصلي",
        "cluster_sources":      "📡 {n} مصادر",
        "cluster_sources_1":    "📡 مصدر واحد",
        "spectrum_wire":        "وكالة",
        "spectrum_public":      "عام",
        "spectrum_commercial":  "خاص",
        "spectrum_state":       "رسمي",
        "spectrum_independent": "مستقل",
        "live_tv_label":   "📡 بث مباشر",
        "live_tv_title":   "بث مباشر — القنوات الإخبارية",
        "live_tv_desc":    "تابع القنوات الإخبارية العالمية مباشرةً عبر اليوتيوب",
        "live_tv_watch":   "▶ شاهد مباشر",
        "live_tv_on_air":  "على الهواء",
    },
    "en": {
        "lang": "en", "dir": "ltr",
        "font_family": "'Roboto','Segoe UI',Arial,system-ui,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&display=swap",
        "og_locale": "en_US", "in_language": "en",
        "slide": "Slide", "highlights": "Top Stories",
        "prev": "Previous", "next": "Next",
        "world_regions_label": "World Regions",
        "media_regions_label": "Media",
        "home": "🏠 Home", "home_bare": "Home",
        "world": "📺 Media",
        "stats": "📊 Stats",
        "articles_unit": "articles", "sources_unit": "sources", "cats_unit": "sections",
        "sections_widget": "🗂️ Sections", "links_widget": "📎 Links",
        "about": "About", "privacy": "Privacy Policy", "ad": "Advertisement",
        "contact": "Contact", "terms": "Terms of Use", "advertise": "Advertise",
        "theme_btn_label": "Toggle theme", "live_label": "Live",
        "nav_label": "Sections", "header_label": "Site header",
        "back_to_top": "Back to top", "theme_color": "#2563eb",
        "updated": "Last updated", "footer_links": "Links", "footer_cats_title": "Sections",
        "rss_feeds": "RSS Feeds", "rss_all": "All News",
        "search_label": "Search", "search_placeholder": "Search headlines...",
        "search_no_results": "No results found",
        "more_from": "More from", "arrow": "→",
        "no_news": "No news available",
        "run_hint": "Please run: <code>python run.py</code>",
        "coming_soon": "Coming Soon ✦",
        "coming_desc": "Sources for this section will be added soon",
        "cat_desc_tpl": "Latest {name} news from trusted sources",
        "world_coming_tpl": "Sources for this section will be added soon — <a href=\"{href}\" style=\"color:{color}\">browse section</a>",
        "body_class": "lang-ltr",
        "econ_prices": "💱 Prices",
        "econ_stats_btn": "📊 Statistics",
        "econ_bourse_btn": "📈 Markets",
        "econ_biz_btn": "🏢 Business Directory",
        "econ_business_btn": "💼 Finance & Business",
        "econ_travel_btn": "✈️ Travel & Tourism",
        "econ_widget_label": "Economy sections",
        "market_strip_label": "Market data",
        "econ_stats_soon": "📊 Statistics — Coming soon",
        "econ_bourse_soon": "📈 Markets — Coming soon",
        "econ_biz_soon": "🏢 Business Directory — Coming soon",
        "prices_fx_hdr": "💱 Exchange Rates",
        "prices_metals_hdr": "🥇 Precious Metals",
        "prices_oil_hdr": "🛢️ Oil & Energy",
        "prices_commodities_hdr": "🌾 Commodities",
        "prices_col_currency": "Currency",
        "prices_col_price": "Price",
        "prices_col_compare": "Base",
        "prices_col_metal": "Metal",
        "prices_col_type": "Type",
        "prices_col_unit": "Unit",
        "prices_oz_unit": "/ oz",
        "prices_bbl_unit": "/ bbl",
        "prices_brent_name": "Brent Crude",
        "prices_fx_error": "⚠️ Failed to fetch exchange rate data",
        "prices_metals_hint": "🥇 Add a MetalpriceAPI key in config/api_keys.json to display metal prices",
        "prices_oil_hint": "🛢️ Add an Alpha Vantage key in config/api_keys.json to display oil prices",
        "prices_commodities_soon": "🌾 Commodity prices will be connected soon",
        "prices_updated": "Last updated",
        "prices_home_bc": "Home",
        "prices_economy_bc": "Economy",
        "prices_prices_bc": "Prices",
        "src_all": "All",
        "src_no_results": "No articles from this source at the moment",
        "gdpr_title": "We use cookies",
        "gdpr_body": "We use cookies to improve your experience and analyse traffic. Choose what works for you.",
        "gdpr_accept": "Accept All",
        "gdpr_reject": "Essential Only",
        "gdpr_customize": "Customize",
        "gdpr_policy": "Privacy Policy",
        "gdpr_modal_title": "Privacy Preferences",
        "gdpr_necessary": "Strictly Necessary",
        "gdpr_necessary_desc": "Required for the site to function. Cannot be disabled.",
        "gdpr_analytics": "Analytics & Performance",
        "gdpr_analytics_desc": "Helps us understand how visitors use the site. Anonymous data only.",
        "gdpr_always_on": "Always On",
        "gdpr_save": "Save Preferences",
        "art_read_orig":    "📖 Read full article",
        "art_related":      "Related articles",
        "art_browse_cat":   "More news from",
        "art_from_source":  "Article from",
        "art_summary_lbl":  "Summary",
        "art_by_source":    "Source",
        "art_back":         "← Back",
        "art_disclaimer":   "Visit the original source for the full article",
        "cluster_sources":      "📡 {n} sources",
        "cluster_sources_1":    "📡 1 source",
        "spectrum_wire":        "Agency",
        "spectrum_public":      "Public",
        "spectrum_commercial":  "Commercial",
        "spectrum_state":       "State",
        "spectrum_independent": "Independent",
        "live_tv_label":   "📡 Live TV",
        "live_tv_title":   "Live TV — News Channels",
        "live_tv_desc":    "Watch global news channels live on YouTube",
        "live_tv_watch":   "▶ Watch Live",
        "live_tv_on_air":  "On Air",
    },
    "fr": {
        "lang": "fr", "dir": "ltr",
        "font_family": "'Roboto','Segoe UI',Arial,system-ui,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&display=swap",
        "og_locale": "fr_FR", "in_language": "fr",
        "slide": "Diapositive", "highlights": "À la une",
        "prev": "Précédent", "next": "Suivant",
        "world_regions_label": "Régions du monde",
        "media_regions_label": "Médias",
        "home": "🏠 Accueil", "home_bare": "Accueil",
        "world": "📺 Médias",
        "stats": "📊 Statistiques",
        "articles_unit": "articles", "sources_unit": "sources", "cats_unit": "sections",
        "sections_widget": "🗂️ Sections", "links_widget": "📎 Liens",
        "about": "À propos", "privacy": "Confidentialité", "ad": "Publicité",
        "contact": "Contact", "terms": "Conditions d'utilisation", "advertise": "Publicité avec nous",
        "theme_btn_label": "Changer le thème", "live_label": "En direct",
        "nav_label": "Sections", "header_label": "En-tête",
        "back_to_top": "Retour en haut", "theme_color": "#1d4ed8",
        "updated": "Mise à jour", "footer_links": "Liens", "footer_cats_title": "Rubriques",
        "rss_feeds": "Flux RSS", "rss_all": "Toutes les actualités",
        "search_label": "Recherche", "search_placeholder": "Rechercher des titres...",
        "search_no_results": "Aucun résultat",
        "more_from": "Plus de", "arrow": "→",
        "no_news": "Aucune actualité disponible",
        "run_hint": "Veuillez exécuter: <code>python run.py</code>",
        "coming_soon": "Bientôt ✦",
        "coming_desc": "Des sources seront ajoutées prochainement",
        "cat_desc_tpl": "Dernières actualités {name} de sources fiables",
        "world_coming_tpl": "Des sources seront ajoutées — <a href=\"{href}\" style=\"color:{color}\">voir la section</a>",
        "body_class": "lang-ltr",
        "econ_prices": "💱 Prix",
        "econ_stats_btn": "📊 Statistiques",
        "econ_bourse_btn": "📈 Bourses",
        "econ_biz_btn": "🏢 Répertoire",
        "econ_business_btn": "💼 Finance & Business",
        "econ_travel_btn": "✈️ Tourisme & Voyages",
        "econ_widget_label": "Sections économie",
        "market_strip_label": "Données du marché",
        "econ_stats_soon": "📊 Statistiques — Bientôt",
        "econ_bourse_soon": "📈 Bourses — Bientôt",
        "econ_biz_soon": "🏢 Répertoire des entreprises — Bientôt",
        "prices_fx_hdr": "💱 Taux de change",
        "prices_metals_hdr": "🥇 Métaux précieux",
        "prices_oil_hdr": "🛢️ Pétrole et énergie",
        "prices_commodities_hdr": "🌾 Matières premières",
        "prices_col_currency": "Devise",
        "prices_col_price": "Prix",
        "prices_col_compare": "Base",
        "prices_col_metal": "Métal",
        "prices_col_type": "Type",
        "prices_col_unit": "Unité",
        "prices_oz_unit": "/ oz",
        "prices_bbl_unit": "/ bbl",
        "prices_brent_name": "Brut Brent",
        "prices_fx_error": "⚠️ Impossible de récupérer les taux de change",
        "prices_metals_hint": "🥇 Ajoutez une clé MetalpriceAPI dans config/api_keys.json",
        "prices_oil_hint": "🛢️ Ajoutez une clé Alpha Vantage dans config/api_keys.json",
        "prices_commodities_soon": "🌾 Les prix des matières premières seront ajoutés prochainement",
        "prices_updated": "Mise à jour",
        "prices_home_bc": "Accueil",
        "prices_economy_bc": "Économie",
        "prices_prices_bc": "Prix",
        "src_all": "Tout",
        "src_no_results": "Aucun article de cette source pour le moment",
        "gdpr_title": "Nous utilisons des cookies",
        "gdpr_body": "Nous utilisons des cookies pour améliorer votre expérience et analyser le trafic. Faites votre choix.",
        "gdpr_accept": "Tout accepter",
        "gdpr_reject": "Essentiel uniquement",
        "gdpr_customize": "Personnaliser",
        "gdpr_policy": "Politique de confidentialité",
        "gdpr_modal_title": "Préférences de confidentialité",
        "gdpr_necessary": "Strictement nécessaire",
        "gdpr_necessary_desc": "Requis pour le fonctionnement du site. Ne peut pas être désactivé.",
        "gdpr_analytics": "Analytique et performance",
        "gdpr_analytics_desc": "Nous aide à comprendre comment les visiteurs utilisent le site. Données anonymes uniquement.",
        "gdpr_always_on": "Toujours actif",
        "gdpr_save": "Enregistrer les préférences",
        "art_read_orig":    "📖 Lire l'article complet",
        "art_related":      "Articles liés",
        "art_browse_cat":   "Plus d'actualités de",
        "art_from_source":  "Article de",
        "art_summary_lbl":  "Résumé",
        "art_by_source":    "Source",
        "art_back":         "← Retour",
        "art_disclaimer":   "Visitez la source originale pour l'article complet",
        "cluster_sources":      "📡 {n} sources",
        "cluster_sources_1":    "📡 1 source",
        "spectrum_wire":        "Agence",
        "spectrum_public":      "Public",
        "spectrum_commercial":  "Commercial",
        "spectrum_state":       "Officiel",
        "spectrum_independent": "Indépendant",
        "live_tv_label":   "📡 TV en direct",
        "live_tv_title":   "TV en direct — Chaînes d'info",
        "live_tv_desc":    "Regardez les chaînes d'information mondiales en direct sur YouTube",
        "live_tv_watch":   "▶ Regarder en direct",
        "live_tv_on_air":  "En direct",
    },
    "es": {
        "lang": "es", "dir": "ltr",
        "font_family": "'Roboto','Segoe UI',Arial,system-ui,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&display=swap",
        "og_locale": "es_ES", "in_language": "es",
        "slide": "Diapositiva", "highlights": "Destacados",
        "prev": "Anterior", "next": "Siguiente",
        "world_regions_label": "Regiones del mundo",
        "media_regions_label": "Medios",
        "home": "🏠 Inicio", "home_bare": "Inicio",
        "world": "📺 Medios",
        "stats": "📊 Estadísticas",
        "articles_unit": "artículos", "sources_unit": "fuentes", "cats_unit": "secciones",
        "sections_widget": "🗂️ Secciones", "links_widget": "📎 Enlaces",
        "about": "Acerca de", "privacy": "Privacidad", "ad": "Publicidad",
        "contact": "Contacto", "terms": "Términos de uso", "advertise": "Publicidad",
        "theme_btn_label": "Cambiar tema", "live_label": "En vivo",
        "nav_label": "Secciones", "header_label": "Encabezado",
        "back_to_top": "Volver arriba", "theme_color": "#c2410c",
        "updated": "Actualizado", "footer_links": "Enlaces", "footer_cats_title": "Secciones",
        "rss_feeds": "Fuentes RSS", "rss_all": "Todas las noticias",
        "search_label": "Buscar", "search_placeholder": "Buscar titulares...",
        "search_no_results": "Sin resultados",
        "more_from": "Más de", "arrow": "→",
        "no_news": "No hay noticias disponibles",
        "run_hint": "Por favor ejecuta: <code>python run.py</code>",
        "coming_soon": "Próximamente ✦",
        "coming_desc": "Se añadirán fuentes pronto",
        "cat_desc_tpl": "Últimas noticias de {name} de fuentes confiables",
        "world_coming_tpl": "Se añadirán fuentes pronto — <a href=\"{href}\" style=\"color:{color}\">explorar sección</a>",
        "body_class": "lang-ltr",
        "econ_prices": "💱 Precios",
        "econ_stats_btn": "📊 Estadísticas",
        "econ_bourse_btn": "📈 Bolsas",
        "econ_biz_btn": "🏢 Directorio",
        "econ_business_btn": "💼 Finanzas & Negocios",
        "econ_travel_btn": "✈️ Turismo & Viajes",
        "econ_widget_label": "Secciones de economía",
        "market_strip_label": "Datos del mercado",
        "econ_stats_soon": "📊 Estadísticas — Próximamente",
        "econ_bourse_soon": "📈 Bolsas — Próximamente",
        "econ_biz_soon": "🏢 Directorio de empresas — Próximamente",
        "prices_fx_hdr": "💱 Tipos de cambio",
        "prices_metals_hdr": "🥇 Metales preciosos",
        "prices_oil_hdr": "🛢️ Petróleo y energía",
        "prices_commodities_hdr": "🌾 Materias primas",
        "prices_col_currency": "Divisa",
        "prices_col_price": "Precio",
        "prices_col_compare": "Base",
        "prices_col_metal": "Metal",
        "prices_col_type": "Tipo",
        "prices_col_unit": "Unidad",
        "prices_oz_unit": "/ oz",
        "prices_bbl_unit": "/ bbl",
        "prices_brent_name": "Crudo Brent",
        "prices_fx_error": "⚠️ Error al obtener los tipos de cambio",
        "prices_metals_hint": "🥇 Añade una clave MetalpriceAPI en config/api_keys.json",
        "prices_oil_hint": "🛢️ Añade una clave Alpha Vantage en config/api_keys.json",
        "prices_commodities_soon": "🌾 Los precios de materias primas se añadirán pronto",
        "prices_updated": "Actualizado",
        "prices_home_bc": "Inicio",
        "prices_economy_bc": "Economía",
        "prices_prices_bc": "Precios",
        "src_all": "Todo",
        "src_no_results": "No hay artículos de esta fuente en este momento",
        "gdpr_title": "Usamos cookies",
        "gdpr_body": "Usamos cookies para mejorar tu experiencia y analizar el tráfico. Elige lo que prefieras.",
        "gdpr_accept": "Aceptar todo",
        "gdpr_reject": "Solo esenciales",
        "gdpr_customize": "Personalizar",
        "gdpr_policy": "Política de privacidad",
        "gdpr_modal_title": "Preferencias de privacidad",
        "gdpr_necessary": "Estrictamente necesario",
        "gdpr_necessary_desc": "Necesario para el funcionamiento del sitio. No se puede desactivar.",
        "gdpr_analytics": "Analítica y rendimiento",
        "gdpr_analytics_desc": "Nos ayuda a entender cómo los visitantes usan el sitio. Solo datos anónimos.",
        "gdpr_always_on": "Siempre activo",
        "gdpr_save": "Guardar preferencias",
        "art_read_orig":    "📖 Leer artículo completo",
        "art_related":      "Artículos relacionados",
        "art_browse_cat":   "Más noticias de",
        "art_from_source":  "Artículo de",
        "art_summary_lbl":  "Resumen",
        "art_by_source":    "Fuente",
        "art_back":         "← Volver",
        "art_disclaimer":   "Visita la fuente original para el artículo completo",
        "cluster_sources":      "📡 {n} fuentes",
        "cluster_sources_1":    "📡 1 fuente",
        "spectrum_wire":        "Agencia",
        "spectrum_public":      "Público",
        "spectrum_commercial":  "Comercial",
        "spectrum_state":       "Oficial",
        "spectrum_independent": "Independiente",
        "live_tv_label":   "📡 TV en vivo",
        "live_tv_title":   "TV en vivo — Canales de noticias",
        "live_tv_desc":    "Sigue los canales de noticias globales en directo en YouTube",
        "live_tv_watch":   "▶ Ver en vivo",
        "live_tv_on_air":  "En el aire",
    },
    "tr": {
        "lang": "tr", "dir": "ltr",
        "font_family": "'Roboto','Segoe UI',Arial,system-ui,sans-serif",
        "font_url": "https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&display=swap",
        "og_locale": "tr_TR", "in_language": "tr",
        "slide": "Slayt", "highlights": "Öne Çıkanlar",
        "prev": "Önceki", "next": "Sonraki",
        "world_regions_label": "Dünya Bölgeleri",
        "media_regions_label": "Medya",
        "home": "🏠 Ana Sayfa", "home_bare": "Ana Sayfa",
        "world": "📺 Medya",
        "stats": "📊 İstatistikler",
        "articles_unit": "haber", "sources_unit": "kaynak", "cats_unit": "bölüm",
        "sections_widget": "🗂️ Bölümler", "links_widget": "📎 Bağlantılar",
        "about": "Hakkımızda", "privacy": "Gizlilik Politikası", "ad": "Reklam",
        "contact": "İletişim", "terms": "Kullanim Kosullari", "advertise": "Reklam Ver",
        "theme_btn_label": "Temayı değiştir", "live_label": "Canlı",
        "nav_label": "Bölümler", "header_label": "Site başlığı",
        "back_to_top": "Başa dön", "theme_color": "#dc2626",
        "updated": "Son güncelleme", "footer_links": "Bağlantılar", "footer_cats_title": "Bölümler",
        "rss_feeds": "RSS Beslemeleri", "rss_all": "Tüm haberler",
        "search_label": "Arama", "search_placeholder": "Başlıklarda ara...",
        "search_no_results": "Sonuç bulunamadı",
        "more_from": "Daha fazlası:", "arrow": "→",
        "no_news": "Şu anda haber yok",
        "run_hint": "Lütfen çalıştırın: <code>python run.py</code>",
        "coming_soon": "Yakında ✦",
        "coming_desc": "Bu bölüm için kaynaklar yakında eklenecek",
        "cat_desc_tpl": "Güvenilir kaynaklardan en son {name} haberleri",
        "world_coming_tpl": "Bu bölüm için kaynaklar yakında eklenecek — <a href=\"{href}\" style=\"color:{color}\">bölümü görüntüle</a>",
        "body_class": "lang-ltr",
        "econ_prices": "💱 Kurlar",
        "econ_stats_btn": "📊 İstatistikler",
        "econ_bourse_btn": "📈 Borsalar",
        "econ_biz_btn": "🏢 Şirket Rehberi",
        "econ_business_btn": "💼 Finans & İş Dünyası",
        "econ_travel_btn": "✈️ Turizm & Seyahat",
        "econ_widget_label": "Ekonomi bölümleri",
        "market_strip_label": "Piyasa verileri",
        "econ_stats_soon": "📊 İstatistikler — Yakında",
        "econ_bourse_soon": "📈 Borsalar — Yakında",
        "econ_biz_soon": "🏢 Şirket Rehberi — Yakında",
        "prices_fx_hdr": "💱 Döviz Kurları",
        "prices_metals_hdr": "🥇 Değerli Metaller",
        "prices_oil_hdr": "🛢️ Petrol ve Enerji",
        "prices_commodities_hdr": "🌾 Emtialar",
        "prices_col_currency": "Para Birimi",
        "prices_col_price": "Fiyat",
        "prices_col_compare": "Baz",
        "prices_col_metal": "Metal",
        "prices_col_type": "Tür",
        "prices_col_unit": "Birim",
        "prices_oz_unit": "/ ons",
        "prices_bbl_unit": "/ varil",
        "prices_brent_name": "Brent Ham Petrol",
        "prices_fx_error": "⚠️ Döviz kuru verileri alınamadı",
        "prices_metals_hint": "🥇 Metal fiyatlarını görüntülemek için config/api_keys.json dosyasına MetalpriceAPI anahtarı ekleyin",
        "prices_oil_hint": "🛢️ Petrol fiyatlarını görüntülemek için config/api_keys.json dosyasına Alpha Vantage anahtarı ekleyin",
        "prices_commodities_soon": "🌾 Emtia fiyatları yakında eklenecek",
        "prices_updated": "Son güncelleme",
        "prices_home_bc": "Ana Sayfa",
        "prices_economy_bc": "Ekonomi",
        "prices_prices_bc": "Kurlar",
        "src_all": "Tümü",
        "src_no_results": "Bu kaynaktan şu an makale bulunmuyor",
        "gdpr_title": "Çerez kullanıyoruz",
        "gdpr_body": "Deneyiminizi iyileştirmek ve trafiği analiz etmek için çerez kullanıyoruz. Tercihinizi seçin.",
        "gdpr_accept": "Tümünü kabul et",
        "gdpr_reject": "Yalnızca zorunlu",
        "gdpr_customize": "Özelleştir",
        "gdpr_policy": "Gizlilik Politikası",
        "gdpr_modal_title": "Gizlilik Tercihleri",
        "gdpr_necessary": "Zorunlu",
        "gdpr_necessary_desc": "Sitenin çalışması için gereklidir. Devre dışı bırakılamaz.",
        "gdpr_analytics": "Analitik ve Performans",
        "gdpr_analytics_desc": "Ziyaretçilerin siteyi nasıl kullandığını anlamamıza yardımcı olur. Yalnızca anonim veriler.",
        "gdpr_always_on": "Her zaman açık",
        "gdpr_save": "Tercihleri kaydet",
        "art_read_orig":    "📖 Tam makaleyi oku",
        "art_related":      "İlgili makaleler",
        "art_browse_cat":   "Daha fazla haber:",
        "art_from_source":  "Kaynak:",
        "art_summary_lbl":  "Özet",
        "art_by_source":    "Kaynak",
        "art_back":         "← Geri",
        "art_disclaimer":   "Tam makale için orijinal kaynağı ziyaret edin",
        "cluster_sources":      "📡 {n} kaynak",
        "cluster_sources_1":    "📡 1 kaynak",
        "spectrum_wire":        "Ajans",
        "spectrum_public":      "Kamu",
        "spectrum_commercial":  "Ticari",
        "spectrum_state":       "Resmi",
        "spectrum_independent": "Bağımsız",
        "live_tv_label":   "📡 Canlı TV",
        "live_tv_title":   "Canlı TV — Haber Kanalları",
        "live_tv_desc":    "YouTube üzerinden dünya haber kanallarını canlı izleyin",
        "live_tv_watch":   "▶ Canlı İzle",
        "live_tv_on_air":  "Yayında",
    },
}

# Merge fallback into STRINGS for any missing language (safety net)
for _lang, _sdict in _STRINGS_FALLBACK.items():
    if _lang not in STRINGS:
        STRINGS[_lang] = _sdict
        logger.warning("Strings: using fallback for lang=%s (JSON file missing)", _lang)


def _load_spectrum_map() -> dict[str, str]:
    """Load config/spectrum_map.json → {source_name: spectrum_type}.
    Returns an empty dict on failure so the site still generates without badges."""
    _path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "config", "spectrum_map.json")
    try:
        with open(_path, "r", encoding="utf-8") as _f:
            raw = json.load(_f)
        # Filter out comment/meta keys that start with "_"
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except Exception as _e:
        logger.warning("spectrum_map.json load failed: %s", _e)
        return {}


# Loaded once at import time
_SPECTRUM_MAP: dict[str, str] = _load_spectrum_map()

# CSS class per spectrum type
_SPECTRUM_CSS: dict[str, str] = {
    "wire":        "sp-wire",
    "public":      "sp-public",
    "commercial":  "sp-commercial",
    "state":       "sp-state",
    "independent": "sp-independent",
}


def _article_slug(url: str) -> str:
    """Return a 12-char hex ID for a URL — used as article page filename."""
    import hashlib
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:12]


def esc(text: object) -> str:
    """HTML-escape any value to prevent XSS."""
    return _html_lib.escape(str(text), quote=True)


# Language directory mapping — used to build cross-language links
LANG_DIRS: dict[str, str] = {
    "en": "",      # root (default language)
    "ar": "ar/",
    "fr": "fr/",
    "es": "es/",
    "tr": "tr/",
}
LANG_LABELS: dict[str, str] = {
    "en": "EN", "ar": "AR", "fr": "FR", "es": "ES", "tr": "TR",
}

# Cross-language slug equivalency map.
# Each entry maps a slug to its equivalent slug in every language.
# None → no direct equivalent; fall back to world.html (region) or index.html (category).
_SLUG_XMAP: dict[str, dict[str, str | None]] = {
    # ── North Africa / Morocco region ────────────────────────────────────────
    "morocco":         {"ar": "morocco",    "en": "n-africa-en", "fr": "n-africa-fr", "es": "n-africa-es", "tr": "n-africa-tr"},
    "n-africa-en":     {"ar": "morocco",    "en": "n-africa-en", "fr": "n-africa-fr", "es": "n-africa-es", "tr": "n-africa-tr"},
    "n-africa-fr":     {"ar": "morocco",    "en": "n-africa-en", "fr": "n-africa-fr", "es": "n-africa-es", "tr": "n-africa-tr"},
    "n-africa-es":     {"ar": "morocco",    "en": "n-africa-en", "fr": "n-africa-fr", "es": "n-africa-es", "tr": "n-africa-tr"},
    "n-africa-tr":     {"ar": "morocco",    "en": "n-africa-en", "fr": "n-africa-fr", "es": "n-africa-es", "tr": "n-africa-tr"},
    # ── Europe ───────────────────────────────────────────────────────────────
    "europe":          {"ar": "europe",     "en": "europe-en",   "fr": "europe-fr",   "es": "europe-es",   "tr": "europe-tr"},
    "europe-en":       {"ar": "europe",     "en": "europe-en",   "fr": "europe-fr",   "es": "europe-es",   "tr": "europe-tr"},
    "europe-fr":       {"ar": "europe",     "en": "europe-en",   "fr": "europe-fr",   "es": "europe-es",   "tr": "europe-tr"},
    "europe-es":       {"ar": "europe",     "en": "europe-en",   "fr": "europe-fr",   "es": "europe-es",   "tr": "europe-tr"},
    "europe-tr":       {"ar": "europe",     "en": "europe-en",   "fr": "europe-fr",   "es": "europe-es",   "tr": "europe-tr"},
    # ── Asia ─────────────────────────────────────────────────────────────────
    "asia":            {"ar": "asia",       "en": "asia-en",     "fr": "asia-fr",     "es": "asia-es",     "tr": "asia-tr"},
    "asia-en":         {"ar": "asia",       "en": "asia-en",     "fr": "asia-fr",     "es": "asia-es",     "tr": "asia-tr"},
    "asia-fr":         {"ar": "asia",       "en": "asia-en",     "fr": "asia-fr",     "es": "asia-es",     "tr": "asia-tr"},
    "asia-es":         {"ar": "asia",       "en": "asia-en",     "fr": "asia-fr",     "es": "asia-es",     "tr": "asia-tr"},
    "asia-tr":         {"ar": "asia",       "en": "asia-en",     "fr": "asia-fr",     "es": "asia-es",     "tr": "asia-tr"},
    # ── Africa ───────────────────────────────────────────────────────────────
    "africa":          {"ar": "africa",     "en": "africa-en",   "fr": "afrique-fr",  "es": "africa-es",   "tr": "africa-tr"},
    "africa-en":       {"ar": "africa",     "en": "africa-en",   "fr": "afrique-fr",  "es": "africa-es",   "tr": "africa-tr"},
    "afrique-fr":      {"ar": "africa",     "en": "africa-en",   "fr": "afrique-fr",  "es": "africa-es",   "tr": "africa-tr"},
    "africa-es":       {"ar": "africa",     "en": "africa-en",   "fr": "afrique-fr",  "es": "africa-es",   "tr": "africa-tr"},
    "africa-tr":       {"ar": "africa",     "en": "africa-en",   "fr": "afrique-fr",  "es": "africa-es",   "tr": "africa-tr"},
    # ── Americas ─────────────────────────────────────────────────────────────
    "americas":        {"ar": "americas",   "en": "americas-en", "fr": "ameriques-fr","es": "latam-es",    "tr": "americas-tr"},
    "americas-en":     {"ar": "americas",   "en": "americas-en", "fr": "ameriques-fr","es": "latam-es",    "tr": "americas-tr"},
    "ameriques-fr":    {"ar": "americas",   "en": "americas-en", "fr": "ameriques-fr","es": "latam-es",    "tr": "americas-tr"},
    "latam-es":        {"ar": "americas",   "en": "americas-en", "fr": "ameriques-fr","es": "latam-es",    "tr": "americas-tr"},
    "americas-tr":     {"ar": "americas",   "en": "americas-en", "fr": "ameriques-fr","es": "latam-es",    "tr": "americas-tr"},
    # ── Middle East ──────────────────────────────────────────────────────────
    "middleeast":      {"ar": "middleeast", "en": "mideast-en",  "fr": "moyen-orient-fr","es": "mideast-es","tr": "mideast-tr"},
    "mideast-en":      {"ar": "middleeast", "en": "mideast-en",  "fr": "moyen-orient-fr","es": "mideast-es","tr": "mideast-tr"},
    "moyen-orient-fr": {"ar": "middleeast", "en": "mideast-en",  "fr": "moyen-orient-fr","es": "mideast-es","tr": "mideast-tr"},
    "mideast-es":      {"ar": "middleeast", "en": "mideast-en",  "fr": "moyen-orient-fr","es": "mideast-es","tr": "mideast-tr"},
    "mideast-tr":      {"ar": "middleeast", "en": "mideast-en",  "fr": "moyen-orient-fr","es": "mideast-es","tr": "mideast-tr"},
    # ── Language-specific regions (→ world.html in other languages) ──────────
    "islamic":         {"ar": "islamic",    "en": None,          "fr": None,          "es": None,          "tr": None},
    "diaspora":        {"ar": "diaspora",   "en": None,          "fr": None,          "es": None,          "tr": None},
    "france-fr":       {"ar": None,         "en": None,          "fr": "france-fr",   "es": None,          "tr": None},
    "espana-es":       {"ar": None,         "en": None,          "fr": None,          "es": "espana-es",   "tr": None},
    "turkey":          {"ar": None,         "en": None,          "fr": None,          "es": None,          "tr": "turkey"},
    "uk-en":           {"ar": None,         "en": "uk-en",       "fr": None,          "es": None,          "tr": None},
    "us-en":           {"ar": None,         "en": "us-en",       "fr": None,          "es": None,          "tr": None},
    # ── Main categories only in some languages (→ index.html elsewhere) ──────
    "society":         {"ar": "society",    "en": None,          "fr": None,          "es": None,          "tr": None},
    "science":         {"ar": None,         "en": "science",     "fr": "science",     "es": "science",     "tr": "science"},
    # ── New universal categories (same slug in all languages) ─────────────────
    "environment":     {"ar": "environment","en": "environment", "fr": "environment", "es": "environment", "tr": "environment"},
    "business":        {"ar": "business",   "en": "business",    "fr": "business",    "es": "business",    "tr": "business"},
    "travel":          {"ar": "travel",     "en": "travel",      "fr": "travel",      "es": "travel",      "tr": "travel"},
}

# Slugs that are world-region pages (fallback = world.html when no equivalent)
_REGION_SLUG_SET: frozenset[str] = frozenset({
    "morocco","middleeast","islamic","diaspora","asia","americas","europe","africa",
    "n-africa-en","europe-en","asia-en","africa-en","americas-en","mideast-en","uk-en","us-en",
    "n-africa-fr","europe-fr","asia-fr","afrique-fr","ameriques-fr","moyen-orient-fr","france-fr",
    "n-africa-es","europe-es","asia-es","africa-es","latam-es","mideast-es","espana-es",
    "n-africa-tr","europe-tr","asia-tr","africa-tr","americas-tr","mideast-tr","turkey",
})


def _xslug(slug: str, target_lang: str) -> str:
    """Return the correct .html filename for *slug* in *target_lang*.

    Consults _SLUG_XMAP for language-specific equivalents.
    Falls back to world.html (region) or index.html (main category) when
    no direct equivalent exists.
    """
    if slug in _SLUG_XMAP:
        target = _SLUG_XMAP[slug].get(target_lang)
        if target:
            return f"{target}.html"
        # No equivalent
        return "world.html" if slug in _REGION_SLUG_SET else "index.html"
    # Standard slug identical across all languages
    return f"{slug}.html"


def _lang_switcher(current_lang: str, page_file: str) -> str:
    """Build a compact multi-language switcher for the site header.

    Always links to the homepage (index.html) of the target language.
    """
    items = ""
    for lang, prefix in LANG_DIRS.items():
        label = LANG_LABELS[lang]
        if lang == current_lang:
            items += f'<span class="lang-btn current">{label}</span>'
        else:
            if current_lang == "en":
                href = f"{prefix}index.html"     # root → subdir/index.html
            elif lang == "en":
                href = "../index.html"           # subdir → root/index.html
            else:
                href = f"../{prefix}index.html"  # subdir → ../other/index.html
            items += f'<a href="{href}" class="lang-btn">{label}</a>'
    return f'<div class="lang-switcher">{items}</div>'


def _prices_main_html(market_data: dict,
                      pairs: list[tuple[str, str]] = None,
                      s: dict = None) -> str:
    """Build the main content HTML for prices.html (language-aware).

    Sections: Exchange Rates | Metals | Oil & Energy | Commodities
    All data comes from market_data (fetched at build time, no JS).
    """
    if s is None:
        s = STRINGS["ar"]
    if pairs is None:
        pairs = DEFAULT_MARKET_PAIRS

    lang = s.get("lang", "ar")
    rates = market_data.get("rates", {})
    ts    = market_data.get("ts", "")
    ts_html = f'<p class="prices-ts">🕒 {esc(s["prices_updated"])}: {esc(ts)}</p>' if ts else ""

    # ── 1. Exchange rates table ───────────────────────────────────────────────
    fx_rows = ""
    for code, _label in pairs:
        val = rates.get(code)
        if val is None:
            continue
        meta = CURRENCY_META.get(code, {})
        name = meta.get(lang, meta.get("ar", code))
        flag = meta.get("flag", "")
        fx_rows += (
            f'<tr>'
            f'<td class="ptd-flag">{flag}</td>'
            f'<td><span class="ptd-name">{esc(name)}</span>'
            f' <span class="ptd-code">{esc(code)}</span></td>'
            f'<td class="ptd-val">{val:.4g}'
            f' <span class="ptd-base">{esc(code)}</span></td>'
            f'<td class="ptd-base">1 USD</td>'
            f'</tr>\n'
        )
    if fx_rows:
        fx_table = (
            f'<table class="prices-table">'
            f'<thead><tr>'
            f'<th></th><th>{esc(s["prices_col_currency"])}</th>'
            f'<th>{esc(s["prices_col_price"])}</th>'
            f'<th>{esc(s["prices_col_compare"])}</th>'
            f'</tr></thead>'
            f'<tbody>{fx_rows}</tbody>'
            f'</table>'
            f'{ts_html}'
        )
    else:
        fx_table = f'<div class="prices-coming">{esc(s["prices_fx_error"])}</div>'

    # ── 2. Metals table ───────────────────────────────────────────────────────
    metal_rows = ""
    for code, metal in METAL_META.items():
        usd_per_oz: float | None = None
        oz_per_usd = rates.get(code)
        if oz_per_usd and oz_per_usd > 0:
            usd_per_oz = round(1.0 / float(oz_per_usd), 2)
        elif code == "XAU" and market_data.get("gold"):
            usd_per_oz = float(market_data["gold"])
        if usd_per_oz:
            metal_name = metal.get(lang, metal.get("ar", code))
            icon = metal.get("icon", "")
            metal_rows += (
                f'<tr>'
                f'<td class="ptd-flag">{icon}</td>'
                f'<td><span class="ptd-name">{esc(metal_name)}</span>'
                f' <span class="ptd-code">{esc(code)}</span></td>'
                f'<td class="ptd-val">${usd_per_oz:,.2f}'
                f' <span class="ptd-base">{esc(s["prices_oz_unit"])}</span></td>'
                f'<td class="ptd-base">Troy Oz</td>'
                f'</tr>\n'
            )
    if metal_rows:
        metals_table = (
            f'<table class="prices-table">'
            f'<thead><tr>'
            f'<th></th><th>{esc(s["prices_col_metal"])}</th>'
            f'<th>{esc(s["prices_col_price"])} (USD)</th>'
            f'<th>{esc(s["prices_col_unit"])}</th>'
            f'</tr></thead>'
            f'<tbody>{metal_rows}</tbody>'
            f'</table>'
            f'{ts_html}'
        )
    else:
        metals_table = f'<div class="prices-coming">{esc(s["prices_metals_hint"])}</div>'

    # ── 3. Oil & Energy table ─────────────────────────────────────────────────
    oil_rows = ""
    if market_data.get("oil"):
        oil_rows += (
            f'<tr>'
            f'<td class="ptd-flag">🛢️</td>'
            f'<td><span class="ptd-name">{esc(s["prices_brent_name"])}</span>'
            f' <span class="ptd-code">BRENT</span></td>'
            f'<td class="ptd-val">${market_data["oil"]:.2f}'
            f' <span class="ptd-base">{esc(s["prices_bbl_unit"])}</span></td>'
            f'<td class="ptd-base">USD/bbl</td>'
            f'</tr>\n'
        )
    if oil_rows:
        oil_table = (
            f'<table class="prices-table">'
            f'<thead><tr>'
            f'<th></th><th>{esc(s["prices_col_type"])}</th>'
            f'<th>{esc(s["prices_col_price"])} (USD)</th>'
            f'<th>{esc(s["prices_col_unit"])}</th>'
            f'</tr></thead>'
            f'<tbody>{oil_rows}</tbody>'
            f'</table>'
        )
    else:
        oil_table = f'<div class="prices-coming">{esc(s["prices_oil_hint"])}</div>'

    # ── 4. Commodities (coming soon) ──────────────────────────────────────────
    commodities_table = f'<div class="prices-coming">{esc(s["prices_commodities_soon"])}</div>'

    # ── Section wrapper helper ────────────────────────────────────────────────
    def _section(icon: str, title: str, content: str, color: str = "#059669") -> str:
        return (
            f'<div class="prices-section">'
            f'<div class="prices-section-header" style="border-inline-start-color:{color}">'
            f'<span class="section-icon">{icon}</span>'
            f'<h2 class="prices-section-title">{esc(title)}</h2>'
            f'</div>'
            f'{content}'
            f'</div>'
        )

    breadcrumb = (
        f'<div class="breadcrumb">'
        f'<a href="index.html">{esc(s["home"])}</a>'
        f'<span class="bc-sep">›</span>'
        f'<a href="economy.html">{esc(s.get("prices_economy_bc", "Economy"))}</a>'
        f'<span class="bc-sep">›</span>'
        f'<span>{esc(s.get("prices_prices_bc", "Prices"))}</span>'
        f'</div>'
    )

    return (
        breadcrumb
        + _section("💱", s["prices_fx_hdr"],           fx_table,          "#059669")
        + '<div class="prices-grid">'
        + _section("🥇", s["prices_metals_hdr"],        metals_table,      "#d97706")
        + _section("🛢️", s["prices_oil_hdr"],          oil_table,         "#6b7280")
        + '</div>'
        + _section("🌾", s["prices_commodities_hdr"],   commodities_table, "#16a34a")
    )


def safe_url(url: str) -> str:
    """Return HTML-escaped URL only for http/https schemes; else return '#'."""
    stripped = str(url).strip()
    if stripped.startswith("http://") or stripped.startswith("https://"):
        return esc(stripped)
    return "#"


# ──────────────────────────────────────────────────────────────────────────────
# STATIC ASSET STRINGS
# These are written once to static/ so they can be cached by browsers.
# ──────────────────────────────────────────────────────────────────────────────

STYLE_CSS = """\
/* ===================== RESET ===================== */
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}

/* ===================== VARIABLES ===================== */
:root{
  --bg:linear-gradient(180deg, #faf5ff 0%, #f0f9ff 30%, #f8fafc 100%);
  --bg-flat:#f8f9fe;
  --surface:#ffffff;
  --surface-2:#f1f5f9;
  --glass:rgba(255,255,255,.75);
  --text:#1e293b;
  --text-muted:#64748b;
  --text-light:#94a3b8;
  --header-start:#4f46e5;
  --header-end:#7c3aed;
  --nav-bg:rgba(255,255,255,.92);
  --nav-text:#475569;
  --nav-active:#6366f1;
  --breaking-bg:linear-gradient(90deg, #ef4444, #f97316);
  --border:#e2e8f0;
  --card-shadow:0 2px 12px rgba(0,0,0,.06);
  --card-shadow-hover:0 12px 32px rgba(99,102,241,.15);
  --accent:#6366f1;
  --footer-bg:#1e1b4b;
  --footer-text:#a5b4fc;
  --radius:16px;
}
body.dark-mode{
  --bg:linear-gradient(180deg, #0f0a1e 0%, #1a1040 100%);
  --bg-flat:#0f0a1e;
  --surface:#1e1b3a;
  --surface-2:#2a2654;
  --glass:rgba(30,27,58,.8);
  --text:#e2e8f0;
  --text-muted:#a5b4fc;
  --text-light:#7c7cb0;
  --nav-bg:rgba(30,27,58,.95);
  --nav-text:#c7d2fe;
  --border:#312e81;
  --card-shadow:0 2px 12px rgba(0,0,0,.25);
  --card-shadow-hover:0 12px 32px rgba(99,102,241,.25);
}

/* ===================== BASE ===================== */
body{background:var(--bg-flat);background-image:var(--bg);color:var(--text);line-height:1.7;min-height:100vh}
body.lang-rtl{direction:rtl;font-family:'Cairo','Segoe UI',Tahoma,system-ui,sans-serif}
body.lang-ltr{direction:ltr;font-family:'Roboto','Segoe UI',Arial,system-ui,sans-serif}
a{text-decoration:none;color:inherit}
ul,ol{list-style:none}

/* ===================== STICKY WRAPPER ===================== */
.sticky-header{position:sticky;top:0;z-index:500}

/* ===================== SITE HEADER (merged) ===================== */
.site-header{background:linear-gradient(135deg,var(--header-start),var(--header-end));color:#fff;padding:9px 0;position:relative;overflow:hidden}
.site-header::before{content:'';position:absolute;inset:0;background:repeating-linear-gradient(90deg,rgba(255,255,255,.04) 0,rgba(255,255,255,.04) 1px,transparent 1px,transparent 60px);pointer-events:none}
.site-header-inner{max-width:1200px;margin:0 auto;padding:0 20px;display:flex;justify-content:space-between;align-items:center;gap:16px;position:relative}
.header-start{display:flex;align-items:center;gap:9px;flex-shrink:0}
.header-end{display:flex;align-items:center;gap:12px;flex-shrink:0}
.top-date{color:#fff;font-weight:800;font-size:1em;letter-spacing:.5px;text-shadow:0 1px 4px rgba(0,0,0,.3)}
.live-dot{display:inline-block;width:8px;height:8px;background:#4ade80;border-radius:50%;animation:pulse-dot 2s ease infinite;flex-shrink:0}
.live-time{color:rgba(255,255,255,.75);font-size:.88em;font-weight:600;font-variant-numeric:tabular-nums;letter-spacing:.5px}
@keyframes pulse-dot{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.7)}}
.site-header-title{font-size:1.3em;font-weight:900;letter-spacing:3px;text-shadow:0 2px 12px rgba(0,0,0,.3);white-space:nowrap}
.theme-btn{background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.25);color:#fff;cursor:pointer;padding:6px 16px;border-radius:20px;font-size:.95em;transition:all .2s}
.theme-btn:hover{background:rgba(255,255,255,.25);border-color:rgba(255,255,255,.5)}

/* ===================== NAVIGATION ===================== */
.site-nav{background:var(--nav-bg);position:relative;z-index:200;box-shadow:0 1px 8px rgba(0,0,0,.07);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);overflow:hidden}
.nav-inner{max-width:1200px;margin:0 auto;padding:0 6px;display:flex;flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;gap:1px;scroll-behavior:smooth}
.nav-inner::-webkit-scrollbar{display:none}
.nav-tab{display:inline-flex;align-items:center;gap:4px;color:var(--nav-text);padding:8px 10px;font-size:.84em;white-space:nowrap;border-bottom:3px solid transparent;transition:all .2s;font-weight:700;cursor:pointer;border-radius:6px 6px 0 0;flex-shrink:0;min-width:0}
.nav-tab:hover{color:var(--accent);background:rgba(99,102,241,.05)}
.nav-tab.active{color:var(--accent);border-bottom-color:var(--accent);background:rgba(99,102,241,.08)}

/* ===================== SEARCH BAR ===================== */
.search-bar{background:var(--nav-bg);border-bottom:1px solid var(--border);overflow:hidden;max-height:0;transition:max-height .3s ease,padding .3s ease;padding:0 10px}
.search-bar.open{max-height:64px;padding:10px 10px}
.search-bar-inner{max-width:1200px;margin:0 auto;position:relative}
.search-input{width:100%;padding:8px 36px 8px 14px;border-radius:8px;border:1.5px solid var(--border);background:var(--card-bg);color:var(--text);font-size:.93em;font-family:inherit;outline:none;transition:border-color .2s}
.search-input:focus{border-color:var(--accent)}
.search-clear{position:absolute;inset-inline-end:10px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:1.1em;line-height:1;padding:2px}
.search-no-results{display:none;padding:30px 20px;text-align:center;color:var(--text-muted);font-size:.95rem}
.search-no-results.visible{display:block}
.search-count{font-size:.75em;color:var(--text-muted);margin-inline-start:8px;font-weight:600}

/* ===================== WORLD REGIONS SUBNAV ===================== */
.world-subnav{background:var(--nav-bg);border-top:1px solid var(--border);border-bottom:2px solid var(--accent);backdrop-filter:blur(12px)}
.world-subnav-inner{max-width:1200px;margin:0 auto;padding:0 10px;display:flex;overflow-x:auto;scrollbar-width:none;gap:1px}
.world-subnav-inner::-webkit-scrollbar{display:none}
.world-region-btn{display:inline-flex;align-items:center;gap:4px;color:#111;padding:9px 15px;font-size:.9em;white-space:nowrap;border-bottom:3px solid transparent;transition:all .2s;font-weight:800;cursor:pointer;border-radius:6px 6px 0 0;flex-shrink:0;opacity:0;animation:btn-drop .38s ease forwards}
.world-region-btn:hover{color:var(--accent);background:rgba(99,102,241,.06);border-bottom-color:rgba(99,102,241,.3)}
.world-region-btn.active-region{color:var(--accent);border-bottom-color:var(--accent);background:rgba(99,102,241,.09)}
.dark-mode .world-region-btn{color:#e2e8f0}
.dark-mode .world-region-btn:hover{color:#a5b4fc}
.dark-mode .world-region-btn.active-region{color:#a5b4fc}
@keyframes btn-drop{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
.world-region-btn:nth-child(1){animation-delay:.04s}
.world-region-btn:nth-child(2){animation-delay:.09s}
.world-region-btn:nth-child(3){animation-delay:.14s}
.world-region-btn:nth-child(4){animation-delay:.19s}
.world-region-btn:nth-child(5){animation-delay:.24s}
.world-region-btn:nth-child(6){animation-delay:.29s}
.world-region-btn:nth-child(7){animation-delay:.34s}
.world-region-btn:nth-child(8){animation-delay:.39s}
.world-region-btn.live-btn{color:#dc2626;border-bottom-color:transparent}
.world-region-btn.live-btn:hover{color:#b91c1c;background:rgba(220,38,38,.07);border-bottom-color:rgba(220,38,38,.35)}
.world-region-btn.live-btn.active-region{color:#dc2626;border-bottom-color:#dc2626;background:rgba(220,38,38,.09)}
.dark-mode .world-region-btn.live-btn{color:#f87171}
.dark-mode .world-region-btn.live-btn.active-region{color:#f87171;border-bottom-color:#f87171}

/* ===================== LIVE TV PAGE ===================== */
.live-page-hdr{display:flex;align-items:center;gap:14px;padding:20px 0 6px;margin-bottom:24px;border-bottom:2px solid var(--border)}
.live-page-hdr-icon{font-size:2.2em;line-height:1}
.live-page-hdr h1{font-size:1.45em;font-weight:900;margin:0 0 4px;letter-spacing:-.3px}
.live-page-hdr p{font-size:.9em;color:var(--text-muted);margin:0}
.live-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;margin-top:8px}
.live-card{border-radius:var(--radius);background:var(--surface);border:1px solid var(--border);box-shadow:var(--card-shadow);overflow:hidden;display:flex;flex-direction:column;align-items:center;padding:22px 16px 18px;gap:10px;text-align:center;transition:transform .25s,box-shadow .25s;animation:cardIn .42s ease both}
.live-card:hover{transform:translateY(-4px);box-shadow:var(--card-shadow-hover)}
.live-card-flag{font-size:2.4em;line-height:1;filter:drop-shadow(0 2px 4px rgba(0,0,0,.18))}
.live-card-name{font-size:1em;font-weight:800;color:var(--text);line-height:1.3}
.live-badge{display:inline-flex;align-items:center;gap:5px;background:#fee2e2;color:#b91c1c;font-size:.72em;font-weight:800;padding:3px 9px;border-radius:20px;letter-spacing:.4px;margin-top:2px}
.live-badge-dot{display:inline-block;width:7px;height:7px;background:#dc2626;border-radius:50%;animation:pulse-dot 1.6s ease infinite;flex-shrink:0}
.dark-mode .live-badge{background:rgba(220,38,38,.18);color:#fca5a5}
.live-watch-btn{display:inline-flex;align-items:center;gap:6px;margin-top:6px;padding:8px 18px;background:var(--accent);color:#fff;border-radius:22px;font-size:.85em;font-weight:700;text-decoration:none;transition:background .2s,transform .15s;white-space:nowrap}
.live-watch-btn:hover{background:#4f46e5;transform:scale(1.04)}
.dark-mode .live-watch-btn{background:#6366f1}
@media(max-width:900px){.live-grid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.live-grid{grid-template-columns:repeat(2,1fr)}.live-card{padding:16px 10px 14px}.live-card-flag{font-size:2em}}
@media(max-width:380px){.live-grid{grid-template-columns:1fr}}

/* ===================== MAIN LAYOUT ===================== */
.main-wrapper{max-width:1200px;margin:0 auto;padding:24px 20px}

/* ===================== CATEGORY SECTIONS ===================== */
.content-area{min-width:0}
.category-section{margin-bottom:44px;scroll-margin-top:60px}
.section-header{display:flex;align-items:center;gap:12px;padding:14px 20px;margin-bottom:20px;background:var(--surface);border-radius:var(--radius);border-inline-start:5px solid #888;box-shadow:var(--card-shadow);position:relative;overflow:hidden}
.section-header::after{content:'';position:absolute;left:0;top:0;bottom:0;width:40%;background:linear-gradient(90deg,rgba(99,102,241,.04),transparent);pointer-events:none}
.section-icon{font-size:1.5em}
.section-title{font-size:1.3em;font-weight:800;letter-spacing:-.3px}
.section-title-link{color:inherit;text-decoration:none;transition:color .15s}
.section-title-link:hover{color:var(--accent)}

/* ===================== ARTICLES GRID ===================== */
.articles-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}

/* ===================== ARTICLE CARD ===================== */
@keyframes cardIn{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
.article-card{border-radius:var(--radius);overflow:hidden;box-shadow:var(--card-shadow);transition:transform .3s cubic-bezier(.4,0,.2,1),box-shadow .3s;border:1px solid var(--border);animation:cardIn .42s ease both;aspect-ratio:4/3;position:relative;background:#1a2744;display:grid;grid-template-rows:1fr}
.article-card:nth-child(2){animation-delay:.07s}
.article-card:nth-child(3){animation-delay:.14s}
.article-card:nth-child(4){animation-delay:.21s}
.article-card:nth-child(5){animation-delay:.07s}
.article-card:nth-child(6){animation-delay:.14s}
.article-card:nth-child(7){animation-delay:.21s}
.article-card:nth-child(8){animation-delay:.28s}
.article-card:hover{transform:translateY(-4px);box-shadow:var(--card-shadow-hover)}
.card-link{display:block;grid-area:1/1;position:relative;min-height:0;color:inherit;text-decoration:none}
.card-bg{position:absolute;inset:0;overflow:hidden}
.card-bg-img{width:100%;height:100%;object-fit:cover;object-position:center top;display:block;transition:transform .5s ease}
.article-card:hover .card-bg-img{transform:scale(1.07)}
.card-no-img{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:3.5em;opacity:.2}
.card-overlay{position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.92) 0%,rgba(0,0,0,.55) 42%,rgba(0,0,0,.1) 72%,transparent 100%);pointer-events:none}
.card-body{position:absolute;bottom:0;left:0;right:0;padding:12px 14px 15px;display:flex;flex-direction:column;gap:7px}
.card-meta{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:4px}
.card-source{font-size:.74em;font-weight:700;padding:2px 9px;border-radius:20px;color:#fff;white-space:nowrap;max-width:140px;overflow:hidden;text-overflow:ellipsis;background:rgba(255,255,255,.18);backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,.2)}
.card-date{font-size:.72em;color:rgba(255,255,255,.75);font-weight:500}
.card-title{font-size:.95em;font-weight:800;line-height:1.5;color:#fff;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;text-shadow:0 1px 4px rgba(0,0,0,.6)}
.article-card:hover .card-title{color:#e0e7ff}
.article-card.card--no-img{background:var(--surface);border:1px solid var(--border)}
/* Hide the broken <img> element — onerror fires AFTER download attempt */
.article-card.card--no-img .card-bg{display:none}
.article-card.card--no-img .card-overlay{display:none}
.article-card.card--no-img .card-title{color:var(--text);text-shadow:none}
.article-card.card--no-img .card-date{color:var(--text-light)}
.article-card.card--no-img:hover .card-title{color:var(--accent)}
.article-card.card--no-img .card-source{background:rgba(99,102,241,.12);color:var(--text);border:1px solid var(--border)}

/* ===================== SIDEBAR ===================== */
.sidebar{position:sticky;top:66px}
.sidebar-widget{background:var(--surface);border-radius:var(--radius);padding:18px;margin-bottom:16px;border:1px solid var(--border);box-shadow:var(--card-shadow)}
.widget-title{font-size:.95em;font-weight:800;margin-bottom:14px;padding-bottom:10px;border-bottom:2px solid var(--border);color:var(--text)}
.stats-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.stat-box{background:var(--surface-2);border-radius:12px;padding:14px;text-align:center;border:1px solid var(--border)}
.stat-value{font-size:1.7em;font-weight:800;background:linear-gradient(135deg,#6366f1,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1}
.dark-mode .stat-value{background:linear-gradient(135deg,#a5b4fc,#c4b5fd);-webkit-background-clip:text;background-clip:text}
.stat-label{font-size:.78em;color:var(--text-muted);margin-top:5px;font-weight:500}
.cat-list{display:flex;flex-direction:column;gap:6px}
.cat-link{display:flex;justify-content:space-between;align-items:center;padding:10px 12px;border-radius:10px;color:var(--text);font-size:.9em;font-weight:600;border-inline-start:4px solid transparent;background:var(--surface-2);transition:all .2s}
.cat-link:hover{background:rgba(99,102,241,.08);transform:translateX(-3px)}
.cat-count{background:var(--surface);border:1px solid var(--border);color:var(--text-muted);font-size:.75em;padding:2px 9px;border-radius:12px;font-weight:600}

/* ===================== BACK TO TOP ===================== */
.back-to-top{position:fixed;bottom:24px;left:24px;width:48px;height:48px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border:none;border-radius:50%;font-size:1.2em;cursor:pointer;box-shadow:0 4px 18px rgba(99,102,241,.35);transition:all .3s;opacity:0;visibility:hidden;z-index:500;line-height:1}
.back-to-top.visible{opacity:1;visibility:visible}
.back-to-top:hover{transform:translateY(-4px);box-shadow:0 8px 25px rgba(99,102,241,.45)}

/* ===================== MORE BUTTON ===================== */
.more-btn{display:inline-flex;align-items:center;gap:6px;margin-top:16px;padding:10px 22px;border-radius:50px;border:2px solid;font-size:.92em;font-weight:700;transition:all .25s;background:transparent}
.more-btn:hover{background:var(--accent);color:#fff!important;border-color:var(--accent);transform:translateX(-4px)}

/* ===================== BREADCRUMB ===================== */
.breadcrumb{display:flex;align-items:center;gap:8px;padding:10px 0 18px;font-size:.88em;color:var(--text-muted)}
.breadcrumb a{color:var(--accent);font-weight:600}
.breadcrumb a:hover{text-decoration:underline}
.bc-sep{color:var(--text-light)}

/* ===================== EMPTY STATE ===================== */
.empty-state{text-align:center;padding:80px 20px;color:var(--text-muted);background:var(--surface);border-radius:var(--radius);border:1px solid var(--border)}
.empty-state h2{font-size:1.3em;margin-bottom:10px}

/* ===================== FOOTER ===================== */
.site-footer{background:var(--footer-bg);color:var(--footer-text);margin-top:50px;padding-top:48px;position:relative}
.site-footer::before{content:'';position:absolute;top:0;left:0;right:0;height:4px;background:linear-gradient(90deg,#6366f1,#8b5cf6,#ec4899,#f59e0b)}
.footer-inner{max-width:1200px;margin:0 auto;padding:0 20px 36px;display:grid;grid-template-columns:2fr 1.2fr 1fr 1fr;gap:28px}
.footer-brand h3{color:#fff;font-size:1.1em;margin-bottom:10px}
.footer-brand p{font-size:.85em;line-height:1.8;opacity:.8}
.footer-section h4{color:#fff;font-size:.88em;margin-bottom:14px;letter-spacing:.5px}
.footer-section ul{display:flex;flex-direction:column;gap:8px}
.footer-section a{color:var(--footer-text);font-size:.85em;transition:color .2s}
.footer-section a:hover{color:#fff}
.footer-bottom{border-top:1px solid rgba(255,255,255,.08);padding:16px 20px;text-align:center;font-size:.78em;color:rgba(165,180,252,.5)}
.footer-bottom a{color:#a5b4fc}
.footer-bottom p+p{margin-top:4px}

/* ===================== NEWS HERO CAROUSEL ===================== */
.news-hero{max-width:960px;margin:0 auto 36px;background:var(--surface);border-radius:var(--radius);overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.1);border:1px solid var(--border)}
.nh-header{padding:10px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center}
.nh-label{font-size:.72em;font-weight:800;color:var(--text-muted);letter-spacing:2px;text-transform:uppercase}
.nh-body{display:grid;grid-template-columns:1fr 290px}
.nh-main{position:relative;overflow:hidden;background:#111}
.nh-slides{position:relative;width:100%;aspect-ratio:16/9}
.nh-slide{position:absolute;inset:0;opacity:0;transition:opacity .55s ease;pointer-events:none;will-change:opacity}
.nh-slide.active{opacity:1;pointer-events:auto;z-index:2}
.nh-slide a{display:block;width:100%;height:100%;color:inherit;text-decoration:none;position:relative}
.nh-img{width:100%;height:100%;object-fit:cover;display:block;transition:transform 8s ease}
.nh-slide.active .nh-img{transform:scale(1.04)}
.nh-overlay{position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.9) 0%,rgba(0,0,0,.3) 50%,transparent 100%);pointer-events:none}
.nh-text{position:absolute;bottom:0;left:0;right:0;padding:44px 20px 18px;direction:rtl}
.nh-badge{display:inline-block;font-size:.7em;font-weight:800;color:#fff;padding:3px 11px;border-radius:12px;margin-bottom:8px;line-height:1.5}
.nh-title{font-size:1.18em;font-weight:900;color:#fff;line-height:1.6;text-shadow:0 2px 12px rgba(0,0,0,.5);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;margin-bottom:6px}
.nh-meta{font-size:.75em;color:rgba(255,255,255,.65);display:flex;gap:10px}
.nh-nav{position:absolute;top:36%;transform:translateY(-50%);z-index:20;background:rgba(255,255,255,.13);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border:1.5px solid rgba(255,255,255,.25);color:#fff;width:40px;height:40px;border-radius:50%;cursor:pointer;font-size:1.3em;transition:all .2s;padding:0;line-height:1}
.nh-nav:hover{background:rgba(255,255,255,.32);border-color:rgba(255,255,255,.6);transform:translateY(-50%) scale(1.08)}
.nh-prev{right:14px}
.nh-next{left:14px}
.nh-dots{position:absolute;bottom:14px;left:50%;transform:translateX(-50%);display:flex;gap:5px;z-index:20}
.nh-dot{width:7px;height:7px;border-radius:4px;background:rgba(255,255,255,.35);cursor:pointer;transition:all .3s;border:none;padding:0}
.nh-dot.active{width:24px;background:#fff}
.nh-bar{position:absolute;top:0;left:0;right:0;height:3px;background:rgba(0,0,0,.2);z-index:20}
.nh-bar-fill{height:100%;background:linear-gradient(90deg,var(--accent),#a855f7);width:0}
.nh-side{border-right:1px solid var(--border);display:flex;flex-direction:column;background:var(--surface)}
.nh-side-item{display:flex;gap:11px;padding:12px 14px;border-bottom:1px solid var(--border);text-decoration:none;color:inherit;transition:background .2s;align-items:flex-start;position:relative;flex:1}
.nh-side-item:last-child{border-bottom:none}
.nh-side-item::after{content:'';position:absolute;right:0;top:8px;bottom:8px;width:3px;background:transparent;border-radius:2px;transition:background .2s}
.nh-side-item:hover{background:rgba(99,102,241,.06)}
.nh-side-item:hover::after,.nh-side-item.active-side::after{background:var(--accent)}
.nh-side-img{width:72px;height:54px;flex-shrink:0;border-radius:8px;object-fit:cover;background:var(--surface-2);display:block;transition:transform .3s}
.nh-side-item:hover .nh-side-img{transform:scale(1.05)}
.nh-side-body{min-width:0;flex:1}
.nh-side-badge{display:inline-block;font-size:.64em;font-weight:800;color:#fff;padding:2px 8px;border-radius:8px;margin-bottom:5px;line-height:1.4}
.nh-side-title{font-size:.81em;font-weight:700;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;color:var(--text)}
.nh-side-meta{font-size:.7em;color:var(--text-muted);margin-top:3px}
@media(max-width:860px){.nh-body{grid-template-columns:1fr 220px}.nh-title{font-size:1em}}
@media(max-width:640px){.nh-body{grid-template-columns:1fr}.nh-side{display:none}}
.dark-mode .nh-nav{background:rgba(0,0,0,.4);border-color:rgba(255,255,255,.15)}
.dark-mode .nh-nav:hover{background:rgba(0,0,0,.65)}

/* ===================== ECONOMY TABS WIDGET ===================== */
.econ-widget{background:linear-gradient(90deg,#059669,#0d9488);border-bottom:2px solid rgba(0,0,0,.12);color:#fff}
.econ-tab-nav{background:rgba(0,0,0,.2)}
.econ-tab-nav-inner{max-width:1200px;margin:0 auto;padding:0 20px;display:flex;overflow-x:auto;scrollbar-width:none;white-space:nowrap}
.econ-tab-nav-inner::-webkit-scrollbar{display:none}
.econ-tab{background:none;border:none;border-bottom:3px solid transparent;color:rgba(255,255,255,.65);font-size:.83em;font-weight:700;padding:9px 18px;cursor:pointer;transition:all .2s;white-space:nowrap;font-family:inherit;letter-spacing:.2px;flex-shrink:0}
.econ-tab:hover{color:#fff;background:rgba(255,255,255,.08)}
.econ-tab.active{color:#fff;border-bottom-color:rgba(255,255,255,.85);background:rgba(255,255,255,.12)}
.econ-panels{overflow:hidden}
.econ-panel{display:none;font-size:.82em;font-weight:700}
.econ-panel.active{display:block}
.econ-soon{max-width:1200px;margin:0 auto;padding:0 24px;color:rgba(255,255,255,.6);font-size:.81em;font-style:italic;height:36px;display:flex;align-items:center;gap:6px}
.dark-mode .econ-widget{background:linear-gradient(90deg,#065f46,#0f766e)}
.dark-mode .econ-tab-nav{background:rgba(0,0,0,.3)}

/* ===================== PRICES PAGE ===================== */
.prices-section{margin-bottom:44px}
.prices-section-header{display:flex;align-items:center;gap:12px;padding:12px 20px;margin-bottom:16px;background:var(--surface);border-radius:var(--radius);border-inline-start:5px solid #059669;box-shadow:var(--card-shadow)}
.prices-section-title{font-size:1.1em;font-weight:800}
.prices-table{width:100%;border-collapse:collapse;background:var(--surface);border-radius:var(--radius);overflow:hidden;box-shadow:var(--card-shadow);border:1px solid var(--border);font-size:.88em}
.prices-table th{background:var(--surface-2);color:var(--text-muted);font-size:.78em;font-weight:700;letter-spacing:.5px;padding:10px 16px;text-align:right;border-bottom:2px solid var(--border);white-space:nowrap}
.prices-table td{padding:9px 14px;border-bottom:1px solid var(--border);color:var(--text);vertical-align:middle}
.prices-table tr:last-child td{border-bottom:none}
.prices-table tr:hover td{background:rgba(99,102,241,.04)}
.ptd-flag{font-size:1.15em}
.ptd-name{font-weight:600}
.ptd-code{color:var(--text-muted);font-size:.8em;margin-right:5px;font-family:monospace}
.ptd-val{font-weight:700;font-variant-numeric:tabular-nums;color:var(--text)}
.ptd-base{color:var(--text-muted);font-size:.8em;margin-right:4px}
.prices-coming{color:var(--text-muted);font-style:italic;font-size:.85em;padding:28px;text-align:center;background:var(--surface);border-radius:var(--radius);border:1px dashed var(--border)}
.prices-ts{font-size:.75em;color:var(--text-muted);margin-top:8px;text-align:left;direction:ltr}
.prices-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}
@media(max-width:760px){.prices-grid{grid-template-columns:1fr}}
body.lang-ltr .prices-table th{text-align:left}
body.lang-ltr .prices-section-header{border-inline-start:5px solid #059669}

/* ===================== LANGUAGE ROW ===================== */
.lang-row{max-width:1200px;margin:0 auto;padding:0 16px 6px;display:flex;justify-content:flex-end;gap:3px;align-items:center}
/* ===================== LANGUAGE SWITCHER ===================== */
.lang-switcher{display:flex;align-items:center;gap:3px}
.lang-btn{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:rgba(255,255,255,.7);padding:4px 8px;border-radius:12px;font-size:.75em;font-weight:700;text-decoration:none;transition:all .2s;letter-spacing:.6px;white-space:nowrap;line-height:1.4}
.lang-btn:hover{background:rgba(255,255,255,.22);color:#fff;border-color:rgba(255,255,255,.45)}
.lang-btn.current{background:rgba(255,255,255,.28);color:#fff;border-color:rgba(255,255,255,.55);cursor:default;pointer-events:none}

/* ===================== LTR OVERRIDES ===================== */
body.lang-ltr .more-btn:hover{transform:translateX(4px)}
body.lang-ltr .cat-link:hover{transform:translateX(3px)}
/* cat-link uses border-inline-start — no LTR override needed */
body.lang-ltr .back-to-top{left:auto;right:24px}
body.lang-ltr .nh-prev{right:auto;left:14px}
body.lang-ltr .nh-next{left:auto;right:14px}
body.lang-ltr .nh-side{border-right:none;border-left:1px solid var(--border)}
body.lang-ltr .nh-side-item::after{right:auto;left:0}
body.lang-ltr .nh-text{direction:ltr}

/* ===================== RESPONSIVE ===================== */
@media(max-width:1200px){
  .articles-grid{grid-template-columns:repeat(3,1fr)}
}
@media(max-width:900px){
  .articles-grid{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:768px){
  .articles-grid{grid-template-columns:repeat(2,1fr)}
  .footer-inner{grid-template-columns:1fr 1fr}
  /* Hide RSS section on mobile — keep brand + categories + links visible */
  .footer-rss{display:none}
  /* Header compact */
  .site-header{padding:5px 0}
  .site-header-inner{padding:0 10px;gap:8px}
  .site-header-title{font-size:1.02em;letter-spacing:1px}
  .top-date{display:none}
  .theme-btn{padding:5px 11px;font-size:.86em}
  /* Language row — compact full-width scrollable strip */
  .lang-row{padding:3px 10px 4px;justify-content:flex-start;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none;border-top:1px solid rgba(255,255,255,.12)}
  .lang-row::-webkit-scrollbar{display:none}
  .lang-btn{padding:3px 8px;font-size:.71em}
  /* Layout */
  .main-wrapper{padding:14px 10px}
  .section-header{padding:10px 14px;margin-bottom:12px}
  .section-title{font-size:1.05em}
  /* Nav: compact touch targets, smooth horizontal scroll, active indicator */
  .nav-inner{padding:0 4px}
  .nav-tab{padding:9px 11px;font-size:.82em}
  .nav-tab.active{box-shadow:inset 0 -3px 0 var(--accent)}
  /* ALL subnavs (World regions + Media) VISIBLE on mobile — compact and
     horizontally scrollable (MSN / Google News style). Applies to both the
     homepage world-subnav AND region/media page subnavs. */
  .world-subnav{position:relative}
  .world-subnav-inner{padding:0 8px;-webkit-overflow-scrolling:touch}
  .world-region-btn{padding:7px 11px;font-size:.8em}
  /* Right-edge fade hint on the subnav — signals horizontal scrollability.
     Placed on .world-subnav (the relative parent), NOT on the scrolling inner. */
  .world-subnav::after{content:'';position:absolute;top:0;bottom:2px;width:26px;pointer-events:none;z-index:1}
  body.lang-ltr .world-subnav::after{right:0;background:linear-gradient(90deg,transparent,var(--nav-bg))}
  body.lang-rtl .world-subnav::after{left:0;background:linear-gradient(270deg,transparent,var(--nav-bg))}
}
@media(max-width:480px){
  .articles-grid{grid-template-columns:1fr}
  .article-card{aspect-ratio:16/9}
  .card-title{font-size:1em}
  .live-time{display:none}
  .section-header{padding:8px 12px}
  .category-section{margin-bottom:28px}
  /* Nav tabs compact on very small screens */
  .nav-tab{padding:9px 10px;font-size:.8em}
  .footer-inner{grid-template-columns:1fr}
}
/* ── 360px: very small phones (Galaxy A / older Androids) ──────────────────── */
@media(max-width:360px){
  html{font-size:14px}
  .site-header-title{font-size:.92em;letter-spacing:1px}
  .card-title{font-size:.9em}
  .nav-tab{font-size:.76em;padding:8px 8px}
  .lang-btn{padding:2px 6px;font-size:.68em}
  .section-title{font-size:1em}
  .more-btn{font-size:.8em;padding:7px 14px}
}
/* ── 320px: iPhone SE 1st gen / Galaxy A02 ─────────────────────────────────── */
@media(max-width:320px){
  html{font-size:13px}
  .site-header-inner{padding:0 8px;gap:6px}
  .site-header-title{font-size:.85em;letter-spacing:.5px}
  .card-title{font-size:.85em;-webkit-line-clamp:2}
  .articles-grid{gap:10px}
  .main-wrapper{padding:10px 8px}
  .lang-row{padding:3px 8px}
}
/* ── iOS safe-area-inset: notch / Dynamic Island / home bar ─────────────────── */
@supports(padding-top:env(safe-area-inset-top)){
  .sticky-header{padding-top:env(safe-area-inset-top)}
  .back-to-top{bottom:calc(24px + env(safe-area-inset-bottom))}
  .cookie-banner{padding-bottom:calc(14px + env(safe-area-inset-bottom))}
}

/* ====== SOURCE FILTER STRIP ====== */
.src-strip{margin:0 0 18px}
.src-chips{
  display:flex;gap:7px;overflow-x:auto;scrollbar-width:none;
  padding:2px 0 10px;align-items:center;flex-wrap:nowrap
}
.src-chips::-webkit-scrollbar{display:none}
.src-chip{
  display:inline-flex;align-items:center;gap:5px;
  padding:5px 15px;border-radius:20px;
  border:1.5px solid color-mix(in srgb,var(--sc-color,#6366f1) 28%,transparent);
  background:color-mix(in srgb,var(--sc-color,#6366f1) 7%,#fff);
  color:color-mix(in srgb,var(--sc-color,#6366f1) 75%,#1e293b);
  font-size:.92rem;font-weight:700;white-space:nowrap;
  cursor:pointer;transition:all .18s ease;flex-shrink:0;
  letter-spacing:.01em;line-height:1.35;user-select:none
}
.src-chip:hover{
  background:color-mix(in srgb,var(--sc-color,#6366f1) 14%,#fff);
  border-color:color-mix(in srgb,var(--sc-color,#6366f1) 55%,transparent);
  transform:translateY(-1px);
  box-shadow:0 3px 10px color-mix(in srgb,var(--sc-color,#6366f1) 18%,transparent)
}
.src-chip.sc-active{
  background:var(--sc-color,#6366f1);
  border-color:var(--sc-color,#6366f1);
  color:#fff;
  box-shadow:0 3px 12px color-mix(in srgb,var(--sc-color,#6366f1) 38%,transparent)
}
.sc-n{
  font-size:.74em;font-weight:700;line-height:1.4;
  padding:1px 7px;border-radius:10px;
  background:rgba(255,255,255,.28)
}
.src-chip:not(.sc-active) .sc-n{
  background:color-mix(in srgb,var(--sc-color,#6366f1) 13%,transparent);
  color:var(--sc-color,#6366f1)
}
.article-card.sc-hidden{display:none}
@keyframes scIn{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
.sc-anim .article-card:not(.sc-hidden){animation:scIn .2s ease both}
.src-empty{
  display:none;padding:44px 20px;text-align:center;
  color:var(--text-muted);font-size:1rem
}
.src-empty.sc-show{display:block}
.dark-mode .src-chip{
  background:color-mix(in srgb,var(--sc-color,#818cf8) 10%,#0f172a);
  border-color:color-mix(in srgb,var(--sc-color,#818cf8) 25%,transparent);
  color:color-mix(in srgb,var(--sc-color,#818cf8) 88%,#e2e8f0)
}
.dark-mode .src-chip:hover{
  background:color-mix(in srgb,var(--sc-color,#818cf8) 18%,#0f172a)
}
.dark-mode .src-chip:not(.sc-active) .sc-n{
  background:color-mix(in srgb,var(--sc-color,#818cf8) 16%,transparent);
  color:var(--sc-color,#818cf8)
}

/* ====== GDPR COOKIE BANNER ====== */
.cookie-banner{
  position:fixed;bottom:0;left:0;right:0;z-index:9998;
  background:#1e293b;color:#f1f5f9;
  padding:14px 20px;
  box-shadow:0 -4px 24px rgba(0,0,0,.35);
  border-top:3px solid #3b82f6;
  transform:translateY(110%);
  transition:transform .4s cubic-bezier(.16,1,.3,1);
  will-change:transform;
}
.cookie-banner.cb-visible{transform:translateY(0)}
.cookie-inner{
  max-width:1100px;margin:0 auto;
  display:flex;align-items:center;gap:14px;flex-wrap:wrap;
}
.cookie-text{display:flex;flex-direction:column;gap:3px;flex:1;min-width:220px}
.cookie-text strong{font-size:.9em;font-weight:700;line-height:1.3}
.cookie-text span{font-size:.78em;opacity:.78;line-height:1.4}
.cookie-actions{
  display:flex;align-items:center;gap:10px;flex-shrink:0;flex-wrap:wrap
}
.cookie-policy-link{
  font-size:.78em;color:#93c5fd;text-decoration:underline;white-space:nowrap
}
.cookie-btn{
  padding:8px 20px;border:none;border-radius:7px;
  cursor:pointer;font-size:.82em;font-weight:600;
  transition:opacity .15s,background .15s;
  white-space:nowrap;
}
.cookie-btn:hover{opacity:.88}
.cookie-accept{background:#3b82f6;color:#fff}
.cookie-reject{background:transparent;color:#94a3b8;border:1px solid #475569}
.cookie-reject:hover{background:#334155;color:#e2e8f0}
.cookie-customize{background:transparent;color:#93c5fd;border:1px solid #334155;font-size:.78em;padding:7px 14px}
.cookie-customize:hover{background:#1e3a5f;color:#bfdbfe}
@media(max-width:600px){
  .cookie-inner{flex-direction:column;align-items:flex-start}
  .cookie-actions{width:100%;justify-content:flex-end}
  .cookie-btn{padding:9px 16px;font-size:.8em}
}
.dark-mode .cookie-banner{background:#0f172a;border-color:#2563eb}
/* ====== GDPR CUSTOMIZE MODAL ====== */
.consent-overlay{
  display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);
  z-index:9999;align-items:center;justify-content:center;padding:16px
}
.consent-overlay.open{display:flex}
.consent-modal{
  background:#1e293b;color:#f1f5f9;border-radius:14px;
  padding:28px 24px;max-width:480px;width:100%;
  box-shadow:0 8px 40px rgba(0,0,0,.5);
  border:1px solid #334155
}
.consent-modal h3{font-size:1.05em;font-weight:700;margin-bottom:18px;color:#e2e8f0}
.consent-row{
  display:flex;justify-content:space-between;align-items:flex-start;
  padding:14px 0;border-top:1px solid #334155;gap:12px
}
.consent-row-text{flex:1}
.consent-row-text strong{display:block;font-size:.9em;font-weight:700;color:#e2e8f0;margin-bottom:3px}
.consent-row-text span{font-size:.78em;color:#94a3b8;line-height:1.45}
.consent-toggle{
  position:relative;width:44px;height:24px;flex-shrink:0;margin-top:2px
}
.consent-toggle input{opacity:0;width:0;height:0;position:absolute}
.consent-slider{
  position:absolute;inset:0;border-radius:24px;
  background:#334155;cursor:pointer;transition:background .2s
}
.consent-slider::after{
  content:'';position:absolute;width:18px;height:18px;
  border-radius:50%;background:#fff;top:3px;left:3px;
  transition:transform .2s;box-shadow:0 1px 4px rgba(0,0,0,.3)
}
.consent-toggle input:checked+.consent-slider{background:#3b82f6}
.consent-toggle input:checked+.consent-slider::after{transform:translateX(20px)}
.consent-toggle input:disabled+.consent-slider{background:#1d4ed8;cursor:not-allowed}
.consent-always{font-size:.75em;color:#60a5fa;font-weight:600;white-space:nowrap;margin-top:5px}
.consent-modal-actions{
  display:flex;gap:10px;justify-content:flex-end;margin-top:20px;flex-wrap:wrap
}
.consent-save{
  background:#3b82f6;color:#fff;border:none;border-radius:7px;
  padding:9px 22px;font-size:.85em;font-weight:600;cursor:pointer;transition:opacity .15s
}
.consent-save:hover{opacity:.88}
.dark-mode .consent-modal{background:#0f172a;border-color:#1e3a5f}
/* ====== CARD SUMMARY (inside card-body, above title, 2-line max) ====== */
.card-ai{font-size:.75em;line-height:1.5;color:rgba(255,255,255,.9);overflow:hidden;max-height:0;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;transition:max-height .2s ease}
.article-card:hover .card-ai{max-height:3em}
.article-card.card--no-img .card-ai{color:var(--text-muted);max-height:3em}
/* ====== SHARE BUTTONS — bottom bar, CSS Grid overlay ====== */
/* grid-area:1/1 overlaps card-link in same cell; align-self:end anchors to bottom.
   Fixes Safari iOS aspect-ratio bug (absolute+bottom:0 failed on indefinite block-size). */
.card-share{grid-area:1/1;align-self:end;display:flex;gap:5px;justify-content:center;align-items:center;padding:5px 12px;background:rgba(0,0,0,.65);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);opacity:0;pointer-events:none;transform:translateY(4px);transition:opacity .2s,transform .2s;z-index:2}
.article-card:hover .card-share{opacity:1;transform:translateY(0);pointer-events:auto}
/* Push card-body content up on hover so it clears the share bar */
.article-card:hover .card-body{padding-bottom:42px}
@media(pointer:coarse){
  /* On touch: share bar always visible, body always leaves room */
  .card-share{opacity:1;transform:none;pointer-events:auto}
  .card-body{padding-bottom:42px}
  .share-btn{width:30px;height:30px;font-size:.76em}
}
.share-btn{display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;font-size:.72em;font-weight:700;text-decoration:none;border:none;cursor:pointer;transition:transform .15s;backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
.share-btn:hover{transform:scale(1.18)}
.share-wa{background:#25d366;color:#fff}
.share-x{background:rgba(0,0,0,.75);color:#fff}
.share-tg{background:#229ed9;color:#fff}
.share-fb{background:#1877f2;color:#fff}
.share-copy{background:rgba(255,255,255,.22);color:#fff}
.card--no-img .share-wa{box-shadow:0 1px 3px rgba(0,0,0,.15)}
.card--no-img .share-copy{background:var(--border);color:var(--text)}
/* ====== VIDEO PLAY BUTTON OVERLAY ====== */
.card-play{position:absolute;top:50%;left:50%;transform:translate(-50%,-60%);width:52px;height:52px;border-radius:50%;background:rgba(0,0,0,.52);border:3px solid rgba(255,255,255,.88);display:flex;align-items:center;justify-content:center;pointer-events:none;transition:transform .2s,background .2s;z-index:5}
.card-play::after{content:'';display:block;width:0;height:0;border-style:solid;border-width:10px 0 10px 18px;border-color:transparent transparent transparent rgba(255,255,255,.95);margin-inline-start:4px}
.article-card:hover .card-play{transform:translate(-50%,-60%) scale(1.12);background:rgba(255,0,0,.72)}
@media(pointer:coarse){.card-play{width:46px;height:46px}}
/* ====== CLUSTER BADGE ====== */
.cluster-badge{display:inline-flex;align-items:center;gap:3px;font-size:.72em;font-weight:700;background:linear-gradient(90deg,#0ea5e9,#6366f1);color:#fff;padding:2px 8px;border-radius:10px;white-space:nowrap;cursor:default}
.cluster-badge:hover{background:linear-gradient(90deg,#0284c7,#4f46e5)}
.article-card:not(.card--no-img) .cluster-badge{text-shadow:0 1px 2px rgba(0,0,0,.3)}
.dark-mode .cluster-badge{background:linear-gradient(90deg,#0284c7,#4338ca)}
/* ====== SPECTRUM BADGE ====== */
.spectrum-badge{display:inline-flex;align-items:center;font-size:.62em;font-weight:700;letter-spacing:.3px;padding:1px 6px;border-radius:10px;vertical-align:middle;white-space:nowrap;text-transform:uppercase;margin-inline-start:5px;line-height:1.6}
.sp-wire{background:#e2e8f0;color:#475569}
.sp-public{background:#dbeafe;color:#1d4ed8}
.sp-commercial{background:#ffedd5;color:#c2410c}
.sp-state{background:#fee2e2;color:#b91c1c}
.sp-independent{background:#dcfce7;color:#15803d}
.dark-mode .sp-wire{background:#334155;color:#94a3b8}
.dark-mode .sp-public{background:#1e3a8a;color:#93c5fd}
.dark-mode .sp-commercial{background:#431407;color:#fb923c}
.dark-mode .sp-state{background:#450a0a;color:#fca5a5}
.dark-mode .sp-independent{background:#052e16;color:#86efac}
/* ====== ARTICLE PAGES ====== */
.art-page{max-width:800px;margin:0 auto;padding:28px 16px 48px}
.art-back{display:inline-flex;align-items:center;gap:8px;color:#fff;background:linear-gradient(135deg,var(--header-start),var(--header-end));text-decoration:none;font-size:.88em;font-weight:700;margin-bottom:24px;padding:10px 22px;border-radius:24px;box-shadow:0 3px 16px rgba(99,102,241,.3);transition:all .22s;border:none;white-space:nowrap}
.art-back:hover{transform:translateY(-2px);box-shadow:0 6px 24px rgba(99,102,241,.45);opacity:1}
.art-breadcrumb{font-size:.8em;color:var(--text-light);margin-bottom:18px;display:flex;align-items:center;gap:5px;flex-wrap:wrap}
/* Category page breadcrumb */
.cat-breadcrumb{font-size:.82em;color:var(--text-muted);margin-bottom:14px;padding:8px 0;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.cat-breadcrumb a{color:var(--text-muted);text-decoration:none;transition:color .15s}
.cat-breadcrumb a:hover{color:var(--accent)}
.bc-sep{opacity:.4;font-size:.9em}
.art-breadcrumb a{color:var(--accent);text-decoration:none}.art-breadcrumb a:hover{text-decoration:underline}
.art-img{width:100%;border-radius:12px;margin-bottom:22px;object-fit:cover;max-height:400px;display:block}
.art-title{font-size:1.65em;font-weight:800;line-height:1.4;margin:0 0 14px;color:var(--text)}
.art-meta{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:20px;font-size:.85em}
.art-source-badge{background:var(--accent);color:#fff;padding:3px 10px;border-radius:20px;font-weight:700}
.art-cluster-bar{display:flex;align-items:center;gap:8px;margin:12px 0;padding:10px 14px;background:linear-gradient(135deg,rgba(14,165,233,.08),rgba(99,102,241,.08));border-inline-start:3px solid #0ea5e9;border-radius:6px}
.art-cluster-srcs{font-size:.8em;color:var(--text-light);font-weight:500}
.art-date{color:var(--text-light)}
.art-cat-badge{padding:3px 10px;border-radius:20px;font-weight:600;font-size:.85em;color:#fff}
.art-summary-box{background:linear-gradient(135deg,rgba(99,102,241,.08),rgba(139,92,246,.04));border-inline-start:4px solid var(--accent);padding:18px 20px;border-radius:0 10px 10px 0;margin-bottom:24px}
.dark-mode .art-summary-box{background:linear-gradient(135deg,rgba(99,102,241,.15),rgba(139,92,246,.08))}
/* Fallback context card shown when no AI summary — prevents thin content */
.art-context-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px 20px;margin-bottom:24px;color:var(--text-muted);font-size:.92em;line-height:1.7}
.art-context-card strong{color:var(--accent)}
/* Browse category CTA — always shown at bottom of article page */
.art-browse-cta{display:inline-flex;align-items:center;gap:6px;margin-top:24px;padding:10px 20px;border-radius:8px;background:var(--surface);border:1.5px solid var(--border);color:var(--text-muted);font-size:.88em;font-weight:600;transition:all .18s}
.art-browse-cta:hover{border-color:var(--accent);color:var(--accent);background:rgba(99,102,241,.06)}
.art-summary-lbl{font-size:.78em;font-weight:700;color:var(--accent);margin-bottom:8px;display:flex;align-items:center;gap:5px}
.art-summary-text{font-size:.95em;line-height:1.75;color:var(--text)}
.art-disclaimer{font-size:.73em;color:var(--text-light);margin-top:10px;font-style:italic}
.art-read-btn{display:block;text-align:center;background:var(--accent);color:#fff !important;padding:13px 24px;border-radius:10px;text-decoration:none !important;font-weight:700;font-size:1em;margin-bottom:28px;transition:opacity .2s}
.art-read-btn:hover{opacity:.88}
.art-share-row{display:flex;gap:10px;justify-content:center;margin-bottom:32px;flex-wrap:wrap}
.art-share-row .share-btn{width:36px;height:36px;font-size:.88em}
.art-related{border-top:1px solid var(--border);padding-top:24px;margin-top:8px}
.art-related-title{font-size:1.05em;font-weight:700;margin-bottom:14px;color:var(--text)}
.art-related-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.art-rel-card{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:12px;text-decoration:none;color:var(--text);transition:border-color .15s,transform .15s;display:block}
.art-rel-card:hover{border-color:var(--accent);transform:translateY(-2px)}
.art-rel-title{font-size:.87em;font-weight:600;line-height:1.4;margin-bottom:5px;color:var(--text)}
.art-rel-meta{font-size:.74em;color:var(--text-light)}
@media(max-width:600px){.art-title{font-size:1.3em}.art-page{padding:18px 12px 36px}}
"""

APP_JS = r"""
'use strict';

/* ========== ARTICLE BACK LINK ========== */
// Uses history.back() so the browser restores the exact scroll position
// (the card the user clicked). Falls back to href (category anchor) when
// there is no history to go back to (e.g. direct URL from search engine).
(function () {
  var link = document.getElementById('art-back-link');
  if (!link) return;
  link.addEventListener('click', function (e) {
    if (history.length > 1) {
      e.preventDefault();
      history.back();
    }
    // else: let the <a href> navigate to ../index.html#slug normally
  });
})();

/* ========== THEME ========== */
const THEME_KEY = 'news-theme';
function initTheme() { applyTheme(localStorage.getItem(THEME_KEY) || 'light'); }
function applyTheme(mode) {
  document.body.classList.toggle('dark-mode', mode === 'dark');
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = mode === 'dark' ? '☀️' : '🌙';
  localStorage.setItem(THEME_KEY, mode);
}
function toggleTheme() { applyTheme(document.body.classList.contains('dark-mode') ? 'light' : 'dark'); }

/* ========== LIVE CLOCK ========== */
function initClock() {
  const el = document.getElementById('live-time');
  if (!el) return;
  function tick() {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2,'0');
    const mm = String(d.getMinutes()).padStart(2,'0');
    const ss = String(d.getSeconds()).padStart(2,'0');
    el.textContent = hh + ':' + mm + ':' + ss;
  }
  tick();
  setInterval(tick, 1000);
}


/* ========== NEWS HERO CAROUSEL ========== */
function initHeroCarousel() {
  document.querySelectorAll('.news-hero').forEach(hero => {
    const slides    = Array.from(hero.querySelectorAll('.nh-slide'));
    const dots      = Array.from(hero.querySelectorAll('.nh-dot'));
    const fill      = hero.querySelector('.nh-bar-fill');
    const btnPrev   = hero.querySelector('.nh-prev');
    const btnNext   = hero.querySelector('.nh-next');
    const sideItems = Array.from(hero.querySelectorAll('.nh-side-item'));
    if (slides.length < 2) return;

    let cur = 0, timer = null;
    const DELAY = 5500;

    function goTo(n) {
      slides[cur].classList.remove('active');
      if (dots[cur])           dots[cur].classList.remove('active');
      if (sideItems[cur - 1])  sideItems[cur - 1].classList.remove('active-side');
      cur = (n + slides.length) % slides.length;
      slides[cur].classList.add('active');
      if (dots[cur])           dots[cur].classList.add('active');
      if (sideItems[cur - 1])  sideItems[cur - 1].classList.add('active-side');
      startFill();
    }

    function startFill() {
      if (!fill) return;
      fill.style.transition = 'none';
      fill.style.width = '0%';
      requestAnimationFrame(() => requestAnimationFrame(() => {
        fill.style.transition = 'width ' + DELAY + 'ms linear';
        fill.style.width = '100%';
      }));
    }

    function startAuto() {
      clearInterval(timer);
      timer = setInterval(() => goTo(cur + 1), DELAY);
      startFill();
    }
    function stopAuto() {
      clearInterval(timer);
      if (fill) { fill.style.transition = 'none'; fill.style.width = '0%'; }
    }

    btnPrev && btnPrev.addEventListener('click', () => { goTo(cur - 1); stopAuto(); startAuto(); });
    btnNext && btnNext.addEventListener('click', () => { goTo(cur + 1); stopAuto(); startAuto(); });
    dots.forEach((d, i) => d.addEventListener('click', () => { goTo(i); stopAuto(); startAuto(); }));

    hero.addEventListener('mouseenter', stopAuto);
    hero.addEventListener('mouseleave', startAuto);

    // Touch swipe
    const slidesEl = hero.querySelector('.nh-slides');
    if (slidesEl) {
      let tx = 0;
      slidesEl.addEventListener('touchstart', e => { tx = e.touches[0].clientX; }, {passive: true});
      slidesEl.addEventListener('touchend', e => {
        const dx = tx - e.changedTouches[0].clientX;
        if (Math.abs(dx) > 40) { goTo(dx > 0 ? cur + 1 : cur - 1); stopAuto(); startAuto(); }
      });
    }

    startAuto();
  });
}

/* ========== SCROLL-TRIGGERED CARD ANIMATIONS ========== */
function initCardAnimations() {
  if (!('IntersectionObserver' in window)) return;
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion:reduce)').matches) return;
  const grids = Array.from(document.querySelectorAll('.articles-grid'));
  const viewH = window.innerHeight;
  const obs = new IntersectionObserver(entries => {
    entries.filter(e => e.isIntersecting).forEach(e => {
      e.target.querySelectorAll('.article-card').forEach((card, i) => {
        // Reset animation so it plays fresh as grid enters view
        card.style.animation = 'none';
        void card.offsetHeight; // force reflow
        card.style.animation = 'cardIn .44s ease ' + (i * 62) + 'ms both';
      });
      obs.unobserve(e.target);
    });
  }, { threshold: 0.05, rootMargin: '0px 0px -60px 0px' });
  // Only attach observer to grids below the initial viewport
  grids.forEach(g => {
    if (g.getBoundingClientRect().top > viewH * 0.85) obs.observe(g);
  });
}

/* ========== NAV / INTERSECTION ========== */
function initNav() {
  /* scroll active tab into view on page load (important for RTL overflowing navs) */
  const activeTab = document.querySelector('.nav-tab.active');
  if (activeTab) {
    activeTab.scrollIntoView({behavior:'instant', block:'nearest', inline:'nearest'});
  }
  const tabs = document.querySelectorAll('.nav-tab[data-cat]');
  const obs = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        tabs.forEach(t => t.classList.toggle('active', t.dataset.cat === id));
      }
    });
  }, { threshold: 0.2, rootMargin: '-80px 0px -55% 0px' });
  document.querySelectorAll('.category-section[id]').forEach(s => obs.observe(s));
}

/* ========== ECONOMY TABS ========== */
function initEconTabs() {
  const widget = document.querySelector('.econ-widget');
  if (!widget) return;
  // Only button tabs toggle panels — <a> link tabs navigate naturally
  const btnTabs = Array.from(widget.querySelectorAll('button.econ-tab'));
  const panels  = Array.from(widget.querySelectorAll('.econ-panel'));

  btnTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetId = tab.dataset.panel;
      const isAlreadyActive = tab.classList.contains('active');

      // Deactivate all button tabs + panels
      btnTabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));

      // Toggle: click active tab again → collapses; click inactive → opens
      if (!isAlreadyActive) {
        tab.classList.add('active');
        const panel = document.getElementById(targetId);
        if (panel) panel.classList.add('active');
      }
    });
  });
}

/* ========== BACK TO TOP ========== */
function initBackToTop() {
  const btn = document.getElementById('back-to-top');
  if (!btn) return;
  window.addEventListener('scroll', () => btn.classList.toggle('visible', window.scrollY > 400), {passive:true});
  btn.addEventListener('click', () => window.scrollTo({top:0, behavior:'smooth'}));
}

/* ========== SEARCH ========== */
function initSearch() {
  const toggle = document.getElementById('search-toggle');
  const bar    = document.getElementById('search-bar');
  const input  = document.getElementById('search-input');
  const clear  = document.getElementById('search-clear');
  if (!toggle || !bar || !input) return;

  // Toggle open/close
  toggle.addEventListener('click', () => {
    const open = bar.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
    if (open) { input.focus(); }
    else       { input.value = ''; _applySearch(''); }
  });

  // Keyboard shortcut: '/' opens search (unless in input)
  document.addEventListener('keydown', e => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      bar.classList.add('open');
      toggle.setAttribute('aria-expanded', 'true');
      input.focus();
    }
    if (e.key === 'Escape' && bar.classList.contains('open')) {
      bar.classList.remove('open');
      toggle.setAttribute('aria-expanded', 'false');
      input.value = '';
      _applySearch('');
    }
  });

  input.addEventListener('input', () => _applySearch(input.value.trim()));
  clear.addEventListener('click', () => { input.value = ''; _applySearch(''); input.focus(); });
}

function _applySearch(query) {
  const q = query.toLowerCase();
  const cards = document.querySelectorAll('.article-card');
  let visible = 0;
  cards.forEach(card => {
    const title = (card.dataset.title || '').toLowerCase();
    const src   = (card.dataset.source || '').toLowerCase();
    const show  = !q || title.includes(q) || src.includes(q);
    card.classList.toggle('sc-hidden', !show);
    if (show) visible++;
  });
  // Show "no results" message
  let noRes = document.getElementById('search-no-results');
  if (!noRes) {
    noRes = document.createElement('p');
    noRes.id = 'search-no-results';
    noRes.className = 'search-no-results';
    const _noResMap = {ar:'لا نتائج للبحث',fr:'Aucun résultat',es:'Sin resultados',tr:'Sonuç bulunamadı'};
    noRes.textContent = _noResMap[document.documentElement.lang] || 'No results found';
    const main = document.querySelector('main');
    if (main) main.prepend(noRes);
  }
  noRes.classList.toggle('visible', visible === 0 && q.length > 0);
}

/* ========== INIT ========== */
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  document.getElementById('theme-toggle')?.addEventListener('click', toggleTheme);
  initClock();
  initHeroCarousel();
  initCardAnimations();
  initNav();
  initBackToTop();
  initEconTabs();
  initSourceFilter();
  initSearch();
  // Register Service Worker for PWA offline support
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
});

/* ========== SOURCE FILTER ========== */
function initSourceFilter() {
  var strip = document.querySelector('.src-chips');
  if (!strip) return;
  var grid  = document.querySelector('.articles-grid');
  var empty = document.getElementById('src-empty');

  strip.querySelectorAll('.src-chip').forEach(function(chip) {
    chip.addEventListener('click', function() {
      var key = this.dataset.src;

      /* swap active chip */
      strip.querySelectorAll('.src-chip').forEach(function(c) {
        c.classList.remove('sc-active');
      });
      this.classList.add('sc-active');

      /* scroll chip into view (important for long source lists) */
      this.scrollIntoView({behavior:'smooth', block:'nearest', inline:'center'});

      /* filter cards */
      var cards = document.querySelectorAll('.article-card');
      var visible = 0;
      cards.forEach(function(card) {
        var show = key === '__all__' || card.dataset.source === key;
        card.classList.toggle('sc-hidden', !show);
        if (show) visible++;
      });

      /* empty state */
      if (empty) empty.classList.toggle('sc-show', visible === 0);

      /* brief fade-in animation */
      if (grid) {
        grid.classList.remove('sc-anim');
        void grid.offsetWidth; /* force reflow */
        grid.classList.add('sc-anim');
        setTimeout(function() { grid.classList.remove('sc-anim'); }, 350);
      }
    });
  });
}

/* ====== GDPR COOKIE CONSENT ====== */
(function() {
  var CONSENT_KEY = 'atlas_cookie_consent';
  var banner  = document.getElementById('cookie-banner');
  var overlay = document.getElementById('consent-overlay');
  if (!banner) return;

  /* Already decided — don't show */
  if (localStorage.getItem(CONSENT_KEY)) return;

  /* Show after short delay so page feels loaded */
  setTimeout(function() { banner.classList.add('cb-visible'); }, 900);

  function grantAnalytics() {
    if (window.gtag) {
      gtag('consent', 'update', {'analytics_storage': 'granted'});
      gtag('event', 'page_view');
    }
  }

  function dismiss(value) {
    localStorage.setItem(CONSENT_KEY, value);
    banner.classList.remove('cb-visible');
    if (overlay) overlay.classList.remove('open');
    setTimeout(function() { banner.remove(); if (overlay) overlay.remove(); }, 500);
    if (value === 'accepted') grantAnalytics();
  }

  /* Accept / Reject */
  var btnAccept = document.getElementById('cookie-accept');
  var btnReject = document.getElementById('cookie-reject');
  if (btnAccept) btnAccept.addEventListener('click', function() { dismiss('accepted'); });
  if (btnReject) btnReject.addEventListener('click', function() { dismiss('rejected'); });

  /* Customize — open modal */
  var btnCustomize = document.getElementById('cookie-customize');
  if (btnCustomize && overlay) {
    btnCustomize.addEventListener('click', function() {
      overlay.classList.add('open');
    });
    /* Close on overlay click outside modal */
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) overlay.classList.remove('open');
    });
    /* ESC key */
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') overlay.classList.remove('open');
    });
    /* Save preferences */
    var btnSave = document.getElementById('consent-save');
    var toggleAnalytics = document.getElementById('toggle-analytics');
    if (btnSave) {
      btnSave.addEventListener('click', function() {
        var analyticsOn = toggleAnalytics && toggleAnalytics.checked;
        var val = analyticsOn ? 'accepted' : 'rejected';
        dismiss(val);
      });
    }
  }
})();

/* ========== RELATIVE TIME — "منذ 20 دقيقة" / "2 hours ago" ========== */
(function() {
  var lang = document.documentElement.lang || 'en';
  var hasRTF = window.Intl && Intl.RelativeTimeFormat;
  var rtf = hasRTF ? new Intl.RelativeTimeFormat(lang, {numeric: 'auto'}) : null;

  function toRelative(dtStr) {
    if (!dtStr) return null;
    // Accept both "YYYY-MM-DD HH:MM:SS" and ISO formats
    var norm = dtStr.replace(' ', 'T');
    if (norm.length === 10) norm += 'T00:00:00Z';         // date only
    if (norm.length === 19) norm += '+00:00';             // no tz
    var d = new Date(norm);
    if (isNaN(d.getTime())) return null;
    var sec = Math.round((d.getTime() - Date.now()) / 1000);
    var abs = Math.abs(sec);
    if (!hasRTF) {
      // Fallback: simple labels without Intl
      if (abs < 3600)  return Math.round(abs/60)  + ' min';
      if (abs < 86400) return Math.round(abs/3600) + ' h';
      return Math.round(abs/86400) + ' d';
    }
    if (abs < 60)      return rtf.format(Math.round(sec),        'second');
    if (abs < 3600)    return rtf.format(Math.round(sec/60),     'minute');
    if (abs < 86400)   return rtf.format(Math.round(sec/3600),   'hour');
    if (abs < 5184000) return rtf.format(Math.round(sec/86400),  'day');   // 60 days
    return null;
  }

  function run() {
    document.querySelectorAll('time[datetime]').forEach(function(el) {
      var rel = toRelative(el.getAttribute('datetime'));
      if (rel) {
        if (!el.title) el.title = el.textContent.trim();
        el.textContent = rel;
      }
    });
  }

  // Run immediately + after DOM ready (handles dynamically added content)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();

/* ========== SHARE — copy link ========== */
document.addEventListener('click', function(e) {
  var btn = e.target.closest('.share-copy');
  if (!btn) return;
  var url = btn.getAttribute('data-copy');
  if (!url) return;
  if (navigator.clipboard) {
    navigator.clipboard.writeText(url).then(function() {
      var orig = btn.textContent;
      btn.textContent = '✓';
      setTimeout(function() { btn.textContent = orig; }, 1200);
    });
  } else {
    var ta = document.createElement('textarea');
    ta.value = url; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
});
"""

PRIVACY_HTML = """\
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="سياسة خصوصية Atlas News — مجمّع إخباري متعدد اللغات">
<title>سياسة الخصوصية — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-right:3px solid var(--accent);padding-right:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-right:20px;margin-bottom:14px}
.page li{list-style:disc}
.page a{color:var(--accent);text-decoration:underline}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
</style>
</head>
<body>
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">← العودة للرئيسية</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>سياسة الخصوصية</h1>
  <p class="sub">آخر تحديث: 2026</p>

  <p>نرحب بك في <strong>Atlas News</strong>. نلتزم بحماية خصوصيتك وفيما يلي توضيح كامل لسياستنا.</p>

  <h2>1. المعلومات التي نجمعها</h2>
  <p>هذا الموقع لا يجمع أي بيانات شخصية مباشرة. نحن موقع تجميع إخباري يعرض عناوين من مصادر أخرى.</p>
  <ul>
    <li>لا نطلب تسجيلاً أو اشتراكاً</li>
    <li>نستخدم التخزين المحلي للمتصفح (localStorage) فقط لحفظ تفضيلاتك (مثل الوضع المظلم) — لا نستخدم ملفات تعريف ارتباط تتبع خاصة بنا</li>
    <li>لا نجمع عناوين IP أو بيانات التصفح</li>
  </ul>

  <h2>2. Google AdSense والإعلانات</h2>
  <p>قد يستخدم هذا الموقع Google AdSense لعرض الإعلانات. تستخدم Google وشركاؤها ملفات تعريف الارتباط لتخصيص الإعلانات بناءً على زياراتك السابقة لهذا الموقع أو مواقع أخرى.</p>
  <ul>
    <li>يمكنك إلغاء الإعلانات المخصصة من خلال <a href="https://www.google.com/settings/ads" target="_blank" rel="noopener noreferrer">إعدادات إعلانات Google</a></li>
    <li>لمزيد من المعلومات: <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">سياسة خصوصية Google</a></li>
  </ul>

  <h2>3. الروابط الخارجية</h2>
  <p>جميع المقالات المعروضة تؤدي إلى مصادرها الأصلية. نحن لا نتحكم في محتوى هذه المواقع ولا نتحمل مسؤولية ممارسات خصوصيتها.</p>

  <h2>4. تحليلات الموقع</h2>
  <p>لا نستخدم حالياً أي أدوات تحليل مواقع. قد نضيف ذلك مستقبلاً مع الإفصاح الكامل.</p>

  <h2>5. حقوق الملكية الفكرية</h2>
  <p>عناوين الأخبار هي ملك لأصحابها الأصليين. نعرض فقط العناوين مع روابط المصادر الأصلية استناداً إلى مبدأ الاقتباس المنصف.</p>

  <h2>6. تعديل السياسة</h2>
  <p>نحتفظ بحق تعديل هذه السياسة في أي وقت. ننصحك بمراجعتها بانتظام.</p>

  <h2>7. التواصل معنا</h2>
  <p>لأي استفسار حول الخصوصية، يرجى مراجعة صفحة <a href="about.html">من نحن</a>.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ABOUT_HTML = """\
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="تعرف على Atlas News — مجمّع إخباري متعدد اللغات يغطي أخبار العالم بـ5 لغات">
<title>من نحن — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-right:3px solid var(--accent);padding-right:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-right:20px;margin-bottom:14px}
.page li{list-style:disc}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.chip{background:var(--surface-2);border:1px solid var(--border);padding:7px 14px;border-radius:8px;font-size:.85em;color:var(--text-muted)}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
.steps{display:flex;flex-direction:column;gap:10px;margin-top:10px}
.step{display:flex;gap:12px;align-items:flex-start;background:var(--surface-2);padding:12px 14px;border-radius:8px;border:1px solid var(--border)}
.step-num{background:var(--accent);color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.8em;font-weight:700;flex-shrink:0;margin-top:2px}
.dark-mode .step-num{background:#1e40af}
</style>
</head>
<body>
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">← العودة للرئيسية</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>من نحن</h1>
  <p class="sub">Atlas News — مجمّع إخباري آلي متعدد اللغات</p>

  <p><strong>Atlas News</strong> هو موقع تجميع إخباري يجمع أهم العناوين من مصادر عربية وعالمية موثوقة في مكان واحد، دون الحاجة إلى زيارة عشرات المواقع يومياً.</p>

  <h2>كيف يعمل الموقع</h2>
  <div class="steps">
    <div class="step"><span class="step-num">1</span><span>يتم جلب العناوين بشكل آلي كل 6 ساعات من المصادر المحددة</span></div>
    <div class="step"><span class="step-num">2</span><span>يتم تصفية العناوين غير ذات الصلة وإزالة المكررات تلقائياً</span></div>
    <div class="step"><span class="step-num">3</span><span>يعرض الموقع العنوان ورابط المصدر الأصلي فقط — لا يتم تعديل أي محتوى</span></div>
    <div class="step"><span class="step-num">4</span><span>يتجدد الموقع تلقائياً عبر GitHub Actions كل 6 ساعات</span></div>
  </div>

  <h2>مصادرنا</h2>
  <p>نجمع الأخبار من مصادر معروفة ومتنوعة:</p>
  <div class="chips">
    <span class="chip">🏛️ الجزيرة نت</span>
    <span class="chip">🏛️ BBC عربي</span>
    <span class="chip">🏛️ هسبريس</span>
    <span class="chip">🏛️ شوف تيفي</span>
    <span class="chip">🏛️ اليوم 24</span>
    <span class="chip">💰 العربية</span>
    <span class="chip">💰 سكاي نيوز عربية</span>
    <span class="chip">💻 تك عربي</span>
    <span class="chip">💻 عرب هاردوير</span>
    <span class="chip">⚽ كورة</span>
    <span class="chip">⚽ يلا كورة</span>
    <span class="chip">🔬 صحة ويب</span>
    <span class="chip">🔬 ساينس مغ</span>
  </div>

  <h2>التصنيفات المتاحة</h2>
  <ul>
    <li>🏛️ <strong>سياسة</strong> — أخبار سياسية عربية ودولية</li>
    <li>💰 <strong>اقتصاد</strong> — أحداث اقتصادية ومالية</li>
    <li>💻 <strong>تكنولوجيا</strong> — آخر أخبار التقنية والابتكار</li>
    <li>⚽ <strong>رياضة</strong> — أخبار الملاعب والبطولات</li>
    <li>🔬 <strong>صحة وعلوم</strong> — اكتشافات طبية وعلمية</li>
    <li>🎬 <strong>ثقافة وفن</strong> — أخبار الثقافة والفنون والإبداع</li>
    <li>🎓 <strong>تربية وتعليم</strong> — أخبار التعليم والأكاديميا</li>
    <li>🌿 <strong>بيئة ومناخ</strong> — أخبار البيئة والتغير المناخي</li>
    <li>💼 <strong>مال وأعمال</strong> — أخبار الأسواق والشركات</li>
    <li>✈️ <strong>سياحة وسفر</strong> — أخبار السياحة والوجهات العالمية</li>
  </ul>

  <h2>إخلاء المسؤولية</h2>
  <p>هذا الموقع هو مجمّع إخباري آلي. جميع المقالات مرتبطة بمصادرها الأصلية ونحن لسنا مسؤولين عن محتواها. قد يعرض الموقع إعلانات من خلال Google AdSense، لمزيد من التفاصيل راجع <a href="privacy.html">سياسة الخصوصية</a>.</p>

  <h2>الناشر</h2>
  <p>Atlas News موقع إخباري مُشغَّل من قِبل <strong>مطور مستقل</strong>. للتواصل: <a href="contact.html">صفحة التواصل</a> أو <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

PRIVACY_HTML_EN = """\
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="Atlas News Privacy Policy — multilingual automated news aggregator">
<title>Privacy Policy — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-left:20px;margin-bottom:14px}
.page li{list-style:disc}
.page a{color:var(--accent);text-decoration:underline}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}
</style>
</head>
<body>
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">&#8592; Back to Home</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>Privacy Policy</h1>
  <p class="sub">Last updated: 2026</p>
  <p>Welcome to <strong>Atlas News</strong>. We are committed to protecting your privacy.</p>
  <h2>1. Information We Collect</h2>
  <p>This site does not collect personal data directly. We are a news aggregator that displays headlines from other sources.</p>
  <ul>
    <li>No registration or subscription required</li>
    <li>We use browser local storage only to save your preferences (e.g., dark mode) — we do not use our own tracking cookies</li>
    <li>We do not collect IP addresses or browsing data</li>
  </ul>
  <h2>2. Google AdSense</h2>
  <p>This site may use Google AdSense to display advertisements. Google uses cookies to personalise ads based on your visits to this and other sites.</p>
  <ul>
    <li>Opt out via <a href="https://www.google.com/settings/ads" target="_blank" rel="noopener noreferrer">Google Ads Settings</a></li>
    <li>More info: <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Google Privacy Policy</a></li>
  </ul>
  <h2>3. External Links</h2>
  <p>All articles link to their original sources. We do not control the content or privacy practices of those sites.</p>
  <h2>4. Analytics</h2>
  <p>We do not currently use any analytics tools. This may change in the future with full disclosure.</p>
  <h2>5. Intellectual Property</h2>
  <p>Article headlines belong to their original publishers. We display headlines with links to original sources under fair use principles.</p>
  <h2>6. Policy Changes</h2>
  <p>We reserve the right to update this policy at any time. We recommend reviewing it periodically.</p>
  <h2>7. Contact</h2>
  <p>For any privacy questions, please visit <a href="about.html">About</a>.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ABOUT_HTML_EN = """\
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="About Atlas News — a multilingual automated news aggregator covering world news in 5 languages">
<title>About — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-left:20px;margin-bottom:14px}
.page li{list-style:disc}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.chip{background:var(--surface-2);border:1px solid var(--border);padding:7px 14px;border-radius:8px;font-size:.85em;color:var(--text-muted)}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
.steps{display:flex;flex-direction:column;gap:10px;margin-top:10px}
.step{display:flex;gap:12px;align-items:flex-start;background:var(--surface-2);padding:12px 14px;border-radius:8px;border:1px solid var(--border)}
.step-num{background:var(--accent);color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.8em;font-weight:700;flex-shrink:0;margin-top:2px}
body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}
</style>
</head>
<body>
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">&#8592; Back to Home</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>About</h1>
  <p class="sub">Atlas News — Automated multilingual news aggregator</p>
  <p><strong>Atlas News</strong> is a news aggregator that gathers the most important headlines from trusted international sources in one place, without needing to visit dozens of sites every day.</p>
  <h2>How It Works</h2>
  <div class="steps">
    <div class="step"><span class="step-num">1</span><span>Headlines are fetched automatically every 6 hours from configured sources</span></div>
    <div class="step"><span class="step-num">2</span><span>Irrelevant headlines are filtered and duplicates are removed automatically</span></div>
    <div class="step"><span class="step-num">3</span><span>The site displays the headline and a link to the original source only — no content is modified</span></div>
    <div class="step"><span class="step-num">4</span><span>The site is refreshed automatically via GitHub Actions every 6 hours</span></div>
  </div>
  <h2>Our Sources</h2>
  <p>We aggregate news from well-known, diverse sources:</p>
  <div class="chips">
    <span class="chip">🏛️ BBC World News</span>
    <span class="chip">🏛️ Reuters</span>
    <span class="chip">🏛️ Al Jazeera English</span>
    <span class="chip">🏛️ AP News</span>
    <span class="chip">💰 Financial Times</span>
    <span class="chip">💻 TechCrunch</span>
    <span class="chip">💻 The Verge</span>
    <span class="chip">⚽ BBC Sport</span>
    <span class="chip">🔬 Reuters Health</span>
    <span class="chip">🎓 Education Week</span>
  </div>
  <h2>Categories</h2>
  <ul>
    <li>🏛️ <strong>Politics</strong> — International political news</li>
    <li>💰 <strong>Economy</strong> — Financial and economic events</li>
    <li>💻 <strong>Technology</strong> — Latest tech and innovation news</li>
    <li>⚽ <strong>Sports</strong> — Sports and tournament news</li>
    <li>🔬 <strong>Health</strong> — Medical and scientific discoveries</li>
    <li>🎓 <strong>Education</strong> — Academic news and learning resources</li>
    <li>🌿 <strong>Environment</strong> — Environmental and climate change news</li>
    <li>💼 <strong>Business</strong> — Market and corporate news</li>
    <li>✈️ <strong>Travel</strong> — Tourism and global destinations news</li>
  </ul>
  <h2>Disclaimer</h2>
  <p>This site is an automated news aggregator. All articles link to their original sources and we are not responsible for their content. The site may display ads via Google AdSense; see <a href="privacy.html">Privacy Policy</a> for details.</p>

  <h2>Publisher</h2>
  <p>Atlas News is operated by an <strong>independent developer</strong>. Contact: <a href="contact.html">contact page</a> or <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

PRIVACY_HTML_FR = """\
<!DOCTYPE html>
<html lang="fr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="Politique de confidentialité d'Atlas News — agrégateur d'actualités multilingue automatisé">
<title>Politique de confidentialité — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-left:20px;margin-bottom:14px}
.page li{list-style:disc}
.page a{color:var(--accent);text-decoration:underline}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
</style>
</head>
<body class="lang-ltr">
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">&#8592; Retour à l'accueil</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>Politique de confidentialité</h1>
  <p class="sub">Dernière mise à jour : 2026</p>
  <p>Bienvenue sur <strong>Atlas News</strong>. Nous nous engageons à protéger votre vie privée.</p>
  <h2>1. Informations collectées</h2>
  <p>Ce site ne collecte aucune donnée personnelle directement. Nous sommes un agrégateur de nouvelles qui affiche des titres provenant d'autres sources.</p>
  <ul>
    <li>Aucune inscription ou abonnement requis</li>
    <li>Nous utilisons le stockage local du navigateur uniquement pour sauvegarder vos préférences (ex : mode sombre) — nous n'utilisons pas nos propres cookies de suivi</li>
    <li>Nous ne collectons pas d'adresses IP ni de données de navigation</li>
  </ul>
  <h2>2. Google AdSense</h2>
  <p>Ce site peut utiliser Google AdSense pour afficher des publicités. Google utilise des cookies pour personnaliser les annonces.</p>
  <ul>
    <li>Désactivez les annonces personnalisées via <a href="https://www.google.com/settings/ads" target="_blank" rel="noopener noreferrer">Paramètres des annonces Google</a></li>
    <li>Plus d'infos : <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Politique de confidentialité Google</a></li>
  </ul>
  <h2>3. Liens externes</h2>
  <p>Tous les articles renvoient à leurs sources originales. Nous ne contrôlons pas le contenu ni les pratiques de confidentialité de ces sites.</p>
  <h2>4. Analytique</h2>
  <p>Nous n'utilisons actuellement aucun outil d'analyse. Cela pourrait changer à l'avenir avec divulgation complète.</p>
  <h2>5. Propriété intellectuelle</h2>
  <p>Les titres d'articles appartiennent à leurs éditeurs d'origine. Nous affichons les titres avec des liens vers les sources originales.</p>
  <h2>6. Modifications de la politique</h2>
  <p>Nous nous réservons le droit de mettre à jour cette politique à tout moment.</p>
  <h2>7. Contact</h2>
  <p>Pour toute question, veuillez consulter <a href="about.html">À propos</a>.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ABOUT_HTML_FR = """\
<!DOCTYPE html>
<html lang="fr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="À propos d'Atlas News — agrégateur d'actualités multilingue automatisé en 5 langues">
<title>À propos — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-left:20px;margin-bottom:14px}
.page li{list-style:disc}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.chip{background:var(--surface-2);border:1px solid var(--border);padding:7px 14px;border-radius:8px;font-size:.85em;color:var(--text-muted)}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
.steps{display:flex;flex-direction:column;gap:10px;margin-top:10px}
.step{display:flex;gap:12px;align-items:flex-start;background:var(--surface-2);padding:12px 14px;border-radius:8px;border:1px solid var(--border)}
.step-num{background:var(--accent);color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.8em;font-weight:700;flex-shrink:0;margin-top:2px}
</style>
</head>
<body class="lang-ltr">
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">&#8592; Retour à l'accueil</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>À propos</h1>
  <p class="sub">Atlas News — Agrégateur d'actualités multilingue automatique</p>
  <p><strong>Atlas News</strong> est un agrégateur de nouvelles qui rassemble les titres les plus importants de sources internationales fiables en un seul endroit.</p>
  <h2>Comment ça fonctionne</h2>
  <div class="steps">
    <div class="step"><span class="step-num">1</span><span>Les titres sont récupérés automatiquement toutes les 6 heures depuis les sources configurées</span></div>
    <div class="step"><span class="step-num">2</span><span>Les titres non pertinents sont filtrés et les doublons supprimés automatiquement</span></div>
    <div class="step"><span class="step-num">3</span><span>Le site affiche le titre et un lien vers la source originale uniquement</span></div>
    <div class="step"><span class="step-num">4</span><span>Le site est mis à jour automatiquement via GitHub Actions toutes les 6 heures</span></div>
  </div>
  <h2>Nos sources</h2>
  <p>Nous agrégeons les actualités de sources reconnues et diverses :</p>
  <div class="chips">
    <span class="chip">🏛️ Le Monde</span>
    <span class="chip">🏛️ France 24</span>
    <span class="chip">🏛️ RFI</span>
    <span class="chip">🏛️ Le Figaro</span>
    <span class="chip">💰 Les Échos</span>
    <span class="chip">💰 La Tribune</span>
    <span class="chip">💻 01net</span>
    <span class="chip">💻 Numerama</span>
    <span class="chip">⚽ L'Équipe</span>
    <span class="chip">🔬 Le Monde Santé</span>
    <span class="chip">🎓 L'Étudiant</span>
  </div>
  <h2>Catégories</h2>
  <ul>
    <li>🏛️ <strong>Politique</strong> — Actualités politiques internationales</li>
    <li>💰 <strong>Économie</strong> — Événements financiers et économiques</li>
    <li>💻 <strong>Technologie</strong> — Dernières nouvelles tech et innovation</li>
    <li>⚽ <strong>Sports</strong> — Actualités sportives</li>
    <li>🔬 <strong>Santé</strong> — Découvertes médicales et scientifiques</li>
    <li>🎓 <strong>Éducation</strong> — Actualités académiques et pédagogiques</li>
    <li>🌿 <strong>Environnement</strong> — Actualités environnementales et climatiques</li>
    <li>💼 <strong>Business</strong> — Actualités des marchés et des entreprises</li>
    <li>✈️ <strong>Tourisme</strong> — Actualités touristiques et destinations mondiales</li>
  </ul>
  <h2>Avertissement</h2>
  <p>Ce site est un agrégateur automatique. Tous les articles renvoient à leurs sources originales. Consultez la <a href="privacy.html">politique de confidentialité</a> pour les détails sur la publicité.</p>

  <h2>Éditeur</h2>
  <p>Atlas News est géré par un <strong>développeur indépendant</strong>. Contact : <a href="contact.html">page de contact</a> ou <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

PRIVACY_HTML_ES = """\
<!DOCTYPE html>
<html lang="es" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="Política de privacidad de Atlas News — agregador de noticias multilingüe automatizado">
<title>Política de privacidad — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-left:20px;margin-bottom:14px}
.page li{list-style:disc}
.page a{color:var(--accent);text-decoration:underline}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
</style>
</head>
<body class="lang-ltr">
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">&#8592; Volver al inicio</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>Política de privacidad</h1>
  <p class="sub">Última actualización: 2026</p>
  <p>Bienvenido a <strong>Atlas News</strong>. Estamos comprometidos a proteger tu privacidad.</p>
  <h2>1. Información que recopilamos</h2>
  <p>Este sitio no recopila datos personales directamente. Somos un agregador de noticias que muestra titulares de otras fuentes.</p>
  <ul>
    <li>No se requiere registro ni suscripción</li>
    <li>Usamos el almacenamiento local del navegador solo para guardar tus preferencias (p. ej., modo oscuro) — no usamos cookies de seguimiento propias</li>
    <li>No recopilamos direcciones IP ni datos de navegación</li>
  </ul>
  <h2>2. Google AdSense</h2>
  <p>Este sitio puede usar Google AdSense para mostrar anuncios. Google usa cookies para personalizar los anuncios.</p>
  <ul>
    <li>Desactiva los anuncios personalizados en <a href="https://www.google.com/settings/ads" target="_blank" rel="noopener noreferrer">Configuración de anuncios de Google</a></li>
    <li>Más info: <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Política de privacidad de Google</a></li>
  </ul>
  <h2>3. Enlaces externos</h2>
  <p>Todos los artículos enlazan a sus fuentes originales. No controlamos el contenido ni las prácticas de privacidad de esos sitios.</p>
  <h2>4. Analítica</h2>
  <p>Actualmente no usamos ninguna herramienta de análisis. Esto podría cambiar en el futuro con divulgación completa.</p>
  <h2>5. Propiedad intelectual</h2>
  <p>Los titulares de artículos pertenecen a sus editores originales. Mostramos titulares con enlaces a las fuentes originales.</p>
  <h2>6. Cambios en la política</h2>
  <p>Nos reservamos el derecho de actualizar esta política en cualquier momento.</p>
  <h2>7. Contacto</h2>
  <p>Para cualquier pregunta, visita <a href="about.html">Acerca de</a>.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ABOUT_HTML_ES = """\
<!DOCTYPE html>
<html lang="es" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="Acerca de Atlas News — agregador de noticias multilingüe automatizado en 5 idiomas">
<title>Acerca de — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-left:20px;margin-bottom:14px}
.page li{list-style:disc}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.chip{background:var(--surface-2);border:1px solid var(--border);padding:7px 14px;border-radius:8px;font-size:.85em;color:var(--text-muted)}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
.steps{display:flex;flex-direction:column;gap:10px;margin-top:10px}
.step{display:flex;gap:12px;align-items:flex-start;background:var(--surface-2);padding:12px 14px;border-radius:8px;border:1px solid var(--border)}
.step-num{background:var(--accent);color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.8em;font-weight:700;flex-shrink:0;margin-top:2px}
</style>
</head>
<body class="lang-ltr">
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">&#8592; Volver al inicio</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>Acerca de</h1>
  <p class="sub">Atlas News — Agregador de noticias multilingüe automatizado</p>
  <p><strong>Atlas News</strong> es un agregador de noticias que reúne los titulares más importantes de fuentes internacionales confiables en un solo lugar.</p>
  <h2>Cómo funciona</h2>
  <div class="steps">
    <div class="step"><span class="step-num">1</span><span>Los titulares se obtienen automáticamente cada 6 horas desde las fuentes configuradas</span></div>
    <div class="step"><span class="step-num">2</span><span>Los titulares irrelevantes se filtran y los duplicados se eliminan automáticamente</span></div>
    <div class="step"><span class="step-num">3</span><span>El sitio muestra el titular y un enlace a la fuente original únicamente</span></div>
    <div class="step"><span class="step-num">4</span><span>El sitio se actualiza automáticamente mediante GitHub Actions cada 6 horas</span></div>
  </div>
  <h2>Nuestras fuentes</h2>
  <p>Agregamos noticias de fuentes reconocidas y diversas:</p>
  <div class="chips">
    <span class="chip">🏛️ El País</span>
    <span class="chip">🏛️ BBC Mundo</span>
    <span class="chip">🏛️ El Mundo</span>
    <span class="chip">🏛️ Infobae</span>
    <span class="chip">💰 Expansión</span>
    <span class="chip">💻 Xataka</span>
    <span class="chip">💻 Hipertextual</span>
    <span class="chip">⚽ Marca</span>
    <span class="chip">⚽ AS</span>
    <span class="chip">🔬 El País Salud</span>
    <span class="chip">🎓 El País Educación</span>
  </div>
  <h2>Categorías</h2>
  <ul>
    <li>🏛️ <strong>Política</strong> — Noticias políticas internacionales</li>
    <li>💰 <strong>Economía</strong> — Eventos financieros y económicos</li>
    <li>💻 <strong>Tecnología</strong> — Últimas noticias de tecnología e innovación</li>
    <li>⚽ <strong>Deportes</strong> — Noticias deportivas</li>
    <li>🔬 <strong>Salud</strong> — Descubrimientos médicos y científicos</li>
    <li>🎓 <strong>Educación</strong> — Noticias académicas y recursos educativos</li>
    <li>🌿 <strong>Medio Ambiente</strong> — Noticias medioambientales y climáticas</li>
    <li>💼 <strong>Negocios</strong> — Noticias de mercados y empresas</li>
    <li>✈️ <strong>Turismo</strong> — Noticias de turismo y destinos globales</li>
  </ul>
  <h2>Aviso legal</h2>
  <p>Este sitio es un agregador automático. Todos los artículos enlazan a sus fuentes originales. Consulta la <a href="privacy.html">política de privacidad</a> para detalles sobre publicidad.</p>

  <h2>Editor</h2>
  <p>Atlas News es gestionado por un <strong>desarrollador independiente</strong>. Contacto: <a href="contact.html">página de contacto</a> o <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

PRIVACY_HTML_TR = """\
<!DOCTYPE html>
<html lang="tr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="Atlas News gizlilik politikası — çok dilli otomatik haber toplayıcı">
<title>Gizlilik Politikası — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-left:20px;margin-bottom:14px}
.page li{list-style:disc}
.page a{color:var(--accent);text-decoration:underline}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
</style>
</head>
<body class="lang-ltr">
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">&#8592; Ana sayfaya dön</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>Gizlilik Politikası</h1>
  <p class="sub">Son güncelleme: 2026</p>
  <p><strong>Atlas News</strong>'e hoş geldiniz. Gizliliğinizi korumaya kararlıyız.</p>
  <h2>1. Topladığımız Bilgiler</h2>
  <p>Bu site doğrudan kişisel veri toplamaz. Diğer kaynaklardan haber başlıklarını gösteren bir haber toplayıcısıyız.</p>
  <ul>
    <li>Kayıt veya abonelik gerekmez</li>
    <li>Yalnızca tercihlerinizi kaydetmek için tarayıcı yerel depolama alanı kullanıyoruz (ör. karanlık mod) — kendi izleme çerezlerimizi kullanmıyoruz</li>
    <li>IP adresi veya tarama verisi toplamıyoruz</li>
  </ul>
  <h2>2. Google AdSense</h2>
  <p>Bu site reklam göstermek için Google AdSense kullanabilir. Google, reklamları kişiselleştirmek için çerez kullanır.</p>
  <ul>
    <li>Kişiselleştirilmiş reklamları <a href="https://www.google.com/settings/ads" target="_blank" rel="noopener noreferrer">Google Reklam Ayarları</a>'ndan devre dışı bırakabilirsiniz</li>
    <li>Daha fazla bilgi: <a href="https://policies.google.com/privacy" target="_blank" rel="noopener noreferrer">Google Gizlilik Politikası</a></li>
  </ul>
  <h2>3. Dış Bağlantılar</h2>
  <p>Tüm makaleler orijinal kaynaklarına bağlantı verir. Bu sitelerin içeriğini veya gizlilik uygulamalarını kontrol etmiyoruz.</p>
  <h2>4. Analitik</h2>
  <p>Şu an hiçbir analiz aracı kullanmıyoruz. Bu durum ileride tam açıklama yapılarak değişebilir.</p>
  <h2>5. Fikri Mülkiyet</h2>
  <p>Makale başlıkları orijinal yayıncılarına aittir. Başlıkları orijinal kaynaklarına bağlantı vererek gösteriyoruz.</p>
  <h2>6. Politika Değişiklikleri</h2>
  <p>Bu politikayı istediğimiz zaman güncelleme hakkımızı saklı tutarız.</p>
  <h2>7. İletişim</h2>
  <p>Sorularınız için <a href="about.html">Hakkımızda</a> sayfasını ziyaret edin.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ABOUT_HTML_TR = """\
<!DOCTYPE html>
<html lang="tr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="description" content="Atlas News hakkında — 5 dilde otomatik çok dilli haber toplayıcısı">
<title>Hakkımızda — Atlas News</title>
<link rel="stylesheet" href="style.css">
<style>
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-left:20px;margin-bottom:14px}
.page li{list-style:disc}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.chip{background:var(--surface-2);border:1px solid var(--border);padding:7px 14px;border-radius:8px;font-size:.85em;color:var(--text-muted)}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
.steps{display:flex;flex-direction:column;gap:10px;margin-top:10px}
.step{display:flex;gap:12px;align-items:flex-start;background:var(--surface-2);padding:12px 14px;border-radius:8px;border:1px solid var(--border)}
.step-num{background:var(--accent);color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.8em;font-weight:700;flex-shrink:0;margin-top:2px}
</style>
</head>
<body class="lang-ltr">
<div class="top-bar">
  <div class="top-bar-inner">
    <a href="index.html" class="back">&#8592; Ana sayfaya dön</a>
    <button id="theme-toggle" class="theme-btn">🌙</button>
  </div>
</div>
<div class="page">
  <h1>Hakkımızda</h1>
  <p class="sub">Atlas News — Otomatik çok dilli haber toplayıcısı</p>
  <p>Bu site, Türkiye ve dünyadan birden fazla güvenilir kaynaktan haberleri otomatik olarak toplayan bir <strong>haber toplayıcısıdır</strong>. Her içerik parçası, tam makaleye orijinal kaynağında bağlantı verir.</p>
  <h2>Nasıl Çalışır?</h2>
  <div class="steps">
    <div class="step"><div class="step-num">1</div><div>Otomatik sistem, onlarca güvenilir Türk ve uluslararası haber kaynağını her 6 saatte bir tarar.</div></div>
    <div class="step"><div class="step-num">2</div><div>Haber başlıkları ve bağlantıları toplanır, filtrelenir ve kategorilere göre düzenlenir.</div></div>
    <div class="step"><div class="step-num">3</div><div>Statik HTML sayfaları oluşturulur ve maksimum hız ile güvenilirlik için sunulur.</div></div>
  </div>
  <h2>Kapsanan Bölümler</h2>
  <div class="chips">
    <span class="chip">🏛️ Politika</span>
    <span class="chip">💰 Ekonomi</span>
    <span class="chip">💻 Teknoloji</span>
    <span class="chip">⚽ Spor</span>
    <span class="chip">🔬 Sağlık</span>
    <span class="chip">🧪 Bilim</span>
    <span class="chip">🎬 Kültür &amp; Sanat</span>
    <span class="chip">🎓 Eğitim</span>
  </div>
  <h2>Kapsanan Bölümler hakkında</h2>
  <ul>
    <li>🏛️ <strong>Politika</strong> — Türkiye ve dünya siyasi haberleri</li>
    <li>💰 <strong>Ekonomi</strong> — Finans ve ekonomi haberleri</li>
    <li>💻 <strong>Teknoloji</strong> — Teknoloji ve inovasyon haberleri</li>
    <li>⚽ <strong>Spor</strong> — Spor haberleri</li>
    <li>🔬 <strong>Sağlık</strong> — Tıbbi haberler ve sağlık bilgileri</li>
    <li>🧪 <strong>Bilim</strong> — Bilim ve araştırma haberleri</li>
    <li>🎬 <strong>Kültür &amp; Sanat</strong> — Kültür ve sanat haberleri</li>
    <li>🎓 <strong>Eğitim</strong> — Eğitim ve akademik haberler</li>
    <li>🌿 <strong>Çevre</strong> — Çevre ve iklim değişikliği haberleri</li>
    <li>💼 <strong>İş Dünyası</strong> — Piyasa ve şirket haberleri</li>
    <li>✈️ <strong>Turizm</strong> — Turizm ve küresel destinasyonlar haberleri</li>
  </ul>
  <h2>Yasal Uyarı</h2>
  <p>Bu site otomatik bir toplayıcıdır. Tüm makaleler orijinal kaynaklarına bağlantı verir. Reklamlar hakkında ayrıntılar için <a href="privacy.html">Gizlilik Politikası</a>'nı inceleyin.</p>
  <h2>Yayıncı</h2>
  <p>Atlas News, bir <strong>bağımsız geliştirici</strong> tarafından işletilmektedir. Şeffaflık veya içerik hakkında sorularınız için <a href="contact.html">iletişim sayfamızı</a> ziyaret edin ya da <a href="mailto:contact@solvixi.com">contact@solvixi.com</a> adresine e-posta gönderin.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

# ── Shared inline CSS for static pages ───────────────────────────────────────
_PAGE_CSS = """
.page{max-width:820px;margin:40px auto;padding:0 16px 80px}
.page h1{margin-bottom:6px}
.sub{color:var(--text-muted);margin-bottom:36px;font-size:.85em}
.page h2{margin:28px 0 10px;font-size:1.05em;color:var(--accent);border-inline-start:3px solid var(--accent);padding-inline-start:10px}
.dark-mode .page h2{color:#60a5fa;border-color:#60a5fa}
.page p,.page li{color:var(--text-muted);line-height:1.85;margin-bottom:12px;font-size:.95em}
.page ul{padding-inline-start:20px;margin-bottom:14px}
.page li{list-style:disc}
.page a{color:var(--accent);text-decoration:underline}
.back{display:inline-block;margin-bottom:28px;color:var(--accent);font-size:.9em}
.back:hover{text-decoration:underline}
.info-card{background:var(--surface-2);border:1px solid var(--border);border-radius:12px;padding:22px 24px;margin-bottom:14px;display:flex;gap:16px;align-items:flex-start}
.info-card-icon{font-size:1.8em;flex-shrink:0;margin-top:2px}
.info-card h3{margin:0 0 4px;font-size:1em;font-weight:700}
.info-card p{margin:0;font-size:.88em;color:var(--text-muted)}
.info-card a{color:var(--accent);font-weight:700;text-decoration:none}
.info-card a:hover{text-decoration:underline}
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:20px 0}
.stat-box2{background:var(--surface-2);border:1px solid var(--border);border-radius:10px;padding:18px;text-align:center}
.stat-box2-val{font-size:1.8em;font-weight:800;color:var(--accent)}
.stat-box2-lbl{font-size:.78em;color:var(--text-muted);margin-top:4px}
.ad-format{background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:14px 18px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.ad-format-name{font-weight:700;font-size:.95em}
.ad-format-size{font-size:.82em;color:var(--text-muted);direction:ltr}
.cta-box{background:linear-gradient(135deg,var(--accent),#6366f1);border-radius:14px;padding:32px;text-align:center;margin:28px 0;color:#fff}
.cta-box h2{color:#fff;border:none;padding:0;margin:0 0 10px;font-size:1.3em}
.cta-box p{color:rgba(255,255,255,.9);margin-bottom:20px}
.cta-btn{display:inline-block;background:#fff;color:var(--accent);padding:12px 32px;border-radius:8px;font-weight:700;font-size:.95em;text-decoration:none;transition:.2s}
.cta-btn:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.2)}
@media(max-width:540px){.stat-row{grid-template-columns:1fr 1fr}}
"""

# ════════════════════════════════════════════════════════════════════════════
# CONTACT PAGES (5 languages)
# ════════════════════════════════════════════════════════════════════════════
CONTACT_HTML = """\
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>اتصل بنا — Atlas News</title>
<meta name="description" content="تواصل مع فريق Atlas News — استفسارات، اقتراحات، وفرص الإعلان">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; العودة للرئيسية</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>اتصل بنا</h1>
  <p class="sub">نسعد بسماع آرائكم واستفساراتكم — سيتم الرد خلال 48 ساعة عمل</p>

  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>البريد العام</h3>
      <p>للاستفسارات العامة والاقتراحات</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">📢</span>
    <div>
      <h3>الإعلان والشراكات</h3>
      <p>للاستفسار عن فرص الإعلان والتعاون التجاري</p>
      <a href="mailto:ads@solvixi.com">ads@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>الإبلاغ عن محتوى</h3>
      <p>للإبلاغ عن أي محتوى مشكوك فيه أو أخطاء</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>

  <h2>معلومات عامة</h2>
  <p><strong>Atlas News</strong> هو موقع تجميع إخباري آلي يخدم الجمهور العالمي بخمس لغات: العربية، الإنجليزية، الفرنسية، الإسبانية، والتركية.</p>
  <p>نحن نرحب بأي تعاون أو شراكة أو اقتراحات لمصادر جديدة. تواصل معنا وسنرد في أقرب وقت ممكن.</p>

  <h2>اقتراح مصدر إخباري</h2>
  <p>هل تعرف موقعاً إخبارياً موثوقاً يستحق الإضافة؟ أرسل لنا اسمه ورابطه على <a href="mailto:contact@solvixi.com">contact@solvixi.com</a> وسنراجعه بعناية.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

CONTACT_HTML_EN = """\
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Contact Us — Atlas News</title>
<meta name="description" content="Get in touch with Atlas News — inquiries, suggestions, and advertising opportunities">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Back to Home</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Contact Us</h1>
  <p class="sub">We'd love to hear from you — we reply within 48 business hours</p>

  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>General Inquiries</h3>
      <p>For questions, suggestions and feedback</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">📢</span>
    <div>
      <h3>Advertising &amp; Partnerships</h3>
      <p>For advertising opportunities and commercial partnerships</p>
      <a href="mailto:ads@solvixi.com">ads@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>Report Content</h3>
      <p>To report inaccurate or problematic content</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>

  <h2>About Atlas News</h2>
  <p><strong>Atlas News</strong> is an automated multilingual news aggregator serving global audiences in five languages: Arabic, English, French, Spanish, and Turkish.</p>
  <p>We welcome collaborations, partnerships, and source suggestions. Reach out and we'll get back to you as soon as possible.</p>

  <h2>Suggest a News Source</h2>
  <p>Know a reliable news source worth adding? Send us the name and URL at <a href="mailto:contact@solvixi.com">contact@solvixi.com</a> and we'll review it carefully.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

CONTACT_HTML_FR = """\
<!DOCTYPE html>
<html lang="fr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Contactez-nous — Atlas News</title>
<meta name="description" content="Contactez l'équipe Atlas News — questions, suggestions et opportunités publicitaires">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Retour à l'accueil</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Contactez-nous</h1>
  <p class="sub">Nous serons ravis de vous entendre — réponse sous 48 heures ouvrables</p>

  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>Contact général</h3>
      <p>Pour les questions, suggestions et retours</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">📢</span>
    <div>
      <h3>Publicité &amp; Partenariats</h3>
      <p>Pour les opportunités publicitaires et partenariats commerciaux</p>
      <a href="mailto:ads@solvixi.com">ads@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>Signaler un contenu</h3>
      <p>Pour signaler un contenu inexact ou problématique</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>

  <h2>À propos d'Atlas News</h2>
  <p><strong>Atlas News</strong> est un agrégateur d'actualités multilingue automatisé servant un public mondial en cinq langues : arabe, anglais, français, espagnol et turc.</p>
  <p>Nous accueillons volontiers les collaborations, partenariats et suggestions de sources. Contactez-nous et nous vous répondrons dans les plus brefs délais.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

CONTACT_HTML_ES = """\
<!DOCTYPE html>
<html lang="es" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Contacto — Atlas News</title>
<meta name="description" content="Contacta con el equipo de Atlas News — consultas, sugerencias y oportunidades publicitarias">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Volver al inicio</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Contacto</h1>
  <p class="sub">Nos encantará saber de ti — respondemos en 48 horas hábiles</p>

  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>Consultas generales</h3>
      <p>Para preguntas, sugerencias y comentarios</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">📢</span>
    <div>
      <h3>Publicidad &amp; Colaboraciones</h3>
      <p>Para oportunidades publicitarias y asociaciones comerciales</p>
      <a href="mailto:ads@solvixi.com">ads@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>Reportar contenido</h3>
      <p>Para reportar contenido inexacto o problemático</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>

  <h2>Sobre Atlas News</h2>
  <p><strong>Atlas News</strong> es un agregador de noticias multilingüe automatizado que sirve a audiencias globales en cinco idiomas: árabe, inglés, francés, español y turco.</p>
  <p>Damos la bienvenida a colaboraciones, asociaciones y sugerencias de fuentes. Contáctanos y te responderemos lo antes posible.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

CONTACT_HTML_TR = """\
<!DOCTYPE html>
<html lang="tr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Iletisim — Atlas News</title>
<meta name="description" content="Atlas News ekibiyle iletisime gecin — sorular, oneriler ve reklam firsatlari">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Ana Sayfaya Don</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Iletisim</h1>
  <p class="sub">Sizden haber almaktan memnuniyet duyariz — 48 is saati icinde yanit veririz</p>

  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>Genel Sorular</h3>
      <p>Sorular, oneriler ve geri bildirimler icin</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">📢</span>
    <div>
      <h3>Reklam &amp; Is Birligi</h3>
      <p>Reklam firsatlari ve ticari ortakliklar icin</p>
      <a href="mailto:ads@solvixi.com">ads@solvixi.com</a>
    </div>
  </div>

  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>Icerik Bildirin</h3>
      <p>Yanlis veya sorunlu icerigi bildirmek icin</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>

  <h2>Atlas News Hakkinda</h2>
  <p><strong>Atlas News</strong>, bes dilde — Arapca, Ingilizce, Fransizca, Ispanyolca ve Turkce — kuresel kitlelere hizmet eden otomatik cok dilli bir haber toplayicisidir.</p>
  <p>Is birlikleri, ortakliklar ve kaynak onerileri konusunda her zaman acigiz. Bize ulasin, en kisa surede geri donecegiz.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

# ════════════════════════════════════════════════════════════════════════════
# TERMS OF USE PAGES (5 languages)
# ════════════════════════════════════════════════════════════════════════════
TERMS_HTML = """\
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>شروط الاستخدام — Atlas News</title>
<meta name="description" content="شروط وأحكام استخدام موقع Atlas News">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; العودة للرئيسية</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>شروط الاستخدام</h1>
  <p class="sub">آخر تحديث: 2026 — يُرجى قراءة هذه الشروط بعناية قبل استخدام الموقع</p>

  <h2>1. القبول بالشروط</h2>
  <p>باستخدامك لموقع <strong>Atlas News</strong> (atlasnews.solvixi.com)، فإنك توافق على الالتزام بهذه الشروط والأحكام. إذا كنت لا توافق على أي من هذه الشروط، يُرجى التوقف عن استخدام الموقع.</p>

  <h2>2. طبيعة الخدمة</h2>
  <p>Atlas News هو <strong>مجمّع إخباري آلي</strong> يعرض عناوين الأخبار وروابطها من مصادر إخبارية خارجية. نحن:</p>
  <ul>
    <li>لا ننشئ أو نحرر أي محتوى إخباري</li>
    <li>نعرض فقط العناوين مع روابط المصادر الأصلية</li>
    <li>لسنا مسؤولين عن دقة أو محتوى المقالات الأصلية</li>
    <li>نحترم حقوق الملكية الفكرية للمصادر الأصلية</li>
  </ul>

  <h2>3. الملكية الفكرية</h2>
  <p>جميع عناوين الأخبار وصور المقالات هي ملك لأصحابها الأصليين. يتم عرضها استناداً إلى مبدأ الاقتباس المنصف (Fair Use) لأغراض إخبارية. إذا كنت صاحب محتوى وترغب في إزالته، تواصل معنا على <a href="mailto:report@solvixi.com">report@solvixi.com</a>.</p>
  <p>تُولَّد الملخصات الإضافية بواسطة الذكاء الاصطناعي انطلاقاً من <strong>وصف RSS</strong> الذي ينشره الناشر الأصلي عبر خلاصته العامة — وليست نسخاً حرفية من نص المقالة الكاملة.</p>

  <h2>4. إخلاء المسؤولية</h2>
  <p>يُقدَّم الموقع "كما هو" دون أي ضمانات صريحة أو ضمنية. لا نضمن دقة أو اكتمال أو توافر المحتوى في أي وقت. لن نكون مسؤولين عن أي أضرار مباشرة أو غير مباشرة ناتجة عن استخدام الموقع.</p>

  <h2>5. الاستخدامات المحظورة</h2>
  <p>يُحظر عليك:</p>
  <ul>
    <li>كشط أو استخراج البيانات بشكل منهجي من الموقع</li>
    <li>إعادة نشر محتوى الموقع دون إذن صريح</li>
    <li>محاولة اختراق أو التدخل في عمل الموقع</li>
    <li>استخدام الموقع لأغراض غير قانونية</li>
  </ul>

  <h2>6. الإعلانات</h2>
  <p>قد يعرض الموقع إعلانات من خلال Google AdSense وشبكات إعلانية أخرى. هذه الإعلانات خاضعة لشروط وسياسات خصوصية مزوديها. لا نتحمل مسؤولية محتوى هذه الإعلانات.</p>

  <h2>7. التعديلات</h2>
  <p>نحتفظ بحق تعديل هذه الشروط في أي وقت. الاستمرار في استخدام الموقع بعد التعديلات يُعدّ قبولاً بها.</p>

  <h2>8. التواصل</h2>
  <p>للأسئلة المتعلقة بهذه الشروط: <a href="mailto:contact@solvixi.com">contact@solvixi.com</a></p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

TERMS_HTML_EN = """\
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Terms of Use — Atlas News</title>
<meta name="description" content="Terms and conditions for using Atlas News">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Back to Home</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Terms of Use</h1>
  <p class="sub">Last updated: 2026 — Please read these terms carefully before using the site</p>

  <h2>1. Acceptance of Terms</h2>
  <p>By accessing <strong>Atlas News</strong> (atlasnews.solvixi.com), you agree to be bound by these Terms of Use. If you do not agree to any of these terms, please discontinue use of the site.</p>

  <h2>2. Nature of Service</h2>
  <p>Atlas News is an <strong>automated news aggregator</strong> that displays headlines and links from external news sources. We:</p>
  <ul>
    <li>Do not create or edit any news content</li>
    <li>Display only headlines with links to original sources</li>
    <li>Are not responsible for the accuracy or content of original articles</li>
    <li>Respect the intellectual property rights of original publishers</li>
  </ul>

  <h2>3. Intellectual Property</h2>
  <p>All news headlines and article images are the property of their respective owners. They are displayed under the principle of Fair Use for news aggregation purposes. If you are a content owner and wish to have content removed, contact us at <a href="mailto:report@solvixi.com">report@solvixi.com</a>.</p>
  <p>AI-generated summaries are derived from the <strong>RSS description</strong> published by the original source in their public feed — they are not verbatim copies of the full article text.</p>

  <h2>4. Disclaimer of Warranties</h2>
  <p>The site is provided "as is" without any express or implied warranties. We do not guarantee the accuracy, completeness, or availability of content at any time. We shall not be liable for any direct or indirect damages resulting from use of the site.</p>

  <h2>5. Prohibited Uses</h2>
  <p>You may not:</p>
  <ul>
    <li>Systematically scrape or extract data from the site</li>
    <li>Republish site content without explicit permission</li>
    <li>Attempt to hack or interfere with site operations</li>
    <li>Use the site for any unlawful purposes</li>
  </ul>

  <h2>6. Advertising</h2>
  <p>The site may display advertisements via Google AdSense and other ad networks. These ads are subject to the terms and privacy policies of their providers. We are not responsible for ad content.</p>

  <h2>7. Modifications</h2>
  <p>We reserve the right to modify these terms at any time. Continued use of the site after modifications constitutes acceptance of the updated terms.</p>

  <h2>8. Contact</h2>
  <p>For questions about these terms: <a href="mailto:contact@solvixi.com">contact@solvixi.com</a></p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

TERMS_HTML_FR = """\
<!DOCTYPE html>
<html lang="fr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Conditions d'utilisation — Atlas News</title>
<meta name="description" content="Conditions générales d'utilisation d'Atlas News">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Retour à l'accueil</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Conditions d'utilisation</h1>
  <p class="sub">Dernière mise à jour : 2026 — Veuillez lire attentivement ces conditions</p>

  <h2>1. Acceptation des conditions</h2>
  <p>En accédant à <strong>Atlas News</strong>, vous acceptez d'être lié par ces conditions d'utilisation.</p>

  <h2>2. Nature du service</h2>
  <p>Atlas News est un <strong>agrégateur d'actualités automatisé</strong> qui affiche des titres et des liens vers des sources d'information externes. Nous ne créons ni n'éditons aucun contenu journalistique.</p>

  <h2>3. Propriété intellectuelle</h2>
  <p>Tous les titres et images d'articles appartiennent à leurs propriétaires respectifs. Si vous êtes propriétaire d'un contenu et souhaitez qu'il soit retiré, contactez-nous : <a href="mailto:report@solvixi.com">report@solvixi.com</a>.</p>
  <p>Les résumés générés par l'IA sont dérivés de la <strong>description RSS</strong> publiée par la source originale dans son flux public — il ne s'agit pas de copies textuelles de l'article complet.</p>

  <h2>4. Limitation de responsabilité</h2>
  <p>Le site est fourni "tel quel" sans garantie d'aucune sorte. Nous ne garantissons pas l'exactitude, l'exhaustivité ou la disponibilité du contenu.</p>

  <h2>5. Utilisations interdites</h2>
  <ul>
    <li>Extraction systématique de données (scraping)</li>
    <li>Republication du contenu sans autorisation explicite</li>
    <li>Tentatives de piratage ou d'interférence avec le site</li>
    <li>Utilisation à des fins illégales</li>
  </ul>

  <h2>6. Publicité</h2>
  <p>Le site peut afficher des publicités via Google AdSense et d'autres réseaux. Nous ne sommes pas responsables du contenu de ces publicités.</p>

  <h2>7. Modifications</h2>
  <p>Nous nous réservons le droit de modifier ces conditions à tout moment. La poursuite de l'utilisation du site vaut acceptation.</p>

  <h2>8. Contact</h2>
  <p><a href="mailto:contact@solvixi.com">contact@solvixi.com</a></p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

TERMS_HTML_ES = """\
<!DOCTYPE html>
<html lang="es" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Términos de uso — Atlas News</title>
<meta name="description" content="Términos y condiciones de uso de Atlas News">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Volver al inicio</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Términos de uso</h1>
  <p class="sub">Última actualización: 2026 — Por favor lee estos términos detenidamente</p>

  <h2>1. Aceptación de los términos</h2>
  <p>Al acceder a <strong>Atlas News</strong>, aceptas quedar vinculado por estos Términos de uso.</p>

  <h2>2. Naturaleza del servicio</h2>
  <p>Atlas News es un <strong>agregador de noticias automatizado</strong> que muestra titulares y enlaces a fuentes de noticias externas. No creamos ni editamos ningún contenido periodístico.</p>

  <h2>3. Propiedad intelectual</h2>
  <p>Todos los titulares e imágenes pertenecen a sus respectivos propietarios. Si eres propietario de contenido y deseas que sea eliminado, contáctanos: <a href="mailto:report@solvixi.com">report@solvixi.com</a>.</p>
  <p>Los resúmenes generados por IA se derivan de la <strong>descripción RSS</strong> publicada por la fuente original en su feed público — no son copias literales del texto completo del artículo.</p>

  <h2>4. Limitación de responsabilidad</h2>
  <p>El sitio se proporciona "tal cual" sin garantías de ningún tipo. No garantizamos la exactitud, integridad o disponibilidad del contenido en ningún momento.</p>

  <h2>5. Usos prohibidos</h2>
  <ul>
    <li>Extracción sistemática de datos (scraping)</li>
    <li>Republicación de contenido sin permiso explícito</li>
    <li>Intentos de hackear o interferir con el sitio</li>
    <li>Uso para fines ilegales</li>
  </ul>

  <h2>6. Publicidad</h2>
  <p>El sitio puede mostrar publicidad a través de Google AdSense y otras redes. No somos responsables del contenido de dichos anuncios.</p>

  <h2>7. Modificaciones</h2>
  <p>Nos reservamos el derecho de modificar estos términos en cualquier momento. El uso continuado del sitio implica la aceptación de los términos actualizados.</p>

  <h2>8. Contacto</h2>
  <p><a href="mailto:contact@solvixi.com">contact@solvixi.com</a></p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

TERMS_HTML_TR = """\
<!DOCTYPE html>
<html lang="tr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Kullanim Kosullari — Atlas News</title>
<meta name="description" content="Atlas News kullanim sartlari ve kosullari">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Ana Sayfaya Don</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Kullanim Kosullari</h1>
  <p class="sub">Son guncelleme: 2026 — Siteyi kullanmadan once bu kosullari okuyunuz</p>

  <h2>1. Kosullarin Kabulü</h2>
  <p><strong>Atlas News</strong>'e erisim saglamaniz, bu Kullanim Kosullarini kabul ettiginiz anlamina gelir.</p>

  <h2>2. Hizmetin Niteligj</h2>
  <p>Atlas News, harici haber kaynaklarından basliklari ve bağlantilari görüntüleyen bir <strong>otomatik haber toplayicisidir</strong>. Herhangi bir gazetecilik icerigi olusturmuyoruz veya düzenlemiyoruz.</p>

  <h2>3. Fikri Mülkiyet</h2>
  <p>Tüm haber basliklari ve görseller ilgili sahiplerine aittir. Icerik kaldirma talebi icin: <a href="mailto:report@solvixi.com">report@solvixi.com</a></p>
  <p>Yapay zeka tarafından oluşturulan özetler, orijinal kaynağın genel beslemesinde yayımladığı <strong>RSS açıklamasından</strong> üretilmektedir — bunlar makalenin tam metninin birebir kopyaları değildir.</p>

  <h2>4. Sorumluluk Reddi</h2>
  <p>Site "oldugu gibi" sunulmaktadir. Icerik dogrulugu, eksiksizligi veya kullanilabilirligi konusunda hicbir garanti vermiyoruz.</p>

  <h2>5. Yasak Kullanimlar</h2>
  <ul>
    <li>Sistematik veri cekme (scraping)</li>
    <li>Acik izin olmaksizin icerik yayinlama</li>
    <li>Siteyi hackleme veya mudahale girisimleri</li>
    <li>Yasa disi amaclarla kullanim</li>
  </ul>

  <h2>6. Reklamcilik</h2>
  <p>Site, Google AdSense ve diger ag araciligiyla reklam gösterebilir. Bu reklamlarin iceriginden sorumlu degiliz.</p>

  <h2>7. Degisiklikler</h2>
  <p>Bu kosullari istediğimiz zaman degistirme hakkini sakli tutariz. Siteyi kullanmaya devam etmek degisiklikleri kabul etmek anlamina gelir.</p>

  <h2>8. Iletisim</h2>
  <p><a href="mailto:contact@solvixi.com">contact@solvixi.com</a></p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

# ════════════════════════════════════════════════════════════════════════════
# DMCA / TAKEDOWN PAGES (5 languages)
# ════════════════════════════════════════════════════════════════════════════
DMCA_HTML = """\
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>إشعار DMCA وطلبات إزالة المحتوى — Atlas News</title>
<meta name="description" content="طلبات إزالة المحتوى وإشعارات DMCA على موقع Atlas News — نستجيب خلال 48 ساعة عمل">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; العودة للرئيسية</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>إشعار DMCA وطلبات إزالة المحتوى</h1>
  <p class="sub">آخر تحديث: 2026 — قانون حقوق الملكية الرقمية (DMCA)</p>

  <p><strong>Atlas News</strong> مجمّع إخباري آلي يعرض عناوين المقالات مع روابط تؤدي إلى مصادرها الأصلية. نحترم حقوق الملكية الفكرية ونستجيب لإشعارات DMCA الصحيحة خلال <strong>48–72 ساعة عمل</strong>.</p>

  <h2>1. ماذا نعرض؟</h2>
  <p>نعرض فقط <strong>عناوين الأخبار</strong> مع روابط مصادرها الأصلية استناداً لمبدأ الاقتباس المنصف (Fair Use) للأغراض الإخبارية. لا نعيد نشر المقالات كاملة.</p>

  <h2>2. كيفية تقديم طلب إزالة</h2>
  <p>أرسل إشعار DMCA إلى <a href="mailto:report@solvixi.com">report@solvixi.com</a> متضمناً المعلومات التالية:</p>
  <ul>
    <li>اسمك الكامل ومعلومات الاتصال (بريد إلكتروني + هاتف)</li>
    <li>وصف واضح للعمل المحمي بحقوق النشر الذي تملكه</li>
    <li>الرابط المباشر للمحتوى على موقعنا</li>
    <li>تصريح بحسن النية: "أؤكد أن الاستخدام غير مرخص من قِبل صاحب الحقوق أو القانون"</li>
    <li>تصريح بدقة المعلومات تحت طائلة المسؤولية القانونية</li>
    <li>توقيعك الإلكتروني أو الاسم الكامل</li>
  </ul>

  <h2>3. الإشعار المضاد (Counter-Notice)</h2>
  <p>إذا كنت تعتقد أن الإزالة كانت خطأ، يمكنك تقديم إشعار مضاد إلى <a href="mailto:report@solvixi.com">report@solvixi.com</a> يتضمن: معلومات الاتصال، وصف المحتوى المُزال، وموافقتك على الاختصاص القضائي.</p>

  <h2>4. التواصل</h2>
  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>الإبلاغ عن محتوى</h3>
      <p>طلبات DMCA والإبلاغ عن محتوى مشكل — الرد خلال 48–72 ساعة عمل</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>
  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>الاستفسارات العامة</h3>
      <p>للأسئلة العامة حول الحقوق والتراخيص</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>
</div>
<script src="app.js"></script>
</body>
</html>
"""

DMCA_HTML_EN = """\
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>DMCA Notice &amp; Takedown — Atlas News</title>
<meta name="description" content="How to submit a DMCA takedown request for content on Atlas News">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Back to Home</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>DMCA Notice &amp; Content Takedown</h1>
  <p class="sub">Last updated: 2026 — Digital Millennium Copyright Act</p>

  <p><strong>Atlas News</strong> is an automated news aggregator that displays article headlines with links to their original sources. We respect intellectual property rights and respond to valid DMCA notices within <strong>48–72 business hours</strong>.</p>

  <h2>1. What We Display</h2>
  <p>We display only <strong>article headlines</strong> with links to original sources, based on the Fair Use principle for news aggregation purposes. We do not republish full articles.</p>

  <h2>2. How to Submit a DMCA Takedown Notice</h2>
  <p>Send your DMCA notice to <a href="mailto:report@solvixi.com">report@solvixi.com</a> including:</p>
  <ul>
    <li>Your full legal name and contact information (email + phone)</li>
    <li>A clear description of the copyrighted work you own</li>
    <li>The direct URL of the infringing content on our site</li>
    <li>A good faith statement: "I have a good faith belief that use of the material is not authorized by the copyright owner, its agent, or the law"</li>
    <li>A statement that the information is accurate, under penalty of perjury</li>
    <li>Your electronic or physical signature</li>
  </ul>

  <h2>3. Counter-Notice</h2>
  <p>If you believe content was removed in error, you may submit a counter-notice to <a href="mailto:report@solvixi.com">report@solvixi.com</a> including your contact information, a description of the removed content, and consent to jurisdiction.</p>

  <h2>4. Contact</h2>
  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>Report Content</h3>
      <p>DMCA takedown requests and content reports — response within 48–72 business hours</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>
  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>General Inquiries</h3>
      <p>For general questions about rights and licensing</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>
</div>
<script src="app.js"></script>
</body>
</html>
"""

DMCA_HTML_FR = """\
<!DOCTYPE html>
<html lang="fr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Avis DMCA &amp; Retrait de contenu — Atlas News</title>
<meta name="description" content="Comment soumettre une demande de retrait DMCA sur Atlas News">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Retour à l'accueil</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Avis DMCA &amp; Demandes de retrait</h1>
  <p class="sub">Dernière mise à jour : 2026 — Digital Millennium Copyright Act</p>

  <p><strong>Atlas News</strong> est un agrégateur d'actualités automatisé affichant des titres d'articles avec des liens vers leurs sources originales. Nous respectons les droits de propriété intellectuelle et répondons aux avis DMCA valides dans un délai de <strong>48–72 heures ouvrables</strong>.</p>

  <h2>1. Ce que nous affichons</h2>
  <p>Nous affichons uniquement les <strong>titres d'articles</strong> avec des liens vers les sources originales, conformément au principe d'utilisation équitable pour l'agrégation d'actualités. Nous ne republions pas les articles complets.</p>

  <h2>2. Comment soumettre une demande DMCA</h2>
  <p>Envoyez votre avis DMCA à <a href="mailto:report@solvixi.com">report@solvixi.com</a> en incluant :</p>
  <ul>
    <li>Votre nom complet et coordonnées (e-mail + téléphone)</li>
    <li>Une description claire de l'œuvre protégée par droit d'auteur</li>
    <li>L'URL directe du contenu litigieux sur notre site</li>
    <li>Une déclaration de bonne foi : "J'ai la conviction de bonne foi que l'utilisation du contenu n'est pas autorisée par le titulaire, son agent ou la loi"</li>
    <li>Une déclaration d'exactitude sous peine de parjure</li>
    <li>Votre signature électronique ou physique</li>
  </ul>

  <h2>3. Contre-notification</h2>
  <p>Si vous pensez qu'un contenu a été retiré par erreur, envoyez une contre-notification à <a href="mailto:report@solvixi.com">report@solvixi.com</a> avec vos coordonnées, une description du contenu retiré et votre consentement à la juridiction compétente.</p>

  <h2>4. Contact</h2>
  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>Signaler un contenu</h3>
      <p>Demandes DMCA et signalements — réponse sous 48–72 heures ouvrables</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>
  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>Questions générales</h3>
      <p>Pour toute question sur les droits et licences</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>
</div>
<script src="app.js"></script>
</body>
</html>
"""

DMCA_HTML_ES = """\
<!DOCTYPE html>
<html lang="es" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Aviso DMCA &amp; Eliminación de contenido — Atlas News</title>
<meta name="description" content="Cómo enviar una solicitud de eliminación DMCA en Atlas News">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Volver al inicio</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Aviso DMCA &amp; Eliminación de contenido</h1>
  <p class="sub">Última actualización: 2026 — Digital Millennium Copyright Act</p>

  <p><strong>Atlas News</strong> es un agregador de noticias automatizado que muestra titulares de artículos con enlaces a sus fuentes originales. Respetamos los derechos de propiedad intelectual y respondemos a los avisos DMCA válidos en un plazo de <strong>48–72 horas hábiles</strong>.</p>

  <h2>1. Lo que mostramos</h2>
  <p>Mostramos únicamente <strong>titulares de artículos</strong> con enlaces a las fuentes originales, basándonos en el principio de uso legítimo para la agregación de noticias. No republicamos artículos completos.</p>

  <h2>2. Cómo enviar una solicitud DMCA</h2>
  <p>Envía tu aviso DMCA a <a href="mailto:report@solvixi.com">report@solvixi.com</a> incluyendo:</p>
  <ul>
    <li>Tu nombre completo y datos de contacto (e-mail + teléfono)</li>
    <li>Una descripción clara de la obra protegida por derechos de autor</li>
    <li>La URL directa del contenido infractor en nuestro sitio</li>
    <li>Una declaración de buena fe: "Tengo la convicción de buena fe de que el uso del material no está autorizado por el titular, su agente ni la ley"</li>
    <li>Una declaración de exactitud bajo pena de perjurio</li>
    <li>Tu firma electrónica o física</li>
  </ul>

  <h2>3. Contranotificación</h2>
  <p>Si crees que un contenido fue eliminado por error, puedes enviar una contranotificación a <a href="mailto:report@solvixi.com">report@solvixi.com</a> con tus datos de contacto, descripción del contenido eliminado y consentimiento de jurisdicción.</p>

  <h2>4. Contacto</h2>
  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>Reportar contenido</h3>
      <p>Solicitudes DMCA y reportes de contenido — respuesta en 48–72 horas hábiles</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>
  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>Consultas generales</h3>
      <p>Para preguntas sobre derechos y licencias</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>
</div>
<script src="app.js"></script>
</body>
</html>
"""

DMCA_HTML_TR = """\
<!DOCTYPE html>
<html lang="tr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>DMCA Bildirimi ve Icerik Kaldirma — Atlas News</title>
<meta name="description" content="Atlas News'de DMCA kaldirma talepleri nasil gonderilir">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Ana Sayfaya Don</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>DMCA Bildirimi &amp; Icerik Kaldirma</h1>
  <p class="sub">Son guncelleme: 2026 — Dijital Milenyum Telif Hakki Yasasi</p>

  <p><strong>Atlas News</strong>, makale basliklarini orijinal kaynaklarina yonlendiren baglantilarla birlikte gosteren otomatik bir haber toplayicisidir. Fikri mulkiyet haklarini saygiyla karsiliyor ve gecerli DMCA bildirimlerine <strong>48-72 is saati</strong> icinde yanit veriyoruz.</p>

  <h2>1. Ne Gosteriyoruz?</h2>
  <p>Yalnizca haber toplamayi kapsayan adil kullanim ilkesine dayanarak, orijinal kaynaklara baglanan <strong>makale basliklarini</strong> gosteriyoruz. Tam makaleleri yeniden yayinlamiyoruz.</p>

  <h2>2. DMCA Kaldirma Talebi Nasil Gonderilir?</h2>
  <p>DMCA bildiriminizi asagidaki bilgileri icererek <a href="mailto:report@solvixi.com">report@solvixi.com</a> adresine gonderin:</p>
  <ul>
    <li>Tam adiniz ve iletisim bilgileriniz (e-posta + telefon)</li>
    <li>Sahip oldugunuz telif hakki korumasindaki eserin acik aciklamasi</li>
    <li>Sitemizde ihlal eden icerigin dogrudan URL'si</li>
    <li>Iyiniyet beyani: "Materyal kullaniminin telif hakki sahibi, temsilcisi veya yasa tarafindan yetkilendirilmedigine iyiniyetle inaniyorum"</li>
    <li>Yanlis olma durumunda yasal yaptirima tabi olacagina dair dogru bilgi beyani</li>
    <li>Elektronik veya fiziksel imzaniz</li>
  </ul>

  <h2>3. Karsi Bildirim</h2>
  <p>Bir icerigin yanlistikla kaldirildigina inaniyorsaniz, <a href="mailto:report@solvixi.com">report@solvixi.com</a> adresine iletisim bilgilerinizi, kaldirilan icerigin aciklamasini ve yargi yetkisine riza gosterdiginizi iceren karsi bildirim gonderebilirsiniz.</p>

  <h2>4. Iletisim</h2>
  <div class="info-card">
    <span class="info-card-icon">⚠️</span>
    <div>
      <h3>Icerik Bildirin</h3>
      <p>DMCA talepleri ve icerik bildirimleri — 48-72 is saati icinde yanit</p>
      <a href="mailto:report@solvixi.com">report@solvixi.com</a>
    </div>
  </div>
  <div class="info-card">
    <span class="info-card-icon">📧</span>
    <div>
      <h3>Genel Sorular</h3>
      <p>Haklar ve lisanslar hakkinda genel sorular icin</p>
      <a href="mailto:contact@solvixi.com">contact@solvixi.com</a>
    </div>
  </div>
</div>
<script src="app.js"></script>
</body>
</html>
"""

# ════════════════════════════════════════════════════════════════════════════
# ADVERTISE PAGES (5 languages)
# ════════════════════════════════════════════════════════════════════════════
ADVERTISE_HTML = """\
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>أعلن معنا — Atlas News</title>
<meta name="description" content="أعلن على Atlas News وصل إلى جمهور عالمي بـ 5 لغات — عروض الإعلانات والشراكات">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; العودة للرئيسية</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>أعلن معنا</h1>
  <p class="sub">صل إلى جمهور عالمي متنوع بـ 5 لغات في منصة إخبارية موثوقة</p>

  <div class="stat-row">
    <div class="stat-box2"><div class="stat-box2-val">5</div><div class="stat-box2-lbl">لغات عالمية</div></div>
    <div class="stat-box2"><div class="stat-box2-val">500+</div><div class="stat-box2-lbl">مصدر إخباري</div></div>
    <div class="stat-box2"><div class="stat-box2-val">24/7</div><div class="stat-box2-lbl">تحديث مستمر</div></div>
  </div>

  <h2>لماذا تُعلن معنا؟</h2>
  <ul>
    <li><strong>جمهور متعدد اللغات:</strong> العربية، الإنجليزية، الفرنسية، الإسبانية، التركية — تغطية حقيقية لـ 5 مناطق جغرافية مختلفة</li>
    <li><strong>محتوى ذو صلة:</strong> زوار يبحثون عن أخبار في مجالات السياسة والاقتصاد والتقنية والرياضة وأكثر</li>
    <li><strong>بيئة آمنة للعلامات التجارية:</strong> محتوى إخباري موثوق ومُصنَّف بدقة</li>
    <li><strong>PWA + جميع الأجهزة:</strong> يعمل بسلاسة على الموبايل، التابلت، وسطح المكتب</li>
  </ul>

  <h2>أشكال الإعلانات المتاحة</h2>
  <div class="ad-format">
    <span class="ad-format-name">🖼️ بانر الرأس</span>
    <span class="ad-format-size">728×90 / 320×50 (موبايل)</span>
  </div>
  <div class="ad-format">
    <span class="ad-format-name">📐 مستطيل كبير</span>
    <span class="ad-format-size">336×280 / 300×250</span>
  </div>
  <div class="ad-format">
    <span class="ad-format-name">📏 عمود جانبي</span>
    <span class="ad-format-size">160×600 / 300×600</span>
  </div>
  <div class="ad-format">
    <span class="ad-format-name">📌 بين المقالات</span>
    <span class="ad-format-size">In-feed native ads</span>
  </div>
  <div class="ad-format">
    <span class="ad-format-name">🤝 محتوى مدعوم</span>
    <span class="ad-format-size">Sponsored content</span>
  </div>

  <div class="cta-box">
    <h2>ابدأ الإعلان اليوم</h2>
    <p>تواصل معنا للحصول على عرض مخصص يناسب ميزانيتك وأهدافك التسويقية</p>
    <a href="mailto:ads@solvixi.com" class="cta-btn">📧 ads@solvixi.com</a>
  </div>

  <h2>الشراكات الاستراتيجية</h2>
  <p>نرحب أيضاً بالشراكات الاستراتيجية مع المنصات الإعلامية والعلامات التجارية والمؤسسات الراغبة في الوصول إلى جمهورنا المتنوع. تواصل معنا لمناقشة فرص التعاون.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ADVERTISE_HTML_EN = """\
<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Advertise with Us — Atlas News</title>
<meta name="description" content="Advertise on Atlas News and reach a global audience in 5 languages — ad formats and partnership opportunities">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Back to Home</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Advertise with Us</h1>
  <p class="sub">Reach a diverse global audience across 5 languages on a trusted news platform</p>

  <div class="stat-row">
    <div class="stat-box2"><div class="stat-box2-val">5</div><div class="stat-box2-lbl">Languages</div></div>
    <div class="stat-box2"><div class="stat-box2-val">500+</div><div class="stat-box2-lbl">News Sources</div></div>
    <div class="stat-box2"><div class="stat-box2-val">24/7</div><div class="stat-box2-lbl">Live Updates</div></div>
  </div>

  <h2>Why Advertise with Atlas News?</h2>
  <ul>
    <li><strong>Multilingual audience:</strong> Arabic, English, French, Spanish, Turkish — genuine coverage of 5 distinct geographic markets</li>
    <li><strong>Engaged readers:</strong> Visitors actively seeking news across politics, economy, tech, sports and more</li>
    <li><strong>Brand-safe environment:</strong> Trusted, well-categorized news content</li>
    <li><strong>PWA + all devices:</strong> Seamless experience on mobile, tablet, and desktop</li>
  </ul>

  <h2>Available Ad Formats</h2>
  <div class="ad-format">
    <span class="ad-format-name">🖼️ Leaderboard Banner</span>
    <span class="ad-format-size">728×90 / 320×50 (mobile)</span>
  </div>
  <div class="ad-format">
    <span class="ad-format-name">📐 Large Rectangle</span>
    <span class="ad-format-size">336×280 / 300×250</span>
  </div>
  <div class="ad-format">
    <span class="ad-format-name">📏 Sidebar Column</span>
    <span class="ad-format-size">160×600 / 300×600</span>
  </div>
  <div class="ad-format">
    <span class="ad-format-name">📌 In-feed Ads</span>
    <span class="ad-format-size">Native in-article placement</span>
  </div>
  <div class="ad-format">
    <span class="ad-format-name">🤝 Sponsored Content</span>
    <span class="ad-format-size">Branded content integration</span>
  </div>

  <div class="cta-box">
    <h2>Start Advertising Today</h2>
    <p>Contact us for a custom proposal tailored to your budget and marketing goals</p>
    <a href="mailto:ads@solvixi.com" class="cta-btn">📧 ads@solvixi.com</a>
  </div>

  <h2>Strategic Partnerships</h2>
  <p>We also welcome strategic partnerships with media platforms, brands, and organizations looking to reach our diverse audience. Contact us to discuss collaboration opportunities.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ADVERTISE_HTML_FR = """\
<!DOCTYPE html>
<html lang="fr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Faites de la publicité avec nous — Atlas News</title>
<meta name="description" content="Faites de la publicité sur Atlas News et touchez un public mondial en 5 langues">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Retour à l'accueil</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Publicité avec nous</h1>
  <p class="sub">Touchez un public mondial diversifié en 5 langues sur une plateforme d'actualités de confiance</p>

  <div class="stat-row">
    <div class="stat-box2"><div class="stat-box2-val">5</div><div class="stat-box2-lbl">Langues</div></div>
    <div class="stat-box2"><div class="stat-box2-val">500+</div><div class="stat-box2-lbl">Sources</div></div>
    <div class="stat-box2"><div class="stat-box2-val">24/7</div><div class="stat-box2-lbl">Mises à jour</div></div>
  </div>

  <h2>Pourquoi nous choisir ?</h2>
  <ul>
    <li><strong>Audience multilingue :</strong> Arabe, anglais, français, espagnol, turc — 5 marchés géographiques distincts</li>
    <li><strong>Lecteurs engagés :</strong> Visiteurs en quête d'actualités en politique, économie, tech, sport et plus</li>
    <li><strong>Environnement brand-safe :</strong> Contenu d'actualité fiable et bien catégorisé</li>
    <li><strong>PWA + tous appareils :</strong> Expérience fluide sur mobile, tablette et bureau</li>
  </ul>

  <h2>Formats publicitaires disponibles</h2>
  <div class="ad-format"><span class="ad-format-name">🖼️ Bannière leaderboard</span><span class="ad-format-size">728×90 / 320×50</span></div>
  <div class="ad-format"><span class="ad-format-name">📐 Grand rectangle</span><span class="ad-format-size">336×280 / 300×250</span></div>
  <div class="ad-format"><span class="ad-format-name">📏 Colonne latérale</span><span class="ad-format-size">160×600 / 300×600</span></div>
  <div class="ad-format"><span class="ad-format-name">📌 Publicité in-feed</span><span class="ad-format-size">Native dans les articles</span></div>
  <div class="ad-format"><span class="ad-format-name">🤝 Contenu sponsorisé</span><span class="ad-format-size">Intégration de marque</span></div>

  <div class="cta-box">
    <h2>Commencez dès aujourd'hui</h2>
    <p>Contactez-nous pour une proposition personnalisée adaptée à votre budget</p>
    <a href="mailto:ads@solvixi.com" class="cta-btn">📧 ads@solvixi.com</a>
  </div>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ADVERTISE_HTML_ES = """\
<!DOCTYPE html>
<html lang="es" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Publicidad — Atlas News</title>
<meta name="description" content="Anúnciate en Atlas News y llega a una audiencia global en 5 idiomas">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Volver al inicio</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Publicidad con nosotros</h1>
  <p class="sub">Llega a una audiencia global diversa en 5 idiomas en una plataforma de noticias de confianza</p>

  <div class="stat-row">
    <div class="stat-box2"><div class="stat-box2-val">5</div><div class="stat-box2-lbl">Idiomas</div></div>
    <div class="stat-box2"><div class="stat-box2-val">500+</div><div class="stat-box2-lbl">Fuentes</div></div>
    <div class="stat-box2"><div class="stat-box2-val">24/7</div><div class="stat-box2-lbl">Actualizaciones</div></div>
  </div>

  <h2>¿Por qué anunciarte con nosotros?</h2>
  <ul>
    <li><strong>Audiencia multilingüe:</strong> Árabe, inglés, francés, español, turco — 5 mercados geográficos distintos</li>
    <li><strong>Lectores comprometidos:</strong> Visitantes en busca de noticias de política, economía, tecnología, deportes y más</li>
    <li><strong>Entorno brand-safe:</strong> Contenido informativo fiable y bien categorizado</li>
    <li><strong>PWA + todos los dispositivos:</strong> Experiencia fluida en móvil, tablet y escritorio</li>
  </ul>

  <h2>Formatos publicitarios disponibles</h2>
  <div class="ad-format"><span class="ad-format-name">🖼️ Banner leaderboard</span><span class="ad-format-size">728×90 / 320×50</span></div>
  <div class="ad-format"><span class="ad-format-name">📐 Rectángulo grande</span><span class="ad-format-size">336×280 / 300×250</span></div>
  <div class="ad-format"><span class="ad-format-name">📏 Columna lateral</span><span class="ad-format-size">160×600 / 300×600</span></div>
  <div class="ad-format"><span class="ad-format-name">📌 Anuncios in-feed</span><span class="ad-format-size">Nativo entre artículos</span></div>
  <div class="ad-format"><span class="ad-format-name">🤝 Contenido patrocinado</span><span class="ad-format-size">Integración de marca</span></div>

  <div class="cta-box">
    <h2>Empieza hoy</h2>
    <p>Contáctanos para una propuesta personalizada adaptada a tu presupuesto</p>
    <a href="mailto:ads@solvixi.com" class="cta-btn">📧 ads@solvixi.com</a>
  </div>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ADVERTISE_HTML_TR = """\
<!DOCTYPE html>
<html lang="tr" dir="ltr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<title>Reklam Ver — Atlas News</title>
<meta name="description" content="Atlas News'te reklam verin ve 5 dilde kuresel kitlelere ulasin">
<link rel="stylesheet" href="style.css">
<style>""" + _PAGE_CSS + """body{direction:ltr;font-family:'Roboto','Segoe UI',Arial,sans-serif}</style>
</head>
<body>
<div class="top-bar"><div class="top-bar-inner">
  <a href="index.html" class="back">&#8592; Ana Sayfaya Don</a>
  <button id="theme-toggle" class="theme-btn">🌙</button>
</div></div>
<div class="page">
  <h1>Reklam Verin</h1>
  <p class="sub">5 dilde guvenilir bir haber platformunda cesitli kuresel kitlelere ulasin</p>

  <div class="stat-row">
    <div class="stat-box2"><div class="stat-box2-val">5</div><div class="stat-box2-lbl">Dil</div></div>
    <div class="stat-box2"><div class="stat-box2-val">500+</div><div class="stat-box2-lbl">Kaynak</div></div>
    <div class="stat-box2"><div class="stat-box2-val">24/7</div><div class="stat-box2-lbl">Guncelleme</div></div>
  </div>

  <h2>Neden Bizimle Reklam Verin?</h2>
  <ul>
    <li><strong>Cok dilli kitle:</strong> Arapca, Ingilizce, Fransizca, Ispanyolca, Turkce — 5 farkli cografya</li>
    <li><strong>Aktif okuyucular:</strong> Siyaset, ekonomi, teknoloji, spor ve daha fazlasinda haber arayan ziyaretciler</li>
    <li><strong>Marka guvenligi:</strong> Guvenilir, iyi kategorize edilmis haber icerigi</li>
    <li><strong>PWA + tum cihazlar:</strong> Mobil, tablet ve masaustu uyumlu kesintisiz deneyim</li>
  </ul>

  <h2>Mevcut Reklam Formatlari</h2>
  <div class="ad-format"><span class="ad-format-name">🖼️ Leaderboard Banner</span><span class="ad-format-size">728×90 / 320×50</span></div>
  <div class="ad-format"><span class="ad-format-name">📐 Buyuk Dikdortgen</span><span class="ad-format-size">336×280 / 300×250</span></div>
  <div class="ad-format"><span class="ad-format-name">📏 Yan Sutun</span><span class="ad-format-size">160×600 / 300×600</span></div>
  <div class="ad-format"><span class="ad-format-name">📌 In-feed Reklamlar</span><span class="ad-format-size">Makale arasi yerlesim</span></div>
  <div class="ad-format"><span class="ad-format-name">🤝 Sponsorlu Icerik</span><span class="ad-format-size">Marka entegrasyonu</span></div>

  <div class="cta-box">
    <h2>Bugun Baslayin</h2>
    <p>Butcenize ve pazarlama hedeflerinize uygun ozel bir teklif icin bize ulasin</p>
    <a href="mailto:ads@solvixi.com" class="cta-btn">📧 ads@solvixi.com</a>
  </div>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ROBOTS_TXT = """\
# Atlas News — robots.txt
# https://atlasnews.solvixi.com

User-agent: Googlebot
Allow: /
Disallow: /admin

User-agent: Googlebot-News
Allow: /

User-agent: Bingbot
Allow: /
Disallow: /admin
Crawl-delay: 5

User-agent: SemrushBot
Crawl-delay: 30
Disallow: /article/

User-agent: AhrefsBot
Crawl-delay: 30
Disallow: /article/

User-agent: MJ12bot
Disallow: /

User-agent: DotBot
Disallow: /

User-agent: GPTBot
Crawl-delay: 30

User-agent: PerplexityBot
Crawl-delay: 30

User-agent: anthropic-ai
Crawl-delay: 30

User-agent: *
Allow: /
Disallow: /admin
Crawl-delay: 10

Sitemap: https://atlasnews.solvixi.com/sitemap.xml
Sitemap: https://atlasnews.solvixi.com/news-sitemap.xml
Sitemap: https://atlasnews.solvixi.com/sitemap-articles.xml
"""

# ──────────────────────────────────────────────────────────────────────────────
# CLOUDFLARE PAGES _headers — Security + Cache-Control
# Written to the domain root only (during EN generation).
# Docs: https://developers.cloudflare.com/pages/configuration/headers/
# ──────────────────────────────────────────────────────────────────────────────
CLOUDFLARE_HEADERS = """\
# Security headers — apply to every route
/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  X-XSS-Protection: 1; mode=block
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()

# HTML pages — short cache, revalidate quickly (site updates every 6h in CI)
/*.html
  Cache-Control: public, max-age=3600, stale-while-revalidate=43200

# CSS / JS — short browser cache + background revalidation.
# SW handles stale-asset busting via content-hash in cache name (news-v1-XXXXXXXX).
# Cloudflare Pages edge cache is auto-purged on every deploy.
# 1-hour max-age prevents network failures on slow connections from breaking layout.
/style.css
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400

/*/style.css
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400

/app.js
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400

/*/app.js
  Cache-Control: public, max-age=3600, stale-while-revalidate=86400

# Service worker — never cache (must always be fresh)
/sw.js
  Cache-Control: no-cache, no-store, must-revalidate

# Favicon / icons
/favicon.svg
  Cache-Control: public, max-age=2592000

/favicon-32.png
  Cache-Control: public, max-age=2592000

/icon-192.png
  Cache-Control: public, max-age=2592000

/icon-512.png
  Cache-Control: public, max-age=2592000

# RSS feeds — refresh faster
/rss*.xml
  Cache-Control: public, max-age=1800, stale-while-revalidate=7200
"""

# ads.txt — placed at the DOMAIN ROOT only (written during EN generation).
# Replace placeholder publisher IDs with your real IDs before going live.
ADS_TXT = """\
# ads.txt — atlasnews.solvixi.com
# Standard: https://iabtechlab.com/ads-txt/
#
# ════════════════════════════════════════════════════════════════════════════
# HOW TO ACTIVATE:
#   1. Go to Google AdSense → Account → Account information → Publisher ID
#   2. Replace pub-XXXXXXXXXXXXXXXX with your real Publisher ID
#   3. Remove the leading "#" from the google.com line below
#   4. Commit & push → deploys automatically on next CI run
# ════════════════════════════════════════════════════════════════════════════
#
# ── Google AdSense (uncomment + replace ID when approved) ────────────────────
# google.com, pub-XXXXXXXXXXXXXXXX, DIRECT, f08c47fec0942fa0
#
# ── Media.net (add when account is approved) ──────────────────────────────────
# media.net, XXXXXXXXX, DIRECT
#
# ── Amazon Publisher Services (add when enrolled) ────────────────────────────
# amazon.com, XXXXXXXXXXXXXXXXXXXX, DIRECT
#
# ── Ezoic (add when enrolled — includes AdSense reseller line) ───────────────
# ezoic.com, XXXXXXX, DIRECT, XXXXXXXXXXXXXXXX
# google.com, pub-XXXXXXXXXXXXXXXX, RESELLER, f08c47fec0942fa0
#
# Contact: ads@solvixi.com
"""


def _make_sw(site_url: str = "") -> str:
    """Generate a minimal Service Worker for PWA offline caching.

    Cache name embeds a content-hash of CSS+JS so it changes automatically
    on every deploy that modifies styles or scripts.  The activate handler
    deletes every cache whose name != CACHE, so stale assets are purged the
    moment the new SW takes control — no manual version bumps needed.
    """
    import hashlib as _hl
    # Hash the two assets that change most often; 8 hex chars is plenty.
    _h = _hl.md5((STYLE_CSS + APP_JS).encode("utf-8")).hexdigest()[:8]
    _cache_name = f"news-v1-{_h}"
    base = site_url.rstrip("/") or "."
    return f"""// Service Worker — auto-generated (cache: {_cache_name})
const CACHE = '{_cache_name}';
const STATIC = [
  '{base}/style.css',
  '{base}/app.js',
];

self.addEventListener('install', e => {{
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)).catch(() => {{}}));
  self.skipWaiting();
}});
self.addEventListener('activate', e => {{
  // Delete ALL old caches — any name that isn't the current hash is stale
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
}});
self.addEventListener('fetch', e => {{
  // Network-first for HTML pages (always get fresh news)
  if (e.request.destination === 'document') {{
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }}
  // Cache-first for static assets (CSS/JS are versioned via SW cache name)
  e.respondWith(
    caches.match(e.request).then(cached => {{
      if (cached) return cached;
      return fetch(e.request).then(resp => {{
        if (resp && resp.status === 200 && resp.type === 'basic') {{
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }}
        return resp;
      }});
    }})
  );
}});
"""


def _write_static_assets(out_dir: str = OUTPUT_DIR, lang: str = "ar",
                         site_url: str = "") -> None:
    """Write CSS, JS, SW, favicons and static HTML pages to out_dir."""
    os.makedirs(out_dir, exist_ok=True)

    assets = {
        "style.css":   STYLE_CSS,
        "app.js":      APP_JS,
        "robots.txt":  ROBOTS_TXT,
        "sw.js":       _make_sw(site_url),
        "favicon.svg": FAVICON_SVG,
        "og-image.svg": OG_IMAGE_SVG,
    }
    for filename, content in assets.items():
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
            f.write(content)
    # Domain-root-only files — only write for EN (which deploys to static/)
    if lang == "en":
        with open(os.path.join(out_dir, "ads.txt"), "w", encoding="utf-8") as f:
            f.write(ADS_TXT)
        with open(os.path.join(out_dir, "_headers"), "w", encoding="utf-8") as f:
            f.write(CLOUDFLARE_HEADERS)
        # og-image.png: write once — user can replace with a Canva-designed PNG
        # and it will NOT be overwritten on subsequent runs.
        _og_png_path = os.path.join(out_dir, "og-image.png")
        if not os.path.exists(_og_png_path):
            with open(_og_png_path, "wb") as _f:
                _f.write(_gen_og_png())
    # Minimal 32×32 transparent PNG favicon fallback (only write if not present)
    _FAVICON_32_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00 \x00\x00\x00 "
        b"\x08\x06\x00\x00\x00szz\xf4\x00\x00\x00\x16IDATx\x9cc\xf8\x0f"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    _fav32 = os.path.join(out_dir, "favicon-32.png")
    if not os.path.exists(_fav32):
        with open(_fav32, "wb") as _f:
            _f.write(_FAVICON_32_PNG)

    _privacy_map   = {"en": PRIVACY_HTML_EN,   "fr": PRIVACY_HTML_FR,   "es": PRIVACY_HTML_ES,   "tr": PRIVACY_HTML_TR}
    _about_map     = {"en": ABOUT_HTML_EN,     "fr": ABOUT_HTML_FR,     "es": ABOUT_HTML_ES,     "tr": ABOUT_HTML_TR}
    _contact_map   = {"en": CONTACT_HTML_EN,   "fr": CONTACT_HTML_FR,   "es": CONTACT_HTML_ES,   "tr": CONTACT_HTML_TR}
    _terms_map     = {"en": TERMS_HTML_EN,     "fr": TERMS_HTML_FR,     "es": TERMS_HTML_ES,     "tr": TERMS_HTML_TR}
    _dmca_map      = {"en": DMCA_HTML_EN,      "fr": DMCA_HTML_FR,      "es": DMCA_HTML_ES,      "tr": DMCA_HTML_TR}
    _advertise_map = {"en": ADVERTISE_HTML_EN, "fr": ADVERTISE_HTML_FR, "es": ADVERTISE_HTML_ES, "tr": ADVERTISE_HTML_TR}

    static_pages = [
        ("privacy.html",   _privacy_map.get(lang, PRIVACY_HTML)),
        ("about.html",     _about_map.get(lang, ABOUT_HTML)),
        ("contact.html",   _contact_map.get(lang, CONTACT_HTML)),
        ("terms.html",     _terms_map.get(lang, TERMS_HTML)),
        ("dmca.html",      _dmca_map.get(lang, DMCA_HTML)),
        ("advertise.html", _advertise_map.get(lang, ADVERTISE_HTML)),
    ]

    # Compute root URL for hreflang (strip language prefix from site_url)
    _surl = site_url.rstrip("/")
    _lprefix = _LANG_PATHS.get(lang, "")
    if _surl and _lprefix and _surl.endswith(_lprefix):
        _sp_root_url = _surl[: -len(_lprefix)].rstrip("/")
    else:
        _sp_root_url = _surl  # EN: site_url is already the root

    for filename, content in static_pages:
        # Inject <link rel="canonical"> and hreflang into each static page <head>
        if _sp_root_url:
            _canonical = f"{_surl}/{filename}"
            _hreflang  = _hreflang_links(_sp_root_url, filename)
            _inject    = f'  <link rel="canonical" href="{_canonical}">\n{_hreflang}\n'
            content    = content.replace("</head>", _inject + "</head>", 1)
        dest = os.path.join(out_dir, filename)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

PREVIEW_PER_CAT = 8  # articles shown on home page per category (2 full rows of 4)


def _source_filter_strip(articles: list[dict], cat_sources: list[dict],
                          color: str, s: dict) -> str:
    """Horizontal chip strip to filter articles by source on category pages.

    Rendered only when ≥ 2 sources have articles.
    Uses the same SOURCE_AR_NAME display-name mapping as _card() so that
    chip data-src values always match card data-source attributes.
    """
    if not articles or len(cat_sources) < 2:
        return ""

    # Count articles per display-name (matches _card mapping)
    counts: dict[str, int] = {}
    for art in articles:
        display = SOURCE_AR_NAME.get(art["source"], art["source"])
        counts[display] = counts.get(display, 0) + 1

    if len(counts) < 2:
        return ""

    # Build chips in config source order
    ordered: list[tuple[str, int]] = []
    seen: set[str] = set()
    for src in cat_sources:
        display = SOURCE_AR_NAME.get(src["name"], src["name"])
        if display in counts and display not in seen:
            ordered.append((display, counts[display]))
            seen.add(display)
    # Sources present in DB but missing from config go at the end
    for display, cnt in counts.items():
        if display not in seen:
            ordered.append((display, cnt))

    if len(ordered) < 2:
        return ""

    total   = len(articles)
    all_lbl = s.get("src_all", "All")
    no_lbl  = s.get("src_no_results", "No articles from this source")

    chips = (
        f'<button class="src-chip sc-active" data-src="__all__">'
        f'{esc(all_lbl)} <span class="sc-n">{total}</span></button>'
    )
    for display, cnt in ordered:
        chips += (
            f'<button class="src-chip" data-src="{esc(display)}">'
            f'{esc(display)} <span class="sc-n">{cnt}</span></button>'
        )

    return (
        f'<div class="src-strip" style="--sc-color:{esc(color)}">'
        f'<div class="src-chips">{chips}</div>'
        f'</div>'
        f'<p class="src-empty" id="src-empty">{esc(no_lbl)}</p>'
    )


def _card(art: dict, slug: str, use_article_page: bool = True,
          s: dict | None = None,
          cluster_map: dict | None = None,
          site_url: str = "") -> str:
    import urllib.parse as _up
    color    = CATEGORY_COLORS.get(slug, DEFAULT_COLOR)
    gradient = CATEGORY_GRADIENTS.get(slug, DEFAULT_GRADIENT)
    title_raw  = " ".join(art["title"].split())
    title      = esc(title_raw)
    url        = safe_url(art["url"])
    source_raw = art["source"]
    source     = esc(SOURCE_AR_NAME.get(source_raw, source_raw))
    date       = esc(art.get("date", ""))
    image      = safe_url(art.get("image", ""))
    ai_summary = art.get("ai_summary", "")
    # Build RFC 3339 datetime for the <time> element (enables JS relative time)
    _scraped_raw = art.get("scraped_at", "")
    _dt_attr = (
        _scraped_raw.replace(" ", "T") + "+00:00"
        if len(_scraped_raw) >= 19
        else (art.get("date", "") + "T00:00:00+00:00")
    )

    # ── Spectrum badge (source classification) ────────────────────────────────
    _sp_type = _SPECTRUM_MAP.get(source_raw, "")
    if _sp_type and s:
        _sp_label = s.get(f"spectrum_{_sp_type}", _sp_type)
        _sp_css   = _SPECTRUM_CSS.get(_sp_type, "sp-wire")
        spectrum_badge = f'<span class="spectrum-badge {_sp_css}" title="{esc(_sp_label)}">{esc(_sp_label)}</span>'
    else:
        spectrum_badge = ""

    # ── Cluster badge (multi-source story coverage) ───────────────────────────
    cluster_badge = ""
    if cluster_map and s:
        _cl = cluster_map.get(art.get("url", ""))
        if _cl and _cl.get("source_count", 0) >= 2:
            _n = _cl["source_count"]
            _tpl = s.get("cluster_sources", "📡 {n}")
            _cl_label = _tpl.format(n=_n)
            _sources_title = ", ".join(_cl.get("sources", [])[:6])
            cluster_badge = (
                f'<span class="cluster-badge" '
                f'title="{esc(_sources_title)}">'
                f'{esc(_cl_label)}</span>'
            )

    if image and image != "#":
        bg_html = (
            f'<div class="card-bg">'
            f'<img class="card-bg-img" src="{image}" alt="{esc(title_raw)}" loading="lazy" '
            f'onerror="this.closest(\'article\').classList.add(\'card--no-img\')">'
            f'</div>'
        )
        extra_cls = ""
    else:
        bg_html = f'<div class="card-no-img">📰</div>'
        extra_cls = " card--no-img"

    # ── Share buttons ────────────────────────────────────────────────────────
    _raw_url  = art["url"]
    # Share our own article page URL when available (better for traffic & SEO).
    # Fall back to the original source URL for video/external-only cards.
    if use_article_page and site_url:
        import hashlib as _hl2
        _share_url = (
            site_url.rstrip("/") + "/article/"
            + _hl2.md5(_raw_url.encode("utf-8")).hexdigest()[:12]
            + ".html"
        )
    else:
        _share_url = _raw_url
    _wa_href  = "https://wa.me/?text=" + _up.quote(title_raw + "\n\n" + _share_url, safe="")
    _x_href   = ("https://x.com/intent/tweet?text=" + _up.quote(title_raw, safe="")
                 + "&url=" + _up.quote(_share_url, safe=""))
    _tg_href  = ("https://t.me/share/url?url=" + _up.quote(_share_url, safe="")
                 + "&text=" + _up.quote(title_raw, safe=""))
    _fb_href  = "https://www.facebook.com/sharer/sharer.php?u=" + _up.quote(_share_url, safe="")
    share_html = (
        f'<div class="card-share">'
        f'<a href="{esc(_wa_href)}" class="share-btn share-wa" target="_blank" '
        f'rel="noopener noreferrer" title="WhatsApp" aria-label="WhatsApp">W</a>'
        f'<a href="{esc(_fb_href)}" class="share-btn share-fb" target="_blank" '
        f'rel="noopener noreferrer" title="Facebook" aria-label="Facebook">f</a>'
        f'<a href="{esc(_x_href)}" class="share-btn share-x" target="_blank" '
        f'rel="noopener noreferrer" title="X / Twitter" aria-label="X">𝕏</a>'
        f'<a href="{esc(_tg_href)}" class="share-btn share-tg" target="_blank" '
        f'rel="noopener noreferrer" title="Telegram" aria-label="Telegram">✈</a>'
        f'<button class="share-btn share-copy" data-copy="{esc(_share_url)}" '
        f'title="Copy link" aria-label="Copy link">⧉</button>'
        f'</div>'
    )

    # ── Summary (shown on hover / always on no-img cards) ───────────────────
    ai_html = ""
    if ai_summary:
        ai_html = (
            f'<div class="card-ai">'
            f'{esc(ai_summary)}'
            f'</div>'
        )

    # Determine card link: internal article page or external URL
    if use_article_page:
        import hashlib as _hl
        _art_hash = _hl.md5(art["url"].encode("utf-8")).hexdigest()[:12]
        _card_href = f"article/{_art_hash}.html"
        _card_target = ""
        _card_rel = ""
    else:
        _card_href = url
        _card_target = ' target="_blank"'
        _card_rel = ' rel="noopener noreferrer nofollow"'

    _play_btn = '<div class="card-play" aria-hidden="true"></div>' if slug.startswith("vid-") else ""

    return (
        f'<article class="article-card{extra_cls}" data-cat="{esc(slug)}" data-title="{title}" '
        f'data-source="{source}" data-url="{url}" data-date="{date}" data-color="{esc(color)}">'
        f'<a href="{esc(_card_href)}"{_card_target}{_card_rel} class="card-link">'
        f'{bg_html}'
        f'<div class="card-overlay"></div>'
        f'{_play_btn}'
        f'<div class="card-body">'
        f'<div class="card-meta">'
        f'<span class="card-source" style="background:{esc(gradient)}">{source}{spectrum_badge}</span>'
        f'<time class="card-date" datetime="{esc(_dt_attr)}">{date}</time>'
        f'</div>'
        f'{cluster_badge}'
        f'{ai_html}'
        f'<h3 class="card-title">{title}</h3>'
        f'</div></a>'
        f'{share_html}'
        f'</article>'
    )


def _gather_carousel(
    articles_by_cat: dict,
    slugs_order: list[tuple],
    per_slug: int = 4,
    max_total: int = 16,
    yt_only_slugs: set | None = None,
) -> list[dict]:
    """Build a flat list of carousel-ready article dicts.

    slugs_order: list of (slug, cat_name, cat_icon) tuples in display order.
    Returns up to max_total items with valid images, taking up to per_slug per slug.

    yt_only_slugs: when provided, articles from these slugs are filtered to
    YouTube watch URLs only — prevents article links bleeding into vid-* carousels.
    """
    result: list[dict] = []
    for slug, cat_name, cat_icon in slugs_order:
        cat_data = articles_by_cat.get(slug)
        if not cat_data:
            continue
        count = 0
        for art in cat_data["articles"]:
            # Skip non-YouTube URLs in video-only sections
            if yt_only_slugs and slug in yt_only_slugs and not _is_yt_url(art.get("url", "")):
                continue
            img = art.get("image", "")
            if img and img.startswith("http") and not img.startswith("data:"):
                result.append({**art, "slug": slug,
                                "cat_name": cat_name,
                                "cat_icon": cat_icon})
                count += 1
            if count >= per_slug or len(result) >= max_total:
                break
        if len(result) >= max_total:
            break
    return result[:max_total]


def _carousel(articles: list[dict], max_items: int = 12, s: dict = STRINGS["ar"],
              site_url: str = "", media_slugs: set | None = None) -> str:
    """Hero + sidebar carousel (Hespress/MSN style).

    Main panel: one large slide at a time, auto-advances every 5.5 s,
    crossfade transition, Ken-Burns zoom, progress bar, dot indicators,
    prev/next arrows, touch swipe.
    Sidebar: first 4 articles after the hero as static article links.
    """
    import hashlib as _hl_c
    items = [a for a in articles if a.get("image", "").startswith("http")][:max_items]
    if len(items) < 3:
        return ""

    def _art_href(raw_url: str, slug: str = "") -> tuple[str, str]:
        """Return (href, target) — YouTube/video: direct link; others: internal page."""
        if (media_slugs and slug in media_slugs) or _is_yt_url(raw_url):
            return raw_url, "_blank"
        _hash = _hl_c.md5(raw_url.encode("utf-8")).hexdigest()[:12]
        return f"article/{_hash}.html", ""

    # ── slides (all items cycle in the hero) ─────────────────────────────────
    slides_html = ""
    dots_html   = ""
    for i, art in enumerate(items):
        gradient = CATEGORY_GRADIENTS.get(art["slug"], DEFAULT_GRADIENT)
        title    = esc(" ".join(art["title"].split()))
        raw_url  = art["url"]
        href, target = _art_href(raw_url, art.get("slug", ""))
        image    = safe_url(art["image"])
        source   = esc(SOURCE_AR_NAME.get(art["source"], art["source"]))
        date     = esc(art.get("date", ""))
        cat_name = esc(art["cat_name"])
        cat_icon = esc(art["cat_icon"])
        active   = " active" if i == 0 else ""
        loading  = "eager" if i == 0 else "lazy"
        priority = ' fetchpriority="high"' if i == 0 else ""
        slides_html += (
            f'<div class="nh-slide{active}" data-idx="{i}">'
            f'<a href="{esc(href)}"{(" target=\"" + target + "\"") if target else ""}>'
            f'<img src="{image}" alt="{title}" class="nh-img" loading="{loading}"{priority} '
            f'onerror="this.parentElement.style.background=\'#1e293b\';this.style.display=\'none\'">'
            f'<div class="nh-overlay"></div>'
            f'<div class="nh-text">'
            f'<span class="nh-badge" style="background:{esc(gradient)}">{cat_icon} {cat_name}</span>'
            f'<h3 class="nh-title">{title}</h3>'
            f'<div class="nh-meta"><span>{source}</span><span>{date}</span></div>'
            f'</div>'
            f'</a></div>'
        )
        dot_active = " active" if i == 0 else ""
        dots_html += (
            f'<button class="nh-dot{dot_active}" data-idx="{i}" '
            f'aria-label="{esc(s["slide"])} {i + 1}"></button>'
        )

    # ── sidebar (items[1..4] — static article links) ──────────────────────────
    side_html = ""
    for art in items[1:5]:
        gradient = CATEGORY_GRADIENTS.get(art["slug"], DEFAULT_GRADIENT)
        title    = esc(" ".join(art["title"].split()))
        raw_url  = art["url"]
        href, target = _art_href(raw_url, art.get("slug", ""))
        image    = safe_url(art["image"])
        source   = esc(SOURCE_AR_NAME.get(art["source"], art["source"]))
        date     = esc(art.get("date", ""))
        cat_name = esc(art["cat_name"])
        cat_icon = esc(art["cat_icon"])
        side_html += (
            f'<a href="{esc(href)}"{(" target=\"" + target + "\"") if target else ""} class="nh-side-item">'
            f'<img src="{image}" alt="{title}" class="nh-side-img" loading="lazy" '
            f'onerror="this.style.display=\'none\'">'
            f'<div class="nh-side-body">'
            f'<span class="nh-side-badge" style="background:{esc(gradient)}">{cat_icon} {cat_name}</span>'
            f'<div class="nh-side-title">{title}</div>'
            f'<div class="nh-side-meta">{source} · {date}</div>'
            f'</div>'
            f'</a>'
        )

    return (
        f'<div class="news-hero" aria-label="{esc(s["highlights"])}">'
        f'<div class="nh-header"><div class="nh-label">⭐ {esc(s["highlights"])}</div></div>'
        f'<div class="nh-body">'
        f'<div class="nh-main">'
        f'<div class="nh-bar"><div class="nh-bar-fill"></div></div>'
        f'<div class="nh-slides">{slides_html}</div>'
        f'<button class="nh-nav nh-prev" aria-label="{esc(s["prev"])}">&#8249;</button>'
        f'<button class="nh-nav nh-next" aria-label="{esc(s["next"])}">&#8250;</button>'
        f'<div class="nh-dots">{dots_html}</div>'
        f'</div>'
        f'<div class="nh-side">{side_html}</div>'
        f'</div>'
        f'</div>'
    )


def _world_subnav(active_slug: str = "", world_regions: list = WORLD_REGIONS,
                  s: dict = STRINGS["ar"], homepage: bool = False) -> str:
    """Horizontal world-regions strip — sticky inside .sticky-header on index + world + region pages.

    homepage=True adds the 'world-subnav--home' class which is hidden on mobile
    (homepage already has a full main nav; region pages need it for navigation).
    """
    if not world_regions:
        return ""
    extra_cls = " world-subnav--home" if homepage else ""
    buttons = ""
    for r in world_regions:
        active_cls = " active-region" if r["slug"] == active_slug else ""
        buttons += (
            f'<a href="{esc(r["slug"])}.html" class="world-region-btn{active_cls}">'
            f'{esc(r["icon"])} {esc(r["name"])}'
            f'</a>'
        )
    return (
        f'<div class="world-subnav{extra_cls}" aria-label="{esc(s["world_regions_label"])}">'
        f'<div class="world-subnav-inner">{buttons}</div>'
        f'</div>'
    )


def _media_subnav(active_slug: str = "", media_regions: list = MEDIA_REGIONS,
                  s: dict = STRINGS["ar"]) -> str:
    """Horizontal media-regions strip for صوت وصورة and vid-* pages."""
    if not media_regions:
        return ""
    buttons = ""
    _live_label = s.get("live_tv_label", "📡 Live TV")
    _live_active_cls = " active-region" if active_slug == "live" else ""
    for i, r in enumerate(media_regions):
        active_cls = " active-region" if r["slug"] == active_slug else ""
        buttons += (
            f'<a href="{esc(r["slug"])}.html" class="world-region-btn{active_cls}">'
            f'{esc(r["icon"])} {esc(r["name"])}'
            f'</a>'
        )
        # Insert live TV button right after the first item (أحداث / Events)
        if i == 0:
            buttons += (
                f'<a href="live.html" class="world-region-btn live-btn{_live_active_cls}">'
                f'{esc(_live_label)}'
                f'</a>'
            )
    return (
        f'<div class="world-subnav" aria-label="{esc(s.get("media_regions_label", "صوت وصورة"))}">'
        f'<div class="world-subnav-inner">{buttons}</div>'
        f'</div>'
    )


def _live_page_html(lang: str, s: dict, channels: list[dict],
                    media_regions: list = MEDIA_REGIONS) -> str:
    """Generate the live TV channels page body."""
    title      = s.get("live_tv_title", "Live TV")
    desc       = s.get("live_tv_desc",  "Watch global news channels live")
    watch_lbl  = s.get("live_tv_watch", "▶ Watch Live")
    on_air_lbl = s.get("live_tv_on_air", "On Air")

    cards_html = ""
    for ch in channels:
        cards_html += (
            f'<div class="live-card">'
            f'<div class="live-card-flag">{esc(ch["flag"])}</div>'
            f'<div class="live-card-name">{esc(ch["name"])}</div>'
            f'<div class="live-badge"><span class="live-badge-dot"></span>{esc(on_air_lbl)}</div>'
            f'<a href="{esc(ch["url"])}" class="live-watch-btn" target="_blank" '
            f'rel="noopener noreferrer">{esc(watch_lbl)}</a>'
            f'</div>'
        )

    subnav = _media_subnav(active_slug="live", media_regions=media_regions, s=s)
    return (
        f'{subnav}'
        f'<div class="main-wrapper">'
        f'<div class="live-page-hdr">'
        f'<div class="live-page-hdr-icon">📡</div>'
        f'<div><h1>{esc(title)}</h1><p>{esc(desc)}</p></div>'
        f'</div>'
        f'<div class="live-grid">{cards_html}</div>'
        f'</div>'
    )


def _item_list_json_ld(
    cat_name: str, cat_url: str, articles: list, site_url: str
) -> str:
    """Return an ItemList JSON-LD <script> block for a category page.

    Helps Google understand the page is a list of news articles and index them.
    """
    import hashlib as _hl_il
    items = []
    for i, art in enumerate(articles[:20], 1):   # Google recommends max 20
        _h   = _hl_il.md5(art["url"].encode("utf-8")).hexdigest()[:12]
        _url = f"{site_url.rstrip('/')}/article/{_h}.html"
        items.append({
            "@type":    "ListItem",
            "position": i,
            "url":      _url,
            "name":     art["title"][:110],
        })
    ld = {
        "@context":        "https://schema.org",
        "@type":           "ItemList",
        "name":            cat_name,
        "url":             cat_url,
        "numberOfItems":   len(items),
        "itemListElement": items,
    }
    return (
        f'  <script type="application/ld+json">'
        f'{json.dumps(ld, ensure_ascii=False)}'
        f'</script>'
    )


def _nav(categories: list, articles_by_cat: dict, active: str = "home",
         s: dict = STRINGS["ar"], region_slugs: set = REGION_SLUGS,
         has_world: bool = True, media_slugs: set = MEDIA_SLUGS,
         has_media: bool = True) -> str:
    home_cls = "nav-tab active" if active == "home" else "nav-tab"
    html = f'<a href="index.html" class="{home_cls}" data-cat="all">{s["home"]}</a>\n'

    for cat in categories:
        slug = cat["slug"]
        if slug in region_slugs or slug in media_slugs or slug in ECON_SUB_SLUGS:
            continue  # regions/media/econ-sub live in subnav, not main nav
        cls = "nav-tab active" if active == slug else "nav-tab"
        html += (
            f'<a href="{esc(slug)}.html" class="{cls}" data-cat="{esc(slug)}">'
            f'{esc(cat.get("icon",""))} {esc(cat["name"])}</a>\n'
        )

    # Show media tab when either world_regions or media_regions are configured
    if has_world or has_media:
        media_active = active in media_slugs or active in ("media", "live")
        world_cls = "nav-tab active" if media_active else "nav-tab"
        html += f'<a href="media.html" class="{world_cls}" data-cat="media">{s["world"]}</a>\n'
    return html


def _sidebar(categories: list, articles_by_cat: dict,
             total_articles: int, total_sources: int, total_cats: int,
             s: dict = STRINGS["ar"]) -> str:
    cat_links = ""
    for cat in categories:
        slug = cat["slug"]
        if slug not in articles_by_cat:
            continue
        count = len(articles_by_cat[slug]["articles"])
        color = CATEGORY_COLORS.get(slug, DEFAULT_COLOR)
        cat_links += (
            f'<li><a href="{esc(slug)}.html" class="cat-link" style="border-inline-start-color:{esc(color)}">'
            f'{esc(cat.get("icon",""))} {esc(cat["name"])}'
            f'<span class="cat-count">{count}</span></a></li>'
        )
    return f"""
<div class="sidebar-widget">
  <h3 class="widget-title">{s["stats"]}</h3>
  <div class="stats-grid">
    <div class="stat-box"><div class="stat-value">{total_articles}</div><div class="stat-label">{s["articles_unit"]}</div></div>
    <div class="stat-box"><div class="stat-value">{total_sources}</div><div class="stat-label">{s["sources_unit"]}</div></div>
    <div class="stat-box"><div class="stat-value">{total_cats}</div><div class="stat-label">{s["cats_unit"]}</div></div>
  </div>
</div>
<div class="sidebar-widget">
  <h3 class="widget-title">{s["sections_widget"]}</h3>
  <ul class="cat-list">{cat_links}</ul>
</div>
<div class="sidebar-widget">
  <h3 class="widget-title">{s["links_widget"]}</h3>
  <ul class="cat-list">
    <li><a href="about.html"     class="cat-link" style="border-inline-start-color:#64748b">{s["about"]}</a></li>
    <li><a href="contact.html"   class="cat-link" style="border-inline-start-color:#64748b">{s["contact"]}</a></li>
    <li><a href="advertise.html" class="cat-link" style="border-inline-start-color:#f59e0b">{s["advertise"]}</a></li>
    <li><a href="privacy.html"   class="cat-link" style="border-inline-start-color:#64748b">{s["privacy"]}</a></li>
    <li><a href="terms.html"     class="cat-link" style="border-inline-start-color:#64748b">{s["terms"]}</a></li>
  </ul>
</div>
<div class="sidebar-widget">
  <h3 class="widget-title">{s["ad"]}</h3>
  <div class="ad-slot ad-slot-sidebar"><!-- Google AdSense --></div>
</div>"""


# ──────────────────────────────────────────────────────────────────────────────
# SEO HELPERS
# ──────────────────────────────────────────────────────────────────────────────

# Language subpath mapping.  EN lives at the site root; all others have a
# subpath prefix.  Matches the output directories in run.py.
_LANG_PATHS: dict[str, str] = {
    "en": "",
    "ar": "/ar",
    "fr": "/fr",
    "es": "/es",
    "tr": "/tr",
}

# BCP-47 hreflang values for each language
_LANG_HREFLANG: dict[str, str] = {
    "en": "en",
    "ar": "ar",
    "fr": "fr",
    "es": "es",
    "tr": "tr",
}


def _hreflang_links(base_url: str, filename: str) -> str:
    """Return <link rel="alternate" hreflang="…"> tags for all 5 languages.

    base_url — the site root without trailing slash, e.g.
               "https://atlasnews.solvixi.com"
    filename — e.g. "index.html", "politics.html"
    Returns an empty string when base_url is not configured.
    """
    if not base_url:
        return ""
    base = base_url.rstrip("/")
    tags = []
    for lang_code, path in _LANG_PATHS.items():
        href = f"{base}{path}/{filename}"
        hl   = _LANG_HREFLANG[lang_code]
        tags.append(f'  <link rel="alternate" hreflang="{hl}" href="{esc(href)}">')
    # x-default points to the EN (root) version
    xdef = f"{base}/{filename}"
    tags.append(f'  <link rel="alternate" hreflang="x-default" href="{esc(xdef)}">')
    return "\n".join(tags)


def _org_json_ld(site_title: str, site_url: str) -> str:
    """Return an Organization JSON-LD <script> block."""
    if not site_url:
        return ""
    obj = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": site_title,
        "url": site_url.rstrip("/") + "/",
        "logo": site_url.rstrip("/") + "/icon-512.png",
        "contactPoint": {
            "@type": "ContactPoint",
            "email": "contact@solvixi.com",
            "contactType": "customer service",
        },
        "sameAs": [],
    }
    return f'  <script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>'


def _breadcrumb_json_ld(site_title: str, cat_name: str,
                        site_url: str, page_file: str) -> str:
    """Return a BreadcrumbList JSON-LD <script> block for category pages."""
    if not site_url:
        return ""
    base = site_url.rstrip("/")
    obj = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem", "position": 1,
                "name": site_title,
                "item": base + "/",
            },
            {
                "@type": "ListItem", "position": 2,
                "name": cat_name,
                "item": f"{base}/{page_file}",
            },
        ],
    }
    return f'  <script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>'


def _ga4_head(ga_id: str) -> str:
    """Return GA4 <head> snippet with GDPR consent mode.

    - Starts with analytics_storage=denied (no data until user accepts).
    - If the user already accepted (localStorage), grants immediately.
    - When ga_id is empty, returns empty string (no tracking).
    """
    if not ga_id:
        return ""
    _id = esc(ga_id)
    return f"""\
  <!-- Google Analytics 4 — consent mode enabled -->
  <script async src="https://www.googletagmanager.com/gtag/js?id={_id}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('consent', 'default', {{'analytics_storage': 'denied', 'ad_storage': 'denied'}});
    gtag('js', new Date());
    gtag('config', '{_id}', {{'anonymize_ip': true, 'send_page_view': false}});
    if (localStorage.getItem('atlas_cookie_consent') === 'accepted') {{
      gtag('consent', 'update', {{'analytics_storage': 'granted'}});
      gtag('event', 'page_view');
    }}
  </script>"""


# ──────────────────────────────────────────────────────────────────────────────
# FAVICON SVG (inline, generated as static asset)
# ──────────────────────────────────────────────────────────────────────────────

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#1d4ed8"/>
  <text x="16" y="23" text-anchor="middle" font-family="Arial,sans-serif"
        font-size="20" font-weight="bold" fill="#ffffff">N</text>
</svg>
"""

# Default OG image path (relative).  Override per-page by passing og_image.
_DEFAULT_OG_IMAGE_PATH = "og-image.png"


def _gen_og_png(width: int = 1200, height: int = 630) -> bytes:
    """Generate a 1200×630 PNG OG image with no external dependencies.

    Creates a gradient from dark navy (#0f172a) at top to brand blue (#1d4ed8)
    at bottom — matches the site's header palette.

    Written once to static/og-image.png; the user can replace it with a
    Canva-designed PNG at any time without it being overwritten again.
    """
    import struct
    import zlib as _zl

    def _chunk(tag: bytes, data: bytes) -> bytes:
        crc = _zl.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    # Gradient: dark navy → brand blue
    r0, g0, b0 = 0x0f, 0x17, 0x2a   # top  — #0f172a
    r1, g1, b1 = 0x1d, 0x4e, 0xd8   # bottom — #1d4ed8

    rows = bytearray()
    for y in range(height):
        t = y / max(height - 1, 1)
        r = round(r0 + (r1 - r0) * t)
        g = round(g0 + (g1 - g0) * t)
        b = round(b0 + (b1 - b0) * t)
        # PNG filter byte 0 (None) + raw RGB pixels for this row
        rows += b'\x00' + bytes([r, g, b] * width)

    return (
        b'\x89PNG\r\n\x1a\n'
        + _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + _chunk(b'IDAT', _zl.compress(bytes(rows), 9))
        + _chunk(b'IEND', b'')
    )


# Default OG image (SVG — kept for reference; actual OG meta uses og-image.png)
OG_IMAGE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#1d4ed8"/>
  <text x="600" y="280" text-anchor="middle" font-family="Arial,sans-serif"
        font-size="80" font-weight="bold" fill="#ffffff">Atlas News</text>
  <text x="600" y="380" text-anchor="middle" font-family="Arial,sans-serif"
        font-size="36" fill="#93c5fd">Your World in 5 Languages</text>
</svg>
"""


def _article_page_html(
    art: dict,
    slug: str,
    related: list,
    s: dict,
    site_title: str,
    site_url: str,
    cat_meta: dict,
    lang: str,
    cluster_map: dict | None = None,
    ga_id: str = "",
) -> str:
    """Generate a standalone HTML page for a single article (for SEO / Google News)."""
    import urllib.parse as _up
    import hashlib

    title_raw  = " ".join(art["title"].split())
    title_esc  = esc(title_raw)
    ext_url    = art["url"]
    source_raw = art["source"]
    source_esc = esc(SOURCE_AR_NAME.get(source_raw, source_raw))
    # Spectrum badge for article page
    _sp_t = _SPECTRUM_MAP.get(source_raw, "")
    if _sp_t and s:
        _sp_lbl = s.get(f"spectrum_{_sp_t}", _sp_t)
        _sp_css = _SPECTRUM_CSS.get(_sp_t, "sp-wire")
        _art_sp_badge = f'<span class="spectrum-badge {_sp_css}">{esc(_sp_lbl)}</span>'
    else:
        _art_sp_badge = ""
    date_str   = art.get("date", "")
    scraped_at = art.get("scraped_at", date_str + "T00:00:00")
    # scraped_dt — RFC 3339 of when WE scraped the article (used for dateModified)
    scraped_dt = scraped_at.replace(" ", "T")
    if len(scraped_dt) == 19:
        scraped_dt += "+00:00"
    # pub_dt — actual RSS publication date (used for datePublished)
    # date_str is "YYYY-MM-DD" from the RSS <pubDate>; use T00:00:00 as the
    # time component when no finer granularity is available.
    pub_dt = f"{date_str}T00:00:00+00:00" if date_str else scraped_dt
    ai_summary = art.get("ai_summary", "")
    image_url  = art.get("image", "")
    color      = CATEGORY_COLORS.get(slug, DEFAULT_COLOR)
    gradient   = CATEGORY_GRADIENTS.get(slug, DEFAULT_GRADIENT)

    cat_name, cat_icon = cat_meta.get(slug, (slug, "📰"))

    # Cluster badge for article page
    _art_cluster_badge = ""
    if cluster_map:
        _acl = cluster_map.get(art.get("url", ""))
        if _acl and _acl.get("source_count", 0) >= 2:
            _n = _acl["source_count"]
            _tpl = s.get("cluster_sources", "📡 {n}")
            _cl_lbl = _tpl.format(n=_n)
            _cl_srcs = ", ".join(_acl.get("sources", [])[:8])
            _art_cluster_badge = (
                f'<div class="art-cluster-bar">'
                f'<span class="cluster-badge" title="{esc(_cl_srcs)}">{esc(_cl_lbl)}</span>'
                f'<span class="art-cluster-srcs">{esc(_cl_srcs)}</span>'
                f'</div>'
            )

    # Canonical URL for this article page
    art_hash  = hashlib.md5(ext_url.encode("utf-8")).hexdigest()[:12]
    canon_url = f"{site_url.rstrip('/')}/article/{art_hash}.html" if site_url else ""

    # ── News keywords (title words > 3 chars) — used in JSON-LD + meta ───────
    import re as _re
    kws = [w for w in _re.split(r'\W+', title_raw) if len(w) > 3][:10]

    # ── JSON-LD: NewsArticle ─────────────────────────────────────────────────
    _root_for_ld = site_url.rstrip("/").rsplit("/article", 1)[0].rsplit("/ar", 1)[0].rsplit("/fr", 1)[0].rsplit("/es", 1)[0].rsplit("/tr", 1)[0]
    _publisher = {
        "@type": "Organization",
        "name":  site_title,
        "logo":  {
            "@type":  "ImageObject",
            "url":    f"{_root_for_ld}/icon-512.png",
            "width":  512,
            "height": 512,
        } if site_url else {},
    }
    _author_name = SOURCE_AR_NAME.get(source_raw, source_raw)
    _ld = {
        "@context":         "https://schema.org",
        "@type":            "NewsArticle",
        "headline":         title_raw[:110],
        "datePublished":    pub_dt,      # actual RSS publish date
        "dateModified":     scraped_dt,  # when we last scraped/processed it
        "author":           {"@type": "Organization", "name": _author_name, "url": art.get("url", "")},
        "publisher":        _publisher,
        "description":      ai_summary[:300] if ai_summary else title_raw[:200],
        "isAccessibleForFree": True,
        "inLanguage":       s["in_language"],
        "url":              canon_url,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canon_url},
        "articleSection":   cat_name,
        "keywords":         ", ".join(kws) if kws else title_raw[:100],
    }
    if image_url:
        _ld["image"] = {"@type": "ImageObject", "url": image_url}
    json_ld = json.dumps(_ld, ensure_ascii=False)

    # ── Meta description ─────────────────────────────────────────────────────
    meta_desc = ai_summary[:200] if ai_summary else title_raw[:200]

    # ── Image HTML ───────────────────────────────────────────────────────────
    img_html = (
        f'<img class="art-img" src="{safe_url(image_url)}" '
        f'alt="{title_esc}" loading="eager">'
    ) if image_url else ""

    # ── AI summary block (fallback context card for thin-content prevention) ────
    summary_html = ""
    if ai_summary:
        summary_html = (
            f'<div class="art-summary-box">'
            f'<div class="art-summary-lbl">{esc(s.get("art_summary_lbl", "AI Summary"))}</div>'
            f'<p class="art-summary-text">{esc(ai_summary)}</p>'
            f'<p class="art-disclaimer">{esc(s.get("art_disclaimer", ""))}</p>'
            f'</div>'
        )
    else:
        # No AI summary — show a context card so page isn't pure thin content.
        # Helps Google understand the page topic and avoid "doorway page" signals.
        _from_lbl = s.get("art_from_source", "Article from")
        summary_html = (
            f'<div class="art-context-card">'
            f'{esc(_from_lbl)} <strong>{source_esc}</strong> · '
            f'{esc(cat_icon)} <strong>{esc(cat_name)}</strong> · {esc(date_str)}'
            f'<br><em>{title_esc}</em>'
            f'</div>'
        )

    # ── Share buttons — use our canonical page URL, fall back to ext_url ────────
    _share_page = canon_url if canon_url else ext_url
    _wa  = "https://wa.me/?text=" + _up.quote(title_raw + "\n\n" + _share_page, safe="")
    _x   = ("https://x.com/intent/tweet?text=" + _up.quote(title_raw, safe="")
            + "&url=" + _up.quote(_share_page, safe=""))
    _tg  = ("https://t.me/share/url?url=" + _up.quote(_share_page, safe="")
            + "&text=" + _up.quote(title_raw, safe=""))
    _fb  = "https://www.facebook.com/sharer/sharer.php?u=" + _up.quote(_share_page, safe="")
    share_row = (
        f'<div class="art-share-row">'
        f'<a href="{esc(_wa)}" class="share-btn share-wa" target="_blank" rel="noopener noreferrer" title="WhatsApp">W</a>'
        f'<a href="{esc(_fb)}" class="share-btn share-fb" target="_blank" rel="noopener noreferrer" title="Facebook">f</a>'
        f'<a href="{esc(_x)}" class="share-btn share-x" target="_blank" rel="noopener noreferrer" title="X">𝕏</a>'
        f'<a href="{esc(_tg)}" class="share-btn share-tg" target="_blank" rel="noopener noreferrer" title="Telegram">✈</a>'
        f'<button class="share-btn share-copy" data-copy="{esc(_share_page)}" title="Copy link">⧉</button>'
        f'</div>'
    )

    # ── Related articles ──────────────────────────────────────────────────────
    related_html = ""
    if related:
        rel_cards = ""
        for r in related[:4]:
            r_hash  = hashlib.md5(r["url"].encode("utf-8")).hexdigest()[:12]
            r_title = esc(" ".join(r["title"].split()))
            r_src   = esc(SOURCE_AR_NAME.get(r["source"], r["source"]))
            rel_cards += (
                f'<a href="{r_hash}.html" class="art-rel-card">'
                f'<div class="art-rel-title">{r_title}</div>'
                f'<div class="art-rel-meta">{r_src} · {esc(r.get("date", ""))}</div>'
                f'</a>'
            )
        related_html = (
            f'<div class="art-related">'
            f'<h3 class="art-related-title">{esc(s.get("art_related", "Related"))}</h3>'
            f'<div class="art-related-grid">{rel_cards}</div>'
            f'</div>'
        )

    # ── Breadcrumb ────────────────────────────────────────────────────────────
    breadcrumb = (
        f'<div class="art-breadcrumb">'
        f'<a href="../index.html">{esc(s.get("home_bare", "Home"))}</a>'
        f'<span>›</span>'
        f'<a href="../{esc(slug)}.html">{esc(cat_icon)} {esc(cat_name)}</a>'
        f'<span>›</span>'
        f'<span>{title_esc[:60]}{"…" if len(title_raw) > 60 else ""}</span>'
        f'</div>'
    )

    # ── OG image ─────────────────────────────────────────────────────────────
    og_img_tags = ""
    if image_url:
        og_img_tags = (
            f'  <meta property="og:image" content="{esc(image_url)}">\n'
            f'  <meta property="og:image:width" content="1200">\n'
            f'  <meta name="twitter:image" content="{esc(image_url)}">'
        )

    # ── news_keywords meta tag (kws computed before JSON-LD block above) ──────
    kw_meta = (
        f'  <meta name="news_keywords" content="{esc(", ".join(kws))}">'
    ) if kws else ""

    # ── hreflang: self-referential + x-default pointing to site root ──────────
    # Article pages are language-specific (no direct translation counterpart).
    # We add a self tag (tells Google this page's language) + x-default (homepage).
    _art_hl = ""
    if site_url and canon_url:
        _hl_code = _LANG_HREFLANG.get(lang, lang)
        # Compute root URL by stripping language prefix
        _hl_prefix = _LANG_PATHS.get(lang, "")
        _hl_base   = site_url.rstrip("/")
        if _hl_prefix and _hl_base.endswith(_hl_prefix):
            _hl_root = _hl_base[: -len(_hl_prefix)].rstrip("/")
        else:
            _hl_root = _hl_base
        _art_hl = (
            f'  <link rel="alternate" hreflang="{_hl_code}" href="{esc(canon_url)}">\n'
            f'  <link rel="alternate" hreflang="x-default" href="{esc(_hl_root)}/">'
        )

    # ── Full HTML ─────────────────────────────────────────────────────────────
    _dir  = s.get("dir", "ltr")
    _lang = s.get("lang", lang)
    _bc   = s.get("body_class", "lang-ltr")
    _font_url = s.get("font_url", "")
    return f"""<!DOCTYPE html>
<html lang="{_lang}" dir="{_dir}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
  <title>{title_esc} — {esc(site_title)}</title>
  <meta name="description" content="{esc(meta_desc)}">
{kw_meta}
  <!-- Open Graph -->
  <meta property="og:title" content="{title_esc}">
  <meta property="og:description" content="{esc(meta_desc)}">
  <meta property="og:type" content="article">
  <meta property="og:locale" content="{esc(s.get('og_locale', 'ar_MA'))}">
  <meta property="og:url" content="{esc(canon_url)}">
  <meta property="article:published_time" content="{esc(pub_dt)}">
  <meta property="article:modified_time" content="{esc(scraped_dt)}">
  <meta property="article:section" content="{esc(cat_name)}">
{("  " + chr(10).join(f'<meta property="article:tag" content="{esc(k)}">' for k in kws[:5]) + chr(10)) if kws else ""}{og_img_tags}
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title_esc}">
  <meta name="twitter:description" content="{esc(meta_desc)}">
  <!-- Canonical & hreflang -->
  <link rel="canonical" href="{esc(canon_url)}">
{_art_hl}
  <!-- Favicons -->
  <link rel="icon" type="image/svg+xml" href="../favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="../favicon-32.png">
  <link rel="apple-touch-icon" sizes="180x180" href="../icon-192.png">
  <link rel="manifest" href="../manifest.json">
  <meta name="theme-color" content="{esc(s.get('theme_color', '#1d4ed8'))}">
  <!-- Apple PWA / iOS Home Screen -->
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="{esc(site_title)}">
  <!-- LCP: preload hero image for faster rendering -->
{(f'  <link rel="preload" href="{esc(image_url)}" as="image" fetchpriority="high">' if image_url else "")}
  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="{esc(_font_url)}" rel="stylesheet">
  <link rel="stylesheet" href="../style.css">
  <!-- JSON-LD -->
  <script type="application/ld+json">{json_ld}</script>
{_ga4_head(ga_id)}
</head>
<body id="top" class="{_bc}">
  <div class="sticky-header">
    <header class="site-header" aria-label="{esc(s.get('header_label', 'Header'))}">
      <div class="site-header-inner">
        <div class="header-start">
          <a href="../index.html#{esc(slug)}" class="art-back" id="art-back-link">{esc(s.get('art_back', '← Back'))} {esc(site_title)}</a>
        </div>
        <div class="header-end">
          <button id="theme-toggle" class="theme-btn" aria-label="{esc(s.get('theme_btn_label', 'Toggle theme'))}">🌙</button>
        </div>
      </div>
      {breadcrumb}
    </header>
  </div>
  <div class="main-wrapper">
    <main class="art-page" role="main">
      <article itemscope itemtype="https://schema.org/NewsArticle">
        {img_html}
        <h1 class="art-title" itemprop="headline">{title_esc}</h1>
        <div class="art-meta">
          <span class="art-source-badge" itemprop="author">{source_esc}{_art_sp_badge}</span>
          <time class="art-date" datetime="{esc(pub_dt)}" itemprop="datePublished">{esc(date_str)}</time>
          <span class="art-cat-badge" style="background:{esc(gradient)}">{esc(cat_icon)} {esc(cat_name)}</span>
        </div>
        {_art_cluster_badge}
        {summary_html}
        <a href="{safe_url(ext_url)}" target="_blank" rel="noopener noreferrer nofollow"
           class="art-read-btn" itemprop="url">
          {esc(s.get("art_read_orig", "📖 Read full article"))}
        </a>
        {share_row}
        {related_html}
        <a href="../{esc(slug)}.html" class="art-browse-cta">
          {esc(s.get("art_browse_cat","More from"))} {esc(cat_icon)} {esc(cat_name)} {s.get("arrow","→")}
        </a>
      </article>
    </main>
  </div>
  <button class="back-to-top" id="back-to-top" aria-label="{esc(s.get('back_to_top', 'Back to top'))}">↑</button>
  <script src="../app.js"></script>
</body>
</html>"""


def _page(*, title: str, desc: str, nav_html: str,
          main_html: str, footer_cats: str,
          today_ar: str, now: str, total_articles: int, total_sources: int,
          world_subnav_html: str = "", ticker_html: str = "",
          lang_switcher_html: str = "",
          canonical: str = "", carousel_html: str = "",
          rss_url: str = "rss.xml",
          hreflang_html: str = "",
          og_image_url: str = "",
          extra_json_ld: str = "",
          ga_id: str = "",
          lcp_image_url: str = "",
          s: dict) -> str:
    # ── JSON-LD: WebSite ──────────────────────────────────────────────────────
    sd = json.dumps({
        "@context": "https://schema.org", "@type": "WebSite",
        "name": title, "description": desc, "inLanguage": s["in_language"],
        "url": canonical or "",
    }, ensure_ascii=False)
    og_img_tags = (
        f'  <meta property="og:image" content="{esc(og_image_url)}">\n'
        f'  <meta property="og:image:width" content="1200">\n'
        f'  <meta property="og:image:height" content="630">\n'
        f'  <meta name="twitter:image" content="{esc(og_image_url)}">'
    ) if og_image_url else ""
    return f"""<!DOCTYPE html>
<html lang="{s["lang"]}" dir="{s["dir"]}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
  <meta name="google-site-verification" content="S3p0K9iOQqP3aAeKp_xq8anLJEunF-LDN4cPldiVaUY">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}">
  <!-- Open Graph -->
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(desc)}">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="{s["og_locale"]}">
  <meta property="og:url" content="{esc(canonical)}">
{og_img_tags}
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{esc(title)}">
  <meta name="twitter:description" content="{esc(desc)}">
  <!-- Canonical & hreflang -->
  <link rel="canonical" href="{esc(canonical)}">
{hreflang_html}
  <!-- Favicons -->
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">
  <link rel="apple-touch-icon" sizes="180x180" href="icon-192.png">
  <!-- PWA -->
  <link rel="manifest" href="manifest.json">
  <meta name="theme-color" content="{esc(s.get("theme_color","#1d4ed8"))}">
  <!-- Apple PWA / iOS Home Screen -->
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="{esc(title)}">
  <!-- RSS -->
  <link rel="alternate" type="application/rss+xml" title="{esc(title)}" href="{esc(rss_url)}">
  <!-- Critical CSS — initial skeleton shown instantly before style.css loads.
       MUST come BEFORE <link rel="stylesheet"> so that style.css overrides it
       once loaded. Reversing this order would permanently override style.css. -->
  <style>*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}:root{{--header-start:#4f46e5;--header-end:#7c3aed;--nav-bg:rgba(255,255,255,.92);--nav-text:#475569;--accent:#6366f1;--bg:#f8f9fe;--text:#1e293b;--border:#e2e8f0}}body{{font-family:system-ui,sans-serif;background:#f8f9fe;color:#1e293b;direction:{s["dir"]}}}.sticky-header{{position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.12)}}.site-header{{background:linear-gradient(135deg,var(--header-start),var(--header-end));color:#fff;padding:8px 0}}.site-header-inner{{display:flex;align-items:center;justify-content:space-between;padding:0 20px;max-width:1200px;margin:0 auto}}.site-header-title{{font-weight:800;font-size:1.2em;letter-spacing:2px;color:#fff}}.site-nav{{background:var(--nav-bg);backdrop-filter:blur(8px);overflow:hidden}}.nav-inner{{display:flex;flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;gap:1px;max-width:1200px;margin:0 auto;padding:0 6px}}.nav-tab{{display:inline-flex;align-items:center;padding:8px 14px;color:var(--nav-text);font-size:.82em;text-decoration:none;white-space:nowrap;flex-shrink:0;min-width:0}}.articles-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}}.article-card{{border-radius:14px;overflow:hidden;background:#fff;position:relative;aspect-ratio:4/3}}@media(max-width:900px){{.articles-grid{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:480px){{.articles-grid{{grid-template-columns:1fr}}.article-card{{aspect-ratio:16/9}}}}@media(max-width:768px){{.top-date{{display:none}}.site-header-inner{{padding:0 10px;gap:8px}}}}@media(max-width:480px){{.live-time{{display:none}}}}</style>
  <!-- Performance: preload critical assets first -->
  <link rel="preload" href="style.css" as="style">
{(f'  <link rel="preload" href="{esc(lcp_image_url)}" as="image" fetchpriority="high">' if lcp_image_url else "")}
  <!-- Fonts: async (non-render-blocking) -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="preload" href="{esc(s["font_url"])}" as="style" onload="this.onload=null;this.rel='stylesheet'">
  <noscript><link href="{esc(s["font_url"])}" rel="stylesheet"></noscript>
  <link rel="stylesheet" href="style.css">
  <!-- JSON-LD -->
  <script type="application/ld+json">{sd}</script>
{extra_json_ld}
{_ga4_head(ga_id)}
</head>
<body id="top" class="{s["body_class"]}">
  <div class="sticky-header">
    <header class="site-header" aria-label="{s["header_label"]}">
      <div class="site-header-inner">
        <div class="header-start">
          <span class="top-date">📅 {esc(today_ar)}</span>
          <span class="live-dot" title="{s["live_label"]}"></span>
          <span id="live-time" class="live-time">00:00:00</span>
        </div>
        <span class="site-header-title">{esc(title)}</span>
        <div class="header-end">
          <button id="theme-toggle" class="theme-btn" aria-label="{s["theme_btn_label"]}">🌙</button>
          <button id="search-toggle" class="theme-btn" aria-label="{s.get("search_label","Search")}" aria-expanded="false">🔍</button>
        </div>
      </div>
      <div class="lang-row">{lang_switcher_html}</div>
    </header>
    <div id="search-bar" class="search-bar" role="search">
      <div class="search-bar-inner">
        <input id="search-input" type="search" class="search-input"
               placeholder="{s.get("search_placeholder","...")}"
               aria-label="{s.get("search_label","Search")}" autocomplete="off">
        <button class="search-clear" id="search-clear" aria-label="×">×</button>
      </div>
    </div>
    <nav class="site-nav" aria-label="{s["nav_label"]}">
      <div class="nav-inner">{nav_html}</div>
    </nav>
    {world_subnav_html}
    {ticker_html}
  </div>
  <div class="main-wrapper">
    {carousel_html}
    <main class="content-area" role="main">
      {main_html}
    </main>
  </div>
  <button class="back-to-top" id="back-to-top" aria-label="{s["back_to_top"]}">↑</button>
  <footer class="site-footer">
    <div class="footer-inner">
      <div class="footer-brand">
        <h3>{esc(title)}</h3>
        <p style="margin-top:8px;font-size:.8em">{s["updated"]}: {esc(now)}</p>
      </div>
      <div class="footer-section">
        <h4>{s.get("footer_cats_title","Sections")}</h4>
        <ul>{footer_cats}</ul>
      </div>
      <div class="footer-section">
        <h4>{s["footer_links"]}</h4>
        <ul>
          <li><a href="index.html">{s["home_bare"]}</a></li>
          <li><a href="about.html">{s["about"]}</a></li>
          <li><a href="contact.html">{s["contact"]}</a></li>
          <li><a href="advertise.html">{s["advertise"]}</a></li>
          <li><a href="privacy.html">{s["privacy"]}</a></li>
          <li><a href="terms.html">{s["terms"]}</a></li>
        </ul>
      </div>
      <div class="footer-section footer-rss">
        <h4>{s.get("rss_feeds","RSS")}</h4>
        <ul>
          <li><a href="{esc(rss_url)}" type="application/rss+xml">📡 {s.get("rss_all","All news")}</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-bottom">
      <p><a href="privacy.html">{s["privacy"]}</a> · <a href="terms.html">{s["terms"]}</a> · <a href="about.html">{s["about"]}</a> · <a href="contact.html">{s["contact"]}</a> · <a href="advertise.html">{s["advertise"]}</a> · <a href="{esc(rss_url)}" type="application/rss+xml">RSS</a></p>
    </div>
  </footer>
  <!-- GDPR Cookie Banner -->
  <div id="cookie-banner" class="cookie-banner" role="dialog" aria-live="polite" aria-label="{esc(s.get('gdpr_title','Cookies'))}">
    <div class="cookie-inner">
      <div class="cookie-text">
        <strong>{esc(s.get('gdpr_title','We use cookies'))}</strong>
        <span>{esc(s.get('gdpr_body',''))}</span>
      </div>
      <div class="cookie-actions">
        <a href="privacy.html" class="cookie-policy-link">{esc(s.get('gdpr_policy','Privacy Policy'))}</a>
        <button id="cookie-customize" class="cookie-btn cookie-customize">{esc(s.get('gdpr_customize','Customize'))}</button>
        <button id="cookie-reject" class="cookie-btn cookie-reject">{esc(s.get('gdpr_reject','Essential Only'))}</button>
        <button id="cookie-accept" class="cookie-btn cookie-accept">{esc(s.get('gdpr_accept','Accept All'))}</button>
      </div>
    </div>
  </div>
  <!-- GDPR Customize Modal -->
  <div id="consent-overlay" class="consent-overlay" role="dialog" aria-modal="true">
    <div class="consent-modal">
      <h3>{esc(s.get('gdpr_modal_title','Privacy Preferences'))}</h3>
      <div class="consent-row">
        <div class="consent-row-text">
          <strong>{esc(s.get('gdpr_necessary','Strictly Necessary'))}</strong>
          <span>{esc(s.get('gdpr_necessary_desc','Required for the site to function.'))}</span>
        </div>
        <div style="text-align:center">
          <label class="consent-toggle" aria-label="necessary">
            <input type="checkbox" id="toggle-necessary" checked disabled>
            <span class="consent-slider"></span>
          </label>
          <div class="consent-always">{esc(s.get('gdpr_always_on','Always On'))}</div>
        </div>
      </div>
      <div class="consent-row">
        <div class="consent-row-text">
          <strong>{esc(s.get('gdpr_analytics','Analytics & Performance'))}</strong>
          <span>{esc(s.get('gdpr_analytics_desc','Helps us understand how visitors use the site.'))}</span>
        </div>
        <label class="consent-toggle" aria-label="analytics">
          <input type="checkbox" id="toggle-analytics">
          <span class="consent-slider"></span>
        </label>
      </div>
      <div class="consent-modal-actions">
        <button id="consent-save" class="consent-save">{esc(s.get('gdpr_save','Save Preferences'))}</button>
      </div>
    </div>
  </div>
  <script src="app.js"></script>
</body>
</html>"""


def _write(filename: str, content: str, out_dir: str = OUTPUT_DIR) -> None:
    full_path = os.path.join(out_dir, filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)


# ──────────────────────────────────────────────────────────────────────────────
# RSS FEED GENERATOR
# ──────────────────────────────────────────────────────────────────────────────

def _xml_esc(t: str) -> str:
    """Escape characters invalid in XML text nodes."""
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


def _generate_rss(articles_by_cat: dict, site_title: str, site_url: str,
                  s: dict, categories: list, out_dir: str) -> None:
    """Generate RSS 2.0 feeds: one master rss.xml + per-category rss-{slug}.xml."""
    from email.utils import formatdate

    base = site_url.rstrip("/")
    lang = s.get("lang", "ar")
    now_rss = formatdate(usegmt=True)

    def _item(art: dict, slug: str = "") -> str:
        title  = _xml_esc(art.get("title", ""))
        url    = _xml_esc(art.get("url", ""))
        source = _xml_esc(art.get("source", ""))
        date   = art.get("date", "")
        # Convert YYYY-MM-DD to RFC-2822
        try:
            from email.utils import format_datetime
            from datetime import datetime as _dt
            pub = format_datetime(_dt.strptime(date, "%Y-%m-%d"))
        except Exception:
            pub = now_rss
        cat_name = _xml_esc(art.get("cat_name", ""))
        return (
            f"    <item>\n"
            f"      <title>{title}</title>\n"
            f"      <link>{url}</link>\n"
            f"      <guid isPermaLink='true'>{url}</guid>\n"
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <author>{source}</author>\n"
            f"      {'<category>' + cat_name + '</category>' if cat_name else ''}\n"
            f"    </item>\n"
        )

    def _feed(feed_title: str, feed_link: str, desc: str, items: str) -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
            '  <channel>\n'
            f'    <title>{_xml_esc(feed_title)}</title>\n'
            f'    <link>{feed_link}</link>\n'
            f'    <atom:link href="{feed_link}" rel="self" type="application/rss+xml"/>\n'
            f'    <description>{_xml_esc(desc)}</description>\n'
            f'    <language>{lang}</language>\n'
            f'    <lastBuildDate>{now_rss}</lastBuildDate>\n'
            f'    <ttl>60</ttl>\n'
            f'{items}'
            '  </channel>\n'
            '</rss>\n'
        )

    # ── Master feed (all main categories, newest 60 articles) ────────────────
    all_arts: list[dict] = []
    for cat in categories:
        slug = cat.get("slug", "")
        if not slug or slug not in articles_by_cat:
            continue
        cat_data = articles_by_cat[slug]
        for art in cat_data["articles"]:
            art_copy = dict(art)
            art_copy["cat_name"] = cat.get("name", "")
            all_arts.append(art_copy)
    all_arts.sort(key=lambda a: a.get("date", ""), reverse=True)
    master_items = "".join(_item(a) for a in all_arts[:60])
    _write("rss.xml", _feed(site_title, f"{base}/index.html", site_title, master_items), out_dir)

    # ── Per-category feeds (up to 30 items each) ─────────────────────────────
    for cat in categories:
        slug = cat.get("slug", "")
        if not slug or slug not in articles_by_cat:
            continue
        cat_arts = articles_by_cat[slug]["articles"][:30]
        cat_items = "".join(_item(a) for a in cat_arts)
        _write(
            f"rss-{slug}.xml",
            _feed(f"{site_title} – {cat['name']}", f"{base}/{slug}.html",
                  cat.get("name", ""), cat_items),
            out_dir,
        )


# ──────────────────────────────────────────────────────────────────────────────
# PWA MANIFEST GENERATOR
# ──────────────────────────────────────────────────────────────────────────────

# Theme colours per language (matches nav accent)
_LANG_THEME = {
    "ar": "#1d4ed8", "en": "#2563eb", "fr": "#1d4ed8",
    "es": "#c2410c", "tr": "#dc2626",
}

def _generate_manifest(site_title: str, site_desc: str, site_url: str,
                       lang: str, out_dir: str) -> None:
    """Write a minimal PWA manifest.json."""
    theme   = _LANG_THEME.get(lang, "#6366f1")
    short   = site_title[:12] if len(site_title) > 12 else site_title
    start   = site_url.rstrip("/") + "/index.html" if site_url else "./index.html"
    payload = json.dumps({
        "name":             site_title,
        "short_name":       short,
        "description":      site_desc,
        "start_url":        start,
        "scope":            site_url or "./",
        "display":          "standalone",
        "orientation":      "portrait-primary",
        "background_color": "#ffffff",
        "theme_color":      theme,
        "lang":             lang,
        "dir":              "rtl" if lang == "ar" else "ltr",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        ],
        "categories": ["news"],
        "shortcuts": [
            {"name": site_title, "url": start, "description": site_desc},
        ],
    }, ensure_ascii=False, indent=2)
    _write("manifest.json", payload, out_dir)


# ──────────────────────────────────────────────────────────────────────────────
# ROUND-ROBIN SOURCE ORDERING
# ──────────────────────────────────────────────────────────────────────────────

def _round_robin(articles: list[dict], source_order: list[str]) -> list[dict]:
    """Re-order articles so sources are interleaved in round-robin fashion.

    Algorithm:
      1. Group articles by source_name, preserving newest-first order within each group.
      2. Arrange groups in the order listed in *source_order* (config order).
         Sources not found in the config are appended at the end.
      3. Pop one article at a time from each group in turn until all are exhausted.

    Result: article[0] = source1's latest, article[1] = source2's latest,
            article[2] = source3's latest, article[3] = source1's 2nd latest …
    """
    from collections import defaultdict

    # Group by source, newest first (DB already returns them in scraped_at DESC order)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for art in articles:
        buckets[art["source"]].append(art)

    # Build ordered list-of-lists following config source order
    ordered: list[list[dict]] = []
    seen: set[str] = set()
    for src_name in source_order:
        if src_name in buckets and src_name not in seen:
            ordered.append(buckets[src_name])
            seen.add(src_name)

    # Append any sources present in DB but not declared in config
    for src_name, bucket in buckets.items():
        if src_name not in seen:
            ordered.append(bucket)

    # Round-robin interleave
    result: list[dict] = []
    while any(ordered):
        for bucket in ordered:
            if bucket:
                result.append(bucket.pop(0))

    return result


def _generate_news_sitemap(
    all_articles: list,
    site_url: str,
    media_slugs: set,
    out_dir: str,
    lang: str = "ar",
    site_title: str = "Atlas News",
) -> None:
    """Generate news-sitemap.xml for Google News (last 48 h articles only)."""
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    _now = _dt.now(_tz.utc)
    _cutoff = _now - _td(hours=48)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">',
    ]
    included = 0
    for art in all_articles:
        slug = art.get("slug", "")
        if slug in media_slugs:
            continue
        scraped_raw = art.get("scraped_at", "")
        # Parse scraped_at "YYYY-MM-DD HH:MM:SS" → aware datetime
        try:
            art_dt = _dt.strptime(scraped_raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=_tz.utc)
        except (ValueError, TypeError):
            art_dt = _now  # fall back to now if parse fails
        if art_dt < _cutoff:
            continue
        art_hash  = _article_slug(art["url"])
        art_url   = f"{site_url.rstrip('/')}/article/{art_hash}.html"
        pub_date  = art_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        title_xml = art["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lines += [
            "  <url>",
            f"    <loc>{art_url}</loc>",
            "    <news:news>",
            "      <news:publication>",
            f"        <news:name>{site_title.replace('&','&amp;').replace('<','&lt;')[:50]}</news:name>",
            f"        <news:language>{lang}</news:language>",
            "      </news:publication>",
            f"      <news:publication_date>{pub_date}</news:publication_date>",
            f"      <news:title>{title_xml[:100]}</news:title>",
            "    </news:news>",
            f"    <lastmod>{pub_date}</lastmod>",
            "  </url>",
        ]
        included += 1
        if included >= 1000:  # Google News limit
            break
    lines.append("</urlset>")
    content = "\n".join(lines) + "\n"
    _write("news-sitemap.xml", content, out_dir)
    logger.info("News sitemap: %d articles → %s/news-sitemap.xml", included, out_dir)


def _generate_article_sitemap(
    all_articles: list,
    site_url: str,
    media_slugs: set,
    out_dir: str,
) -> None:
    """Generate sitemap-articles.xml — ALL article pages for Google indexing.

    Unlike news-sitemap.xml (48h only, Google News format), this covers every
    article page so Googlebot can discover and index older articles.
    Google's sitemap limit is 50,000 URLs per file.
    """
    from datetime import datetime as _dt
    base = site_url.rstrip("/")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    included = 0
    # Sort newest-first so Google prioritises fresh content on first crawl
    sorted_arts = sorted(
        all_articles,
        key=lambda a: a.get("scraped_at", ""),
        reverse=True,
    )
    for art in sorted_arts:
        if art.get("slug", "") in media_slugs:
            continue
        art_hash = _article_slug(art["url"])
        art_url  = f"{base}/article/{art_hash}.html"
        # Use scraped_at for lastmod (already RFC 3339-compatible with T+Z)
        raw_dt   = art.get("scraped_at", "")
        if raw_dt:
            try:
                _parsed = _dt.strptime(raw_dt[:19], "%Y-%m-%d %H:%M:%S")
                lastmod = _parsed.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            except (ValueError, TypeError):
                lastmod = raw_dt[:10]
        else:
            lastmod = _dt.now().strftime("%Y-%m-%d")
        lines += [
            "  <url>",
            f"    <loc>{art_url}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            "    <changefreq>never</changefreq>",
            "    <priority>0.5</priority>",
            "  </url>",
        ]
        included += 1
        if included >= 50000:  # Google sitemap limit
            break
    lines.append("</urlset>")
    content = "\n".join(lines) + "\n"
    _write("sitemap-articles.xml", content, out_dir)
    logger.info("Article sitemap: %d URLs → %s/sitemap-articles.xml", included, out_dir)


# ──────────────────────────────────────────────────────────────────────────────
# MAIN GENERATOR
# ──────────────────────────────────────────────────────────────────────────────

def generate_html(config_path: str | None = None, db_path: str | None = None,
                  output_dir: str | None = None, lang: str = "ar") -> str:
    if config_path:
        import json as _json
        with open(config_path, "r", encoding="utf-8") as _f:
            config = _json.load(_f)
    else:
        config = load_config()

    if db_path:
        from database.db import set_db_path
        set_db_path(db_path)

    # ── DB migration (ensure ai_summary column exists) ────────────────────────
    _init_db()

    # ── Language isolation check ───────────────────────────────────────────────
    _check_lang_isolation(config, lang)

    settings    = config.get("settings", {})
    site_title  = settings.get("site_title", "ملخص الأخبار الأسبوعي")
    site_desc   = settings.get("site_description", "أهم العناوين من مصادر متعددة في مكان واحد")
    oldest_days = int(settings.get("oldest_days", 7))

    s = STRINGS.get(lang, STRINGS["ar"])

    out_dir = (
        output_dir
        or settings.get("output_dir")
        or os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    )
    if lang == "en":
        out_dir = os.path.join(out_dir, "en") if not output_dir and not settings.get("output_dir") else out_dir

    def _wrt(filename: str, content: str) -> None:
        _write(filename, content, out_dir)

    # Determine world regions from config (supports language-specific lists)
    world_regions = config.get("world_regions", WORLD_REGIONS if lang == "ar" else [])
    region_slugs  = {r["slug"] for r in world_regions}
    has_world     = bool(world_regions)

    # Determine media regions from config (صوت وصورة)
    media_regions_list = config.get("media_regions", MEDIA_REGIONS if lang == "ar" else [])
    media_slugs_local  = {r["slug"] for r in media_regions_list}
    has_media          = bool(media_regions_list)

    _write_static_assets(out_dir, lang, settings.get("site_url", ""))

    # ── Site URL helpers for SEO ──────────────────────────────────────────────
    # _site_url = language-specific base (e.g. "https://atlasnews.solvixi.com/ar")
    # _root_url = domain root without lang path (e.g. "https://atlasnews.solvixi.com")
    # hreflang needs the root; canonical/breadcrumb need the lang-specific base.
    _site_url = settings.get("site_url", "").rstrip("/")
    _lang_prefix = _LANG_PATHS.get(lang, "")  # e.g. "/ar" for AR, "" for EN
    if _site_url and _lang_prefix and _site_url.endswith(_lang_prefix):
        _root_url = _site_url[: -len(_lang_prefix)].rstrip("/")
    else:
        _root_url = _site_url  # EN: site_url is already the root

    _og_img_url = f"{_root_url}/og-image.png" if _root_url else ""

    def _make_hreflang(filename: str) -> str:
        """Generate hreflang links using root domain (cross-language links)."""
        return _hreflang_links(_root_url, filename) if _root_url else ""

    def _make_org_ld() -> str:
        return _org_json_ld(site_title, _root_url) if _root_url else ""

    def _make_bc_ld(cat_name: str, page_file: str) -> str:
        """Breadcrumb JSON-LD — uses the language-specific base URL."""
        return _breadcrumb_json_ld(site_title, cat_name, _site_url, page_file) if _site_url else ""

    def _page_canonical(filename: str) -> str:
        """Absolute canonical URL for a page (language-specific path)."""
        return f"{_site_url}/{filename}" if _site_url else filename

    # Organisation JSON-LD (added once, on every page)
    _org_ld = _make_org_ld()

    # ── Market data (fetched once, used only on economy page) ─────────────────
    _root = os.path.dirname(os.path.abspath(__file__))
    _api_keys: dict = {}
    # Try local file first, then fall back to environment variables (used in CI/GitHub Actions)
    try:
        with open(os.path.join(_root, "config", "api_keys.json"),
                  "r", encoding="utf-8") as _kf:
            _api_keys = json.load(_kf)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    # Override with environment variables if set (GitHub Actions secrets)
    if os.environ.get("METALPRICEAPI_KEY"):
        _api_keys["metalpriceapi"] = os.environ["METALPRICEAPI_KEY"]
    if os.environ.get("ALPHAVANTAGE_KEY"):
        _api_keys["alphavantage"] = os.environ["ALPHAVANTAGE_KEY"]
    _cache_path = os.path.join(_root, "data", "market_cache.json")
    _market_data = _fetch_market_data(_api_keys, cache_path=_cache_path,
                                      force_refresh=True)

    # ── Story clusters (built by run.py → clustering/cluster.py) ─────────────
    _cluster_file = os.path.join(_root, "data", f"clusters_{lang}.json")
    _cluster_map: dict = {}
    try:
        with open(_cluster_file, "r", encoding="utf-8") as _cf:
            _cluster_map = json.load(_cf)
        logger.info("Clusters: loaded %d tagged articles for [%s]",
                    len(_cluster_map), lang)
    except FileNotFoundError:
        pass  # clusters not yet built — badges simply won't show
    except Exception as _ce:
        logger.warning("Clusters: failed to load %s: %s", _cluster_file, _ce)

    articles_by_cat = get_articles_by_category(days=oldest_days)
    categories      = config["categories"]
    now             = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_ar        = datetime.now().strftime("%Y/%m/%d")

    # ── Blacklist filtering ───────────────────────────────────────────────────
    # Load keywords from config/blacklist.json (created & managed by admin panel).
    # Any article whose title contains a blacklisted keyword (case-insensitive)
    # is excluded from all pages and the carousel.
    try:
        with open(BLACKLIST_PATH, "r", encoding="utf-8") as _bf:
            _bl_data = json.load(_bf)
        blacklist_kws: list[str] = [k.lower().strip() for k in _bl_data.get("keywords", []) if k.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        blacklist_kws = []

    if blacklist_kws:
        removed = 0
        for slug in list(articles_by_cat.keys()):
            before = articles_by_cat[slug]["articles"]
            after  = [a for a in before
                      if not any(kw in a["title"].lower() for kw in blacklist_kws)]
            removed += len(before) - len(after)
            articles_by_cat[slug]["articles"] = after
        if removed:
            logger.info("Blacklist: removed %d article(s) matching %d keyword(s)", removed, len(blacklist_kws))

    # ── Round-robin source ordering ───────────────────────────────────────────
    # Re-order each category's articles so sources are interleaved in config
    # order rather than purely chronologically.  One article from source-1,
    # then one from source-2, … cycling until all articles are placed.
    cat_source_order: dict[str, list[str]] = {
        cat["slug"]: [src["name"] for src in cat.get("sources", [])]
        for cat in categories
    }
    for slug, cat_data in articles_by_cat.items():
        src_order = cat_source_order.get(slug, [])
        if src_order and cat_data["articles"]:
            cat_data["articles"] = _round_robin(cat_data["articles"], src_order)
    logger.info("Round-robin ordering applied to %d category(ies)", len(articles_by_cat))

    # ── Per-category color overrides from sources.json ────────────────────────
    # The admin panel lets users pick a custom color per category and saves it
    # as cat["color"] in sources.json.  We override the module-level dicts here
    # so every helper (_card, _carousel, _sidebar) picks up the custom colors
    # without needing a signature change.
    for cat in categories:
        slug  = cat["slug"]
        color = cat.get("color", "").strip()
        if color and color.startswith("#") and len(color) in (4, 7):
            CATEGORY_COLORS[slug]    = color
            CATEGORY_GRADIENTS[slug] = f"linear-gradient(135deg, {color}, {_lighten(color, 0.35)})"

    all_articles: list[dict] = [
        {**art, "slug": slug}
        for slug, cat_data in articles_by_cat.items()
        for art in cat_data.get("articles", [])
    ]
    total_articles = len(all_articles)
    total_sources  = sum(len(c["sources"]) for c in categories)
    total_cats     = len(articles_by_cat)

    # ── Shared bits ───────────────────────────────────────────────────────────
    footer_cats = "".join(
        f'<li><a href="{esc(c["slug"])}.html">{esc(c.get("icon",""))} {esc(c["name"])}</a></li>'
        for c in categories if c["slug"] in articles_by_cat
    )
    _ga_id = settings.get("ga_id", "").strip()
    common = dict(
        desc=site_desc, footer_cats=footer_cats, today_ar=today_ar, now=now,
        total_articles=total_articles, total_sources=total_sources,
        ga_id=_ga_id, s=s,
    )

    # ── Language switcher helper for this build ───────────────────────────────
    def _lsw(page_file: str) -> str:
        return _lang_switcher(lang, page_file)

    # ── World subnav — homepage gets homepage=True so it hides on mobile ────────
    # (Region/Media pages use their own subnav WITHOUT homepage=True, stays visible)
    world_subnav = _world_subnav(world_regions=world_regions, s=s, homepage=True)

    # Pre-build category lookup: slug → (cat_name, cat_icon)
    cat_meta: dict[str, tuple[str, str]] = {
        c["slug"]: (c["name"], c.get("icon", ""))
        for c in categories
    }

    # ── INDEX PAGE — preview (PREVIEW_PER_CAT articles per category) ─────────
    home_sections = ""
    for cat in categories:
        slug     = cat["slug"]
        if slug in region_slugs or slug in media_slugs_local or slug in ECON_SUB_SLUGS:
            continue  # regions/media/econ-sub shown elsewhere, not home
        cat_data = articles_by_cat.get(slug)
        if not cat_data or not cat_data["articles"]:
            continue
        color   = CATEGORY_COLORS.get(slug, DEFAULT_COLOR)
        preview = cat_data["articles"][:PREVIEW_PER_CAT]
        cards   = "".join(_card(a, slug, s=s, cluster_map=_cluster_map, site_url=_site_url) for a in preview)
        total   = len(cat_data["articles"])
        more_btn = (
            f'<a href="{esc(slug)}.html" class="more-btn" style="border-color:{esc(color)};color:{esc(color)}">'
            f'{s["more_from"]} {esc(cat["name"])} ({total}) {s["arrow"]}</a>'
            if total > PREVIEW_PER_CAT else ""
        )
        home_sections += (
            f'<section class="category-section" id="{esc(slug)}" aria-label="{esc(cat["name"])}">'
            f'<div class="section-header" style="border-inline-start-color:{esc(color)}">'
            f'<span class="section-icon">{esc(cat.get("icon","📰"))}</span>'
            f'<h2 class="section-title"><a href="{esc(slug)}.html" class="section-title-link">{esc(cat["name"])}</a></h2>'
            f'</div>'
            f'<div class="articles-grid">{cards}</div>'
            f'{more_btn}'
            f'</section>'
        )

    if not home_sections:
        home_sections = (
            f'<div class="empty-state"><h2>{s["no_news"]}</h2>'
            f'<p>{s["run_hint"]}</p></div>'
        )

    # Home carousel: mix 3 articles per non-region, non-media category
    _home_carousel_arts = _gather_carousel(
        articles_by_cat,
        [(c["slug"], c["name"], c.get("icon", ""))
         for c in categories if c["slug"] not in region_slugs and c["slug"] not in media_slugs_local and c["slug"] not in ECON_SUB_SLUGS],
        per_slug=3,
    )
    # LCP image = first carousel hero image (preloaded in <head> for speed)
    _home_lcp_img = next(
        (a["image"] for a in _home_carousel_arts if a.get("image", "").startswith("http")),
        ""
    )
    home_carousel = _carousel(_home_carousel_arts, s=s, site_url=_site_url, media_slugs=media_slugs_local)
    _wrt("index.html", _page(
        title=site_title,
        nav_html=_nav(categories, articles_by_cat, active="home",
                      s=s, region_slugs=region_slugs, has_world=has_world,
                      media_slugs=media_slugs_local),
        main_html=home_sections,
        world_subnav_html=world_subnav,
        carousel_html=home_carousel,
        canonical=_page_canonical("index.html"),
        hreflang_html=_make_hreflang("index.html"),
        og_image_url=_og_img_url,
        extra_json_ld=_org_ld,
        lang_switcher_html=_lsw("index.html"),
        lcp_image_url=_home_lcp_img,
        **common,
    ))

    # ── ARTICLE PAGES — one HTML per article (for Google News / SEO) ─────────
    art_dir = os.path.join(out_dir, "article")
    os.makedirs(art_dir, exist_ok=True)
    art_pages_written = 0
    for art in all_articles:
        _slug = art.get("slug", "")
        if _slug in media_slugs_local:
            continue  # Skip YouTube videos — no article pages needed
        _related = [
            a for a in articles_by_cat.get(_slug, {}).get("articles", [])
            if a["url"] != art["url"]
        ][:4]
        _art_hash = _article_slug(art["url"])
        _art_html = _article_page_html(
            art=art,
            slug=_slug,
            related=_related,
            s=s,
            site_title=site_title,
            site_url=_site_url,
            cat_meta=cat_meta,
            lang=lang,
            cluster_map=_cluster_map,
            ga_id=_ga_id,
        )
        _write(f"article/{_art_hash}.html", _art_html, out_dir)
        art_pages_written += 1
    logger.info("Article pages: wrote %d pages in %s/article/", art_pages_written, out_dir)

    # ── NEWS SITEMAP — Google News (last 48h articles only) ───────────────────
    _generate_news_sitemap(
        all_articles=all_articles,
        site_url=_site_url,
        media_slugs=media_slugs_local,
        out_dir=out_dir,
        lang=lang,
        site_title=site_title,
    )
    # Full article sitemap — helps Google discover older articles (>48h)
    _generate_article_sitemap(
        all_articles=all_articles,
        site_url=_site_url,
        media_slugs=media_slugs_local,
        out_dir=out_dir,
    )

    # ── CATEGORY PAGES — all articles (generate even for empty categories) ───
    pages_written = 1
    for cat in categories:
        slug     = cat["slug"]
        cat_data = articles_by_cat.get(slug)

        color     = CATEGORY_COLORS.get(slug, DEFAULT_COLOR)
        gradient  = CATEGORY_GRADIENTS.get(slug, DEFAULT_GRADIENT)
        cat_title = site_title
        cat_desc  = s["cat_desc_tpl"].format(name=cat["name"])

        breadcrumb = (
            f'<div class="breadcrumb">'
            f'<a href="index.html">{s["home"]}</a>'
            f'<span class="bc-sep">›</span>'
            f'<span>{esc(cat.get("icon",""))} {esc(cat["name"])}</span>'
            f'</div>'
        )
        # For vid-* sections only show YouTube watch URLs; other slugs show all
        raw_articles = cat_data["articles"] if (cat_data and cat_data["articles"]) else []
        if slug in media_slugs_local:
            raw_articles = [a for a in raw_articles if _is_yt_url(a.get("url", ""))]
        if raw_articles:
            cards      = "".join(_card(a, slug, use_article_page=(slug not in media_slugs_local), s=s, cluster_map=_cluster_map, site_url=_site_url) for a in raw_articles)
            grid       = f'<div class="articles-grid">{cards}</div>'
            src_filter = _source_filter_strip(
                raw_articles, cat.get("sources", []), color, s
            )
        else:
            grid       = (
                f'<div class="empty-state">'
                f'<h2>{s["coming_soon"]}</h2>'
                f'<p>{s["coming_desc"]}</p>'
                f'</div>'
            )
            src_filter = ""
        cat_section = (
            f'{breadcrumb}'
            f'<section class="category-section" id="{esc(slug)}" aria-label="{esc(cat["name"])}">'
            f'{src_filter}'
            f'{grid}'
            f'</section>'
        )

        # Region pages get the world subnav; vid-* pages get the media subnav
        if slug in media_slugs_local:
            page_world_subnav = _media_subnav(
                active_slug=slug, media_regions=media_regions_list, s=s
            )
        elif slug in region_slugs:
            page_world_subnav = _world_subnav(
                active_slug=slug, world_regions=world_regions, s=s
            )
        else:
            page_world_subnav = ""

        # Per-category carousel: articles from this category only
        # Pass yt_only_slugs so vid-* carousels skip non-YouTube entries
        _cat_carousel_arts = _gather_carousel(
            articles_by_cat,
            [(slug, cat["name"], cat.get("icon", ""))],
            per_slug=16,
            yt_only_slugs=media_slugs_local if slug in media_slugs_local else None,
        )
        # LCP = first image of category carousel (or first article image as fallback)
        _cat_lcp_img = next(
            (a["image"] for a in _cat_carousel_arts if a.get("image", "").startswith("http")),
            next((a.get("image", "") for a in raw_articles if a.get("image", "").startswith("http")), ""),
        )
        cat_carousel = _carousel(_cat_carousel_arts, s=s, site_url=_site_url, media_slugs=media_slugs_local)
        # Economy tabs widget on economy, business, and travel pages
        if slug in {"economy", "business", "travel"}:
            cat_ticker = _economy_widget(s, active_tab=slug)
        else:
            cat_ticker = ""
        # RSS link: category-specific feed when available
        cat_rss = f"rss-{slug}.xml" if slug in articles_by_cat else "rss.xml"
        _cat_page_file = f"{slug}.html"
        _cat_bc_ld = (
            _make_bc_ld(cat["name"], _cat_page_file)
            if slug not in region_slugs and slug not in media_slugs_local
            else ""
        )
        # ItemList JSON-LD: tells Google this page is a list of news articles
        _cat_item_list_ld = (
            _item_list_json_ld(
                cat_name=cat["name"],
                cat_url=_page_canonical(_cat_page_file),
                articles=raw_articles[:20],
                site_url=_site_url,
            )
            if raw_articles and slug not in media_slugs_local
            else ""
        )
        _cat_extra_ld = "\n".join(filter(None, [_org_ld, _cat_bc_ld, _cat_item_list_ld]))
        # Override desc with category-specific description (common has site_desc)
        _cat_common = {**common, "desc": cat_desc}
        _wrt(_cat_page_file, _page(
            title=cat_title,
            nav_html=_nav(categories, articles_by_cat, active=slug,
                          s=s, region_slugs=region_slugs, has_world=has_world,
                          media_slugs=media_slugs_local, has_media=has_media),
            main_html=cat_section,
            canonical=_page_canonical(_cat_page_file),
            hreflang_html=_make_hreflang(_cat_page_file),
            og_image_url=_og_img_url,
            extra_json_ld=_cat_extra_ld,
            world_subnav_html=page_world_subnav,
            ticker_html=cat_ticker,
            carousel_html=cat_carousel,
            rss_url=cat_rss,
            lang_switcher_html=_lsw(_cat_page_file),
            lcp_image_url=_cat_lcp_img,
            **_cat_common,
        ))
        pages_written += 1

        # ── PRICES.HTML — sub-page of economy ────────────────────────────────
        if slug == "economy":
            _wrt("prices.html", _page(
                title=site_title,
                nav_html=_nav(categories, articles_by_cat, active="economy",
                              s=s, region_slugs=region_slugs, has_world=has_world,
                              media_slugs=media_slugs_local),
                main_html=_prices_main_html(_market_data, s=s),
                canonical=_page_canonical("prices.html"),
                hreflang_html=_make_hreflang("prices.html"),
                og_image_url=_og_img_url,
                extra_json_ld=_org_ld,
                world_subnav_html="",
                ticker_html=_economy_widget(s, active_tab="prices"),
                carousel_html="",
                lang_switcher_html=_lsw("prices.html"),
                **common,
            ))
            pages_written += 1

    # ── WORLD.HTML — aggregated world-regions landing page ────────────────────
    if has_world:
        world_sections = ""
        for region in world_regions:
            slug     = region["slug"]
            cat_data = articles_by_cat.get(slug)
            color    = CATEGORY_COLORS.get(slug, DEFAULT_COLOR)
            gradient = CATEGORY_GRADIENTS.get(slug, DEFAULT_GRADIENT)

            if cat_data and cat_data["articles"]:
                preview  = cat_data["articles"][:PREVIEW_PER_CAT]
                cards    = "".join(_card(a, slug, s=s, cluster_map=_cluster_map, site_url=_site_url) for a in preview)
                total    = len(cat_data["articles"])
                more_btn = (
                    f'<a href="{esc(slug)}.html" class="more-btn" '
                    f'style="border-color:{esc(color)};color:{esc(color)}">'
                    f'{s["more_from"]} {esc(region["name"])} ({total}) {s["arrow"]}</a>'
                    if total > PREVIEW_PER_CAT else ""
                )
                grid = f'<div class="articles-grid">{cards}</div>{more_btn}'
            else:
                world_coming = s["world_coming_tpl"].format(
                    href=esc(slug) + ".html", color=esc(color)
                )
                grid = (
                    f'<div class="empty-state">'
                    f'<h2>{s["coming_soon"]}</h2>'
                    f'<p>{world_coming}</p>'
                    f'</div>'
                )

            world_sections += (
                f'<section class="category-section" id="{esc(slug)}" aria-label="{esc(region["name"])}">'
                f'<div class="section-header" style="border-inline-start-color:{esc(color)};'
                f'background:linear-gradient(135deg,{esc(color)}18,transparent)">'
                f'<span class="section-icon">{esc(region["icon"])}</span>'
                f'<h2 class="section-title">{esc(region["name"])}</h2>'
                f'</div>'
                f'{grid}'
                f'</section>'
            )

        # World carousel: mix 3 articles per region
        world_carousel = _carousel(_gather_carousel(
            articles_by_cat,
            [(r["slug"], r["name"], r["icon"]) for r in world_regions],
            per_slug=3,
        ), s=s, site_url=_site_url)
        _wrt("world.html", _page(
            title=site_title,
            nav_html=_nav(categories, articles_by_cat, active="world",
                          s=s, region_slugs=region_slugs, has_world=has_world,
                          media_slugs=media_slugs_local, has_media=has_media),
            main_html=world_sections,
            world_subnav_html=_world_subnav(world_regions=world_regions, s=s),
            canonical=_page_canonical("world.html"),
            hreflang_html=_make_hreflang("world.html"),
            og_image_url=_og_img_url,
            extra_json_ld=_org_ld,
            carousel_html=world_carousel,
            lang_switcher_html=_lsw("world.html"),
            **common,
        ))
        pages_written += 1

    # ── MEDIA.HTML — صوت وصورة landing page ──────────────────────────────────
    if has_media:
        media_sections = ""
        for region in media_regions_list:
            slug     = region["slug"]
            cat_data = articles_by_cat.get(slug)
            color    = CATEGORY_COLORS.get(slug, DEFAULT_COLOR)

            # Only show genuine YouTube watch links in vid-* sections
            yt_articles = [
                a for a in (cat_data["articles"] if cat_data else [])
                if _is_yt_url(a.get("url", ""))
            ]
            if yt_articles:
                preview  = yt_articles[:PREVIEW_PER_CAT]
                cards    = "".join(_card(a, slug, use_article_page=False, s=s, cluster_map=_cluster_map, site_url=_site_url) for a in preview)
                total    = len(yt_articles)
                more_btn = (
                    f'<a href="{esc(slug)}.html" class="more-btn" '
                    f'style="border-color:{esc(color)};color:{esc(color)}">'
                    f'{s["more_from"]} {esc(region["name"])} ({total}) {s["arrow"]}</a>'
                    if total > PREVIEW_PER_CAT else ""
                )
                grid = f'<div class="articles-grid">{cards}</div>{more_btn}'
            else:
                world_coming = s["world_coming_tpl"].format(
                    href=esc(slug) + ".html", color=esc(color)
                )
                grid = (
                    f'<div class="empty-state">'
                    f'<h2>{s["coming_soon"]}</h2>'
                    f'<p>{world_coming}</p>'
                    f'</div>'
                )

            media_sections += (
                f'<section class="category-section" id="{esc(slug)}" aria-label="{esc(region["name"])}">'
                f'<div class="section-header" style="border-inline-start-color:{esc(color)};'
                f'background:linear-gradient(135deg,{esc(color)}18,transparent)">'
                f'<span class="section-icon">{esc(region["icon"])}</span>'
                f'<h2 class="section-title">{esc(region["name"])}</h2>'
                f'</div>'
                f'{grid}'
                f'</section>'
            )

        media_carousel = _carousel(_gather_carousel(
            articles_by_cat,
            [(r["slug"], r["name"], r["icon"]) for r in media_regions_list],
            per_slug=3,
            yt_only_slugs=media_slugs_local,
        ), s=s, site_url=_site_url)
        _wrt("media.html", _page(
            title=site_title,
            nav_html=_nav(categories, articles_by_cat, active="media",
                          s=s, region_slugs=region_slugs, has_world=has_world,
                          media_slugs=media_slugs_local, has_media=has_media),
            main_html=media_sections,
            world_subnav_html=_media_subnav(media_regions=media_regions_list, s=s),
            canonical=_page_canonical("media.html"),
            hreflang_html=_make_hreflang("media.html"),
            og_image_url=_og_img_url,
            extra_json_ld=_org_ld,
            carousel_html=media_carousel,
            lang_switcher_html=_lsw("media.html"),
            **common,
        ))
        pages_written += 1

        # ── LIVE.HTML — live TV channels directory ────────────────────────────
        _live_channels = LIVE_CHANNELS.get(lang, LIVE_CHANNELS.get("en", []))
        _live_main = _live_page_html(
            lang=lang, s=s, channels=_live_channels,
            media_regions=media_regions_list,
        )
        _wrt("live.html", _page(
            title=s.get("live_tv_title", "Live TV") + " — " + site_title,
            nav_html=_nav(categories, articles_by_cat, active="live",
                          s=s, region_slugs=region_slugs, has_world=has_world,
                          media_slugs=media_slugs_local, has_media=has_media),
            main_html=_live_main,
            world_subnav_html="",
            canonical=_page_canonical("live.html"),
            hreflang_html=_make_hreflang("live.html"),
            og_image_url=_og_img_url,
            extra_json_ld=_org_ld,
            carousel_html="",
            lang_switcher_html=_lsw("live.html"),
            **common,
        ))
        pages_written += 1

    # ── RSS Feeds ─────────────────────────────────────────────────────────────
    _generate_rss(articles_by_cat, site_title, settings.get("site_url",""),
                  s, categories, out_dir)
    logger.info("RSS feeds written to %s", out_dir)

    # ── PWA Manifest ─────────────────────────────────────────────────────────
    _generate_manifest(site_title, site_desc, settings.get("site_url",""),
                       lang, out_dir)

    # ── Sitemap + robots.txt (SEO) ────────────────────────────────────────────
    site_url = settings.get("site_url", "").rstrip("/")
    if site_url:
        # site_url already contains the language path (e.g. "https://domain.com/fr")
        _base = site_url.rstrip("/")
        # Compute root URL for cross-language hreflang links in sitemap
        _sm_prefix = _LANG_PATHS.get(lang, "")
        if _sm_prefix and _base.endswith(_sm_prefix):
            _sm_root = _base[: -len(_sm_prefix)].rstrip("/")
        else:
            _sm_root = _base  # EN: base IS root

        def _xhtml_links(filename: str) -> str:
            """<xhtml:link> tags for all 5 language variants of a page."""
            parts = []
            for _lc, _lp in _LANG_PATHS.items():
                _hl   = _LANG_HREFLANG[_lc]
                _href = f"{_sm_root}{_lp}/{filename}"
                parts.append(f'    <xhtml:link rel="alternate" hreflang="{_hl}" href="{_href}"/>')
            parts.append(f'    <xhtml:link rel="alternate" hreflang="x-default" href="{_sm_root}/{filename}"/>')
            return "\n".join(parts)

        # Page list with (filename, priority, changefreq)
        _static_pages = [
            ("index.html",     "1.0", "hourly"),
            ("about.html",     "0.4", "monthly"),
            ("privacy.html",   "0.4", "monthly"),
            ("contact.html",   "0.4", "monthly"),
            ("terms.html",     "0.4", "monthly"),
            ("advertise.html", "0.4", "monthly"),
        ]
        _cat_pages   = []
        _region_pages = []
        for cat in categories:
            _slug = cat.get("slug", "")
            if not _slug:
                continue
            if _slug in region_slugs or _slug in media_slugs_local:
                _region_pages.append((_slug + ".html", "0.6", "hourly"))
            else:
                _cat_pages.append((_slug + ".html", "0.8", "hourly"))
        if has_world:
            _cat_pages.append(("world.html",  "0.7", "hourly"))
            for r in world_regions:
                _region_pages.append((f'{r["slug"]}.html', "0.6", "hourly"))
        if has_media:
            _cat_pages.append(("media.html",  "0.7", "hourly"))
            _cat_pages.append(("live.html",   "0.7", "hourly"))
            for r in media_regions_list:
                _region_pages.append((f'{r["slug"]}.html', "0.6", "hourly"))
        if any(cat.get("slug") == "economy" for cat in categories):
            _cat_pages.append(("prices.html", "0.6", "daily"))

        _all_sm_pages = _static_pages + _cat_pages + _region_pages
        _today = datetime.now().strftime("%Y-%m-%d")
        _url_blocks = []
        for _fname, _pri, _freq in _all_sm_pages:
            _url_blocks.append(
                f"  <url>\n"
                f"    <loc>{_base}/{_fname}</loc>\n"
                f"    <lastmod>{_today}</lastmod>\n"
                f"    <changefreq>{_freq}</changefreq>\n"
                f"    <priority>{_pri}</priority>\n"
                f"{_xhtml_links(_fname)}\n"
                f"  </url>"
            )
        _sitemap_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
            '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
            + "\n".join(_url_blocks) + "\n"
            '</urlset>\n'
        )
        _wrt("sitemap.xml", _sitemap_xml)

        # Update robots.txt with full bot rules + absolute sitemap URLs
        _robots = (
            f"# Atlas News — robots.txt\n"
            f"# {_base}\n\n"
            "User-agent: Googlebot\n"
            "Allow: /\n"
            "Disallow: /admin\n\n"
            "User-agent: Googlebot-News\n"
            "Allow: /\n\n"
            "User-agent: Bingbot\n"
            "Allow: /\n"
            "Disallow: /admin\n"
            "Crawl-delay: 5\n\n"
            "User-agent: SemrushBot\n"
            "Crawl-delay: 30\n"
            "Disallow: /article/\n\n"
            "User-agent: AhrefsBot\n"
            "Crawl-delay: 30\n"
            "Disallow: /article/\n\n"
            "User-agent: MJ12bot\n"
            "Disallow: /\n\n"
            "User-agent: DotBot\n"
            "Disallow: /\n\n"
            "User-agent: GPTBot\n"
            "Crawl-delay: 30\n\n"
            "User-agent: PerplexityBot\n"
            "Crawl-delay: 30\n\n"
            "User-agent: anthropic-ai\n"
            "Crawl-delay: 30\n\n"
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin\n"
            "Crawl-delay: 10\n\n"
            f"Sitemap: {_base}/sitemap.xml\n"
            f"Sitemap: {_base}/news-sitemap.xml\n"
            f"Sitemap: {_base}/sitemap-articles.xml\n"
        )
        _wrt("robots.txt", _robots)
        logger.info("SEO: sitemap.xml written for %s", _base)

    output_path = os.path.join(out_dir, "index.html")
    logger.info(
        "Site generated: %s  (%d articles, %d categories, %d pages)",
        output_path, total_articles, total_cats, pages_written,
    )
    return output_path


if __name__ == "__main__":
    import argparse as _ap
    _parser = _ap.ArgumentParser(description="Static site generator")
    _parser.add_argument("--config", default=None, help="Path to sources config JSON")
    _parser.add_argument("--db",     default=None, help="Path to SQLite database")
    _parser.add_argument("--out",    default=None, help="Output directory")
    _parser.add_argument("--lang",   default="ar", choices=["ar", "en"])
    _args = _parser.parse_args()
    generate_html(config_path=_args.config, db_path=_args.db,
                  output_dir=_args.out, lang=_args.lang)
