import html as _html_lib
import json
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.loader import load_config
from database.db import get_articles_by_category

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

DEFAULT_COLOR = "#6366f1"
DEFAULT_GRADIENT = "linear-gradient(135deg, #6366f1, #8b5cf6)"

# Currency pairs shown in the economy market strip (code, display_label)
DEFAULT_MARKET_PAIRS: list[tuple[str, str]] = [
    # Arab currencies
    ("MAD", "MAD"), ("DZD", "DZD"), ("TND", "TND"), ("EGP", "EGP"),
    ("SAR", "SAR"), ("AED", "AED"), ("KWD", "KWD"), ("QAR", "QAR"),
    ("BHD", "BHD"), ("OMR", "OMR"), ("JOD", "JOD"),
    # Major world economies
    ("EUR", "EUR"), ("GBP", "GBP"), ("JPY", "JPY"), ("CNY", "CNY"),
    ("CHF", "CHF"), ("CAD", "CAD"), ("AUD", "AUD"),
]

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


# Arabic display names override (for any remaining non-Arabic source names)
SOURCE_AR_NAME: dict[str, str] = {
    "Le360":    "لو 360",
    "MAP News": "وكالة ماب",
}

# UI strings per language — extend this dict to add more languages
STRINGS: dict[str, dict] = {
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
        "theme_btn_label": "تبديل الوضع", "live_label": "مباشر",
        "nav_label": "الأقسام", "header_label": "عنوان الموقع",
        "back_to_top": "العودة للأعلى", "theme_color": "#1d4ed8",
        "updated": "آخر تحديث", "footer_links": "روابط",
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
        "theme_btn_label": "Toggle theme", "live_label": "Live",
        "nav_label": "Sections", "header_label": "Site header",
        "back_to_top": "Back to top", "theme_color": "#2563eb",
        "updated": "Last updated", "footer_links": "Links",
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
        "theme_btn_label": "Changer le thème", "live_label": "En direct",
        "nav_label": "Sections", "header_label": "En-tête",
        "back_to_top": "Retour en haut", "theme_color": "#1d4ed8",
        "updated": "Mise à jour", "footer_links": "Liens",
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
        "theme_btn_label": "Cambiar tema", "live_label": "En vivo",
        "nav_label": "Secciones", "header_label": "Encabezado",
        "back_to_top": "Volver arriba", "theme_color": "#c2410c",
        "updated": "Actualizado", "footer_links": "Enlaces",
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
        "theme_btn_label": "Temayı değiştir", "live_label": "Canlı",
        "nav_label": "Bölümler", "header_label": "Site başlığı",
        "back_to_top": "Başa dön", "theme_color": "#dc2626",
        "updated": "Son güncelleme", "footer_links": "Bağlantılar",
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
    },
}


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

    Generates relative URLs from the current language directory to each
    target language directory.  Language-specific slugs are resolved via
    _xslug() so links always point to an existing page.
    """
    slug  = page_file.removesuffix(".html")
    items = ""
    for lang, prefix in LANG_DIRS.items():
        label = LANG_LABELS[lang]
        if lang == current_lang:
            items += f'<span class="lang-btn current">{label}</span>'
        else:
            target_file = _xslug(slug, lang)
            if current_lang == "en":
                href = f"{prefix}{target_file}"      # root  → subdir/page
            elif lang == "en":
                href = f"../{target_file}"           # subdir → root/page
            else:
                href = f"../{prefix}{target_file}"   # subdir → ../other/page
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
.site-nav{background:var(--nav-bg);position:static;z-index:200;box-shadow:0 1px 8px rgba(0,0,0,.07);backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}
.nav-inner{max-width:1200px;margin:0 auto;padding:0 6px;display:flex;flex-wrap:wrap;gap:1px}
.nav-tab{display:inline-flex;align-items:center;gap:4px;color:var(--nav-text);padding:8px 10px;font-size:.84em;white-space:nowrap;border-bottom:3px solid transparent;transition:all .2s;font-weight:700;cursor:pointer;border-radius:6px 6px 0 0}
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


/* ===================== MAIN LAYOUT ===================== */
.main-wrapper{max-width:1200px;margin:0 auto;padding:24px 20px}

/* ===================== CATEGORY SECTIONS ===================== */
.content-area{min-width:0}
.category-section{margin-bottom:44px;scroll-margin-top:60px}
.section-header{display:flex;align-items:center;gap:12px;padding:14px 20px;margin-bottom:20px;background:var(--surface);border-radius:var(--radius);border-inline-start:5px solid #888;box-shadow:var(--card-shadow);position:relative;overflow:hidden}
.section-header::after{content:'';position:absolute;left:0;top:0;bottom:0;width:40%;background:linear-gradient(90deg,rgba(99,102,241,.04),transparent);pointer-events:none}
.section-icon{font-size:1.5em}
.section-title{font-size:1.3em;font-weight:800;letter-spacing:-.3px}

/* ===================== ARTICLES GRID ===================== */
.articles-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}

/* ===================== ARTICLE CARD ===================== */
@keyframes cardIn{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
.article-card{border-radius:var(--radius);overflow:hidden;box-shadow:var(--card-shadow);transition:transform .3s cubic-bezier(.4,0,.2,1),box-shadow .3s;border:1px solid var(--border);animation:cardIn .42s ease both;aspect-ratio:4/3;position:relative;background:#1a2744}
.article-card:nth-child(2){animation-delay:.07s}
.article-card:nth-child(3){animation-delay:.14s}
.article-card:nth-child(4){animation-delay:.21s}
.article-card:nth-child(5){animation-delay:.07s}
.article-card:nth-child(6){animation-delay:.14s}
.article-card:nth-child(7){animation-delay:.21s}
.article-card:nth-child(8){animation-delay:.28s}
.article-card:hover{transform:translateY(-4px);box-shadow:var(--card-shadow-hover)}
.card-link{display:block;position:absolute;inset:0;color:inherit;text-decoration:none}
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
.article-card.card--no-img{background:#ffffff;border:1px solid var(--border)}
.article-card.card--no-img .card-overlay{display:none}
.article-card.card--no-img .card-title{color:var(--text);text-shadow:none}
.article-card.card--no-img .card-date{color:var(--text-light)}
.article-card.card--no-img:hover .card-title{color:var(--accent)}

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
.footer-inner{max-width:1200px;margin:0 auto;padding:0 20px 36px;display:grid;grid-template-columns:2fr 1fr;gap:36px}
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

/* ===================== LANGUAGE SWITCHER ===================== */
.lang-switcher{display:flex;align-items:center;gap:3px;flex-shrink:0}
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
  .footer-inner{grid-template-columns:1fr}
  .footer-section:last-child{display:none}
}
@media(max-width:480px){
  .articles-grid{grid-template-columns:1fr}
  .card-title{font-size:1em}
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
"""

APP_JS = r"""
'use strict';

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
"""

PRIVACY_HTML = """\
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>سياسة الخصوصية</title>
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
  <p class="sub">آخر تحديث: 2025</p>

  <p>نرحب بك في <strong>ملخص الأخبار الأسبوعي</strong>. نلتزم بحماية خصوصيتك وفيما يلي توضيح كامل لسياستنا.</p>

  <h2>1. المعلومات التي نجمعها</h2>
  <p>هذا الموقع لا يجمع أي بيانات شخصية مباشرة. نحن موقع تجميع إخباري يعرض عناوين من مصادر أخرى.</p>
  <ul>
    <li>لا نطلب تسجيلاً أو اشتراكاً</li>
    <li>لا نستخدم ملفات تعريف الارتباط (Cookies) الخاصة بنا</li>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>من نحن</title>
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
  <p class="sub">ملخص الأخبار الأسبوعي — مجمّع إخباري آلي</p>

  <p><strong>ملخص الأخبار الأسبوعي</strong> هو موقع تجميع إخباري يجمع أهم العناوين من مصادر عربية وعالمية موثوقة في مكان واحد، دون الحاجة إلى زيارة عشرات المواقع يومياً.</p>

  <h2>كيف يعمل الموقع</h2>
  <div class="steps">
    <div class="step"><span class="step-num">1</span><span>يتم جلب العناوين بشكل آلي يومياً من المصادر المحددة</span></div>
    <div class="step"><span class="step-num">2</span><span>يتم تصفية العناوين غير ذات الصلة وإزالة المكررات تلقائياً</span></div>
    <div class="step"><span class="step-num">3</span><span>يعرض الموقع العنوان ورابط المصدر الأصلي فقط — لا يتم تعديل أي محتوى</span></div>
    <div class="step"><span class="step-num">4</span><span>يتجدد الموقع تلقائياً عبر GitHub Actions كل يوم</span></div>
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
    <span class="chip">💻 TechRadar</span>
    <span class="chip">💻 Wired</span>
    <span class="chip">⚽ كورة</span>
    <span class="chip">⚽ يلا كورة</span>
    <span class="chip">🔬 WebMD</span>
    <span class="chip">🔬 Nature</span>
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
  </ul>

  <h2>إخلاء المسؤولية</h2>
  <p>هذا الموقع هو مجمّع إخباري آلي. جميع المقالات مرتبطة بمصادرها الأصلية ونحن لسنا مسؤولين عن محتواها. قد يعرض الموقع إعلانات من خلال Google AdSense، لمزيد من التفاصيل راجع <a href="privacy.html">سياسة الخصوصية</a>.</p>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>Privacy Policy</title>
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
  <p class="sub">Last updated: 2025</p>
  <p>Welcome to <strong>World News</strong>. We are committed to protecting your privacy.</p>
  <h2>1. Information We Collect</h2>
  <p>This site does not collect personal data directly. We are a news aggregator that displays headlines from other sources.</p>
  <ul>
    <li>No registration or subscription required</li>
    <li>We do not use our own cookies</li>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>About</title>
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
  <p class="sub">World News — Automated news aggregator</p>
  <p><strong>World News</strong> is a news aggregator that gathers the most important headlines from trusted international sources in one place, without needing to visit dozens of sites every day.</p>
  <h2>How It Works</h2>
  <div class="steps">
    <div class="step"><span class="step-num">1</span><span>Headlines are fetched automatically every day from configured sources</span></div>
    <div class="step"><span class="step-num">2</span><span>Irrelevant headlines are filtered and duplicates are removed automatically</span></div>
    <div class="step"><span class="step-num">3</span><span>The site displays the headline and a link to the original source only — no content is modified</span></div>
    <div class="step"><span class="step-num">4</span><span>The site is refreshed automatically via GitHub Actions every day</span></div>
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
  </ul>
  <h2>Disclaimer</h2>
  <p>This site is an automated news aggregator. All articles link to their original sources and we are not responsible for their content. The site may display ads via Google AdSense; see <a href="privacy.html">Privacy Policy</a> for details.</p>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>Politique de confidentialité</title>
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
  <p class="sub">Dernière mise à jour : 2025</p>
  <p>Bienvenue sur <strong>Actualités Mondiales</strong>. Nous nous engageons à protéger votre vie privée.</p>
  <h2>1. Informations collectées</h2>
  <p>Ce site ne collecte aucune donnée personnelle directement. Nous sommes un agrégateur de nouvelles qui affiche des titres provenant d'autres sources.</p>
  <ul>
    <li>Aucune inscription ou abonnement requis</li>
    <li>Nous n'utilisons pas nos propres cookies</li>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>À propos</title>
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
  <p class="sub">Actualités Mondiales — Agrégateur d'actualités automatique</p>
  <p><strong>Actualités Mondiales</strong> est un agrégateur de nouvelles qui rassemble les titres les plus importants de sources internationales fiables en un seul endroit.</p>
  <h2>Comment ça fonctionne</h2>
  <div class="steps">
    <div class="step"><span class="step-num">1</span><span>Les titres sont récupérés automatiquement chaque jour depuis les sources configurées</span></div>
    <div class="step"><span class="step-num">2</span><span>Les titres non pertinents sont filtrés et les doublons supprimés automatiquement</span></div>
    <div class="step"><span class="step-num">3</span><span>Le site affiche le titre et un lien vers la source originale uniquement</span></div>
    <div class="step"><span class="step-num">4</span><span>Le site est mis à jour automatiquement via GitHub Actions chaque jour</span></div>
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
  </ul>
  <h2>Avertissement</h2>
  <p>Ce site est un agrégateur automatique. Tous les articles renvoient à leurs sources originales. Consultez la <a href="privacy.html">politique de confidentialité</a> pour les détails sur la publicité.</p>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>Política de privacidad</title>
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
  <p class="sub">Última actualización: 2025</p>
  <p>Bienvenido a <strong>Noticias Mundiales</strong>. Estamos comprometidos a proteger tu privacidad.</p>
  <h2>1. Información que recopilamos</h2>
  <p>Este sitio no recopila datos personales directamente. Somos un agregador de noticias que muestra titulares de otras fuentes.</p>
  <ul>
    <li>No se requiere registro ni suscripción</li>
    <li>No usamos nuestras propias cookies</li>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>Acerca de</title>
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
  <p class="sub">Noticias Mundiales — Agregador de noticias automatizado</p>
  <p><strong>Noticias Mundiales</strong> es un agregador de noticias que reúne los titulares más importantes de fuentes internacionales confiables en un solo lugar.</p>
  <h2>Cómo funciona</h2>
  <div class="steps">
    <div class="step"><span class="step-num">1</span><span>Los titulares se obtienen automáticamente cada día desde las fuentes configuradas</span></div>
    <div class="step"><span class="step-num">2</span><span>Los titulares irrelevantes se filtran y los duplicados se eliminan automáticamente</span></div>
    <div class="step"><span class="step-num">3</span><span>El sitio muestra el titular y un enlace a la fuente original únicamente</span></div>
    <div class="step"><span class="step-num">4</span><span>El sitio se actualiza automáticamente mediante GitHub Actions cada día</span></div>
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
  </ul>
  <h2>Aviso legal</h2>
  <p>Este sitio es un agregador automático. Todos los artículos enlazan a sus fuentes originales. Consulta la <a href="privacy.html">política de privacidad</a> para detalles sobre publicidad.</p>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>Gizlilik Politikası</title>
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
  <p class="sub">Son güncelleme: 2025</p>
  <p><strong>Dünya Haberleri</strong>'ne hoş geldiniz. Gizliliğinizi korumaya kararlıyız.</p>
  <h2>1. Topladığımız Bilgiler</h2>
  <p>Bu site doğrudan kişisel veri toplamaz. Diğer kaynaklardan haber başlıklarını gösteren bir haber toplayıcısıyız.</p>
  <ul>
    <li>Kayıt veya abonelik gerekmez</li>
    <li>Kendi çerezlerimizi kullanmıyoruz</li>
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
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<title>Hakkımızda</title>
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
  <p class="sub">Dünya Haberleri — Otomatik haber toplayıcısı</p>
  <p>Bu site, Türkiye ve dünyadan birden fazla güvenilir kaynaktan haberleri otomatik olarak toplayan bir <strong>haber toplayıcısıdır</strong>. Her içerik parçası, tam makaleye orijinal kaynağında bağlantı verir.</p>
  <h2>Nasıl Çalışır?</h2>
  <div class="steps">
    <div class="step"><div class="step-num">1</div><div>Otomatik sistem, onlarca güvenilir Türk ve uluslararası haber kaynağını düzenli olarak tarar.</div></div>
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
  </ul>
  <h2>Yasal Uyarı</h2>
  <p>Bu site otomatik bir toplayıcıdır. Tüm makaleler orijinal kaynaklarına bağlantı verir. Reklamlar hakkında ayrıntılar için <a href="privacy.html">Gizlilik Politikası</a>'nı inceleyin.</p>
</div>
<script src="app.js"></script>
</body>
</html>
"""

ROBOTS_TXT = """\
User-agent: *
Allow: /
Disallow: /admin

# Sitemap: https://YOUR-DOMAIN/sitemap.xml
"""


def _make_sw(site_url: str = "") -> str:
    """Generate a minimal Service Worker for PWA offline caching."""
    base = site_url.rstrip("/") or "."
    return f"""// Service Worker — auto-generated
const CACHE = 'news-v1';
const STATIC = [
  '{base}/style.css',
  '{base}/app.js',
];

self.addEventListener('install', e => {{
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)).catch(() => {{}}));
  self.skipWaiting();
}});
self.addEventListener('activate', e => {{
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
  // Cache-first for static assets
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
    """Write CSS, JS, SW and static HTML pages to out_dir."""
    os.makedirs(out_dir, exist_ok=True)

    assets = {
        "style.css":  STYLE_CSS,
        "app.js":     APP_JS,
        "robots.txt": ROBOTS_TXT,
        "sw.js":      _make_sw(site_url),
    }
    for filename, content in assets.items():
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
            f.write(content)

    _privacy_map = {"en": PRIVACY_HTML_EN, "fr": PRIVACY_HTML_FR, "es": PRIVACY_HTML_ES, "tr": PRIVACY_HTML_TR}
    _about_map   = {"en": ABOUT_HTML_EN,   "fr": ABOUT_HTML_FR,   "es": ABOUT_HTML_ES,   "tr": ABOUT_HTML_TR}
    privacy_src  = _privacy_map.get(lang, PRIVACY_HTML)
    about_src    = _about_map.get(lang, ABOUT_HTML)
    for filename, content in [("privacy.html", privacy_src), ("about.html", about_src)]:
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


def _card(art: dict, slug: str) -> str:
    color    = CATEGORY_COLORS.get(slug, DEFAULT_COLOR)
    gradient = CATEGORY_GRADIENTS.get(slug, DEFAULT_GRADIENT)
    title      = esc(" ".join(art["title"].split()))
    url        = safe_url(art["url"])
    source_raw = art["source"]
    source     = esc(SOURCE_AR_NAME.get(source_raw, source_raw))
    date       = esc(art.get("date", ""))
    image      = safe_url(art.get("image", ""))
    if image and image != "#":
        bg_html = (
            f'<div class="card-bg">'
            f'<img class="card-bg-img" src="{image}" alt="" loading="lazy" '
            f'onerror="this.parentElement.parentElement.classList.add(\'card--no-img\')">'
            f'</div>'
        )
        extra_cls = ""
    else:
        bg_html = f'<div class="card-no-img">📰</div>'
        extra_cls = " card--no-img"
    return (
        f'<article class="article-card{extra_cls}" data-cat="{esc(slug)}" data-title="{title}" '
        f'data-source="{source}" data-url="{url}" data-date="{date}" data-color="{esc(color)}">'
        f'<a href="{url}" target="_blank" rel="noopener noreferrer nofollow" class="card-link">'
        f'{bg_html}'
        f'<div class="card-overlay"></div>'
        f'<div class="card-body">'
        f'<div class="card-meta">'
        f'<span class="card-source" style="background:{esc(gradient)}">{source}</span>'
        f'<time class="card-date">{date}</time>'
        f'</div>'
        f'<h3 class="card-title">{title}</h3>'
        f'</div></a></article>'
    )


def _gather_carousel(
    articles_by_cat: dict,
    slugs_order: list[tuple],
    per_slug: int = 4,
    max_total: int = 16,
) -> list[dict]:
    """Build a flat list of carousel-ready article dicts.

    slugs_order: list of (slug, cat_name, cat_icon) tuples in display order.
    Returns up to max_total items with valid images, taking up to per_slug per slug.
    """
    result: list[dict] = []
    for slug, cat_name, cat_icon in slugs_order:
        cat_data = articles_by_cat.get(slug)
        if not cat_data:
            continue
        count = 0
        for art in cat_data["articles"]:
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


def _carousel(articles: list[dict], max_items: int = 12, s: dict = STRINGS["ar"]) -> str:
    """Hero + sidebar carousel (Hespress/MSN style).

    Main panel: one large slide at a time, auto-advances every 5.5 s,
    crossfade transition, Ken-Burns zoom, progress bar, dot indicators,
    prev/next arrows, touch swipe.
    Sidebar: first 4 articles after the hero as static article links.
    """
    items = [a for a in articles if a.get("image", "").startswith("http")][:max_items]
    if len(items) < 3:
        return ""

    # ── slides (all items cycle in the hero) ─────────────────────────────────
    slides_html = ""
    dots_html   = ""
    for i, art in enumerate(items):
        gradient = CATEGORY_GRADIENTS.get(art["slug"], DEFAULT_GRADIENT)
        title    = esc(" ".join(art["title"].split()))
        url      = safe_url(art["url"])
        image    = safe_url(art["image"])
        source   = esc(SOURCE_AR_NAME.get(art["source"], art["source"]))
        date     = esc(art.get("date", ""))
        cat_name = esc(art["cat_name"])
        cat_icon = esc(art["cat_icon"])
        active   = " active" if i == 0 else ""
        loading  = "eager" if i == 0 else "lazy"
        slides_html += (
            f'<div class="nh-slide{active}" data-idx="{i}">'
            f'<a href="{url}" target="_blank" rel="noopener noreferrer nofollow">'
            f'<img src="{image}" alt="{title}" class="nh-img" loading="{loading}" '
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
        url      = safe_url(art["url"])
        image    = safe_url(art["image"])
        source   = esc(SOURCE_AR_NAME.get(art["source"], art["source"]))
        date     = esc(art.get("date", ""))
        cat_name = esc(art["cat_name"])
        cat_icon = esc(art["cat_icon"])
        side_html += (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer nofollow" class="nh-side-item">'
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
                  s: dict = STRINGS["ar"]) -> str:
    """Horizontal world-regions strip — sticky inside .sticky-header on index + world + region pages."""
    if not world_regions:
        return ""
    buttons = ""
    for r in world_regions:
        active_cls = " active-region" if r["slug"] == active_slug else ""
        buttons += (
            f'<a href="{esc(r["slug"])}.html" class="world-region-btn{active_cls}">'
            f'{esc(r["icon"])} {esc(r["name"])}'
            f'</a>'
        )
    return (
        f'<div class="world-subnav" aria-label="{esc(s["world_regions_label"])}">'
        f'<div class="world-subnav-inner">{buttons}</div>'
        f'</div>'
    )


def _media_subnav(active_slug: str = "", media_regions: list = MEDIA_REGIONS,
                  s: dict = STRINGS["ar"]) -> str:
    """Horizontal media-regions strip for صوت وصورة and vid-* pages."""
    if not media_regions:
        return ""
    buttons = ""
    for r in media_regions:
        active_cls = " active-region" if r["slug"] == active_slug else ""
        buttons += (
            f'<a href="{esc(r["slug"])}.html" class="world-region-btn{active_cls}">'
            f'{esc(r["icon"])} {esc(r["name"])}'
            f'</a>'
        )
    return (
        f'<div class="world-subnav" aria-label="{esc(s.get("media_regions_label", "صوت وصورة"))}">'
        f'<div class="world-subnav-inner">{buttons}</div>'
        f'</div>'
    )


def _nav(categories: list, articles_by_cat: dict, active: str = "home",
         s: dict = STRINGS["ar"], region_slugs: set = REGION_SLUGS,
         has_world: bool = True, media_slugs: set = MEDIA_SLUGS,
         has_media: bool = True) -> str:
    home_cls = "nav-tab active" if active == "home" else "nav-tab"
    html = f'<a href="index.html" class="{home_cls}" data-cat="all">{s["home"]}</a>\n'

    for cat in categories:
        slug = cat["slug"]
        if slug in region_slugs or slug in media_slugs:
            continue  # regions/media live in subnav, not main nav
        cls = "nav-tab active" if active == slug else "nav-tab"
        html += (
            f'<a href="{esc(slug)}.html" class="{cls}" data-cat="{esc(slug)}">'
            f'{esc(cat.get("icon",""))} {esc(cat["name"])}</a>\n'
        )

    # Show media tab when either world_regions or media_regions are configured
    if has_world or has_media:
        media_active = active in media_slugs or active == "media"
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
    <li><a href="about.html" class="cat-link" style="border-inline-start-color:#64748b">{s["about"]}</a></li>
    <li><a href="privacy.html" class="cat-link" style="border-inline-start-color:#64748b">{s["privacy"]}</a></li>
  </ul>
</div>
<div class="sidebar-widget">
  <h3 class="widget-title">{s["ad"]}</h3>
  <div class="ad-slot ad-slot-sidebar"><!-- Google AdSense --></div>
</div>"""


def _page(*, title: str, desc: str, nav_html: str,
          main_html: str, footer_cats: str,
          today_ar: str, now: str, total_articles: int, total_sources: int,
          world_subnav_html: str = "", ticker_html: str = "",
          lang_switcher_html: str = "",
          canonical: str = "", carousel_html: str = "",
          rss_url: str = "rss.xml", s: dict) -> str:
    sd = json.dumps({
        "@context": "https://schema.org", "@type": "WebSite",
        "name": title, "description": desc, "inLanguage": s["in_language"],
    }, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="{s["lang"]}" dir="{s["dir"]}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="index, follow">
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(desc)}">
  <meta property="og:title" content="{esc(title)}">
  <meta property="og:description" content="{esc(desc)}">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="{s["og_locale"]}">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="{esc(title)}">
  <link rel="canonical" href="{esc(canonical)}">
  <link rel="manifest" href="manifest.json">
  <meta name="theme-color" content="{esc(s.get("theme_color","#1d4ed8"))}">
  <link rel="alternate" type="application/rss+xml" title="{esc(title)}" href="{esc(rss_url)}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="{esc(s["font_url"])}" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
  <script type="application/ld+json">{sd}</script>
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
          {lang_switcher_html}
          <button id="theme-toggle" class="theme-btn" aria-label="{s["theme_btn_label"]}">🌙</button>
          <button id="search-toggle" class="theme-btn" aria-label="{s.get("search_label","Search")}" aria-expanded="false">🔍</button>
        </div>
      </div>
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
        <h4>{s["footer_links"]}</h4>
        <ul>
          <li><a href="index.html">{s["home_bare"]}</a></li>
          <li><a href="about.html">{s["about"]}</a></li>
          <li><a href="privacy.html">{s["privacy"]}</a></li>
        </ul>
      </div>
      <div class="footer-section">
        <h4>{s.get("rss_feeds","RSS")}</h4>
        <ul>
          <li><a href="{esc(rss_url)}" type="application/rss+xml">📡 {s.get("rss_all","All news")}</a></li>
        </ul>
      </div>
    </div>
    <div class="footer-bottom">
      <p><a href="privacy.html">{s["privacy"]}</a> · <a href="about.html">{s["about"]}</a> · <a href="{esc(rss_url)}" type="application/rss+xml">RSS</a></p>
    </div>
  </footer>
  <script src="app.js"></script>
</body>
</html>"""


def _write(filename: str, content: str, out_dir: str = OUTPUT_DIR) -> None:
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
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
    common = dict(
        desc=site_desc, footer_cats=footer_cats, today_ar=today_ar, now=now,
        total_articles=total_articles, total_sources=total_sources, s=s,
    )

    # ── Language switcher helper for this build ───────────────────────────────
    def _lsw(page_file: str) -> str:
        return _lang_switcher(lang, page_file)

    # ── World subnav — reused on index + world pages ─────────────────────────
    world_subnav = _world_subnav(world_regions=world_regions, s=s)

    # Pre-build category lookup: slug → (cat_name, cat_icon)
    cat_meta: dict[str, tuple[str, str]] = {
        c["slug"]: (c["name"], c.get("icon", ""))
        for c in categories
    }

    # ── INDEX PAGE — preview (PREVIEW_PER_CAT articles per category) ─────────
    home_sections = ""
    for cat in categories:
        slug     = cat["slug"]
        if slug in region_slugs or slug in media_slugs_local:
            continue  # regions/media shown in subnav / world.html / media.html, not home
        cat_data = articles_by_cat.get(slug)
        if not cat_data or not cat_data["articles"]:
            continue
        color   = CATEGORY_COLORS.get(slug, DEFAULT_COLOR)
        preview = cat_data["articles"][:PREVIEW_PER_CAT]
        cards   = "".join(_card(a, slug) for a in preview)
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
            f'<h2 class="section-title">{esc(cat["name"])}</h2>'
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
    home_carousel = _carousel(_gather_carousel(
        articles_by_cat,
        [(c["slug"], c["name"], c.get("icon", ""))
         for c in categories if c["slug"] not in region_slugs and c["slug"] not in media_slugs_local],
        per_slug=3,
    ), s=s)
    _wrt("index.html", _page(
        title=site_title,
        nav_html=_nav(categories, articles_by_cat, active="home",
                      s=s, region_slugs=region_slugs, has_world=has_world,
                      media_slugs=media_slugs_local),
        main_html=home_sections,
        world_subnav_html=world_subnav,
        carousel_html=home_carousel,
        lang_switcher_html=_lsw("index.html"),
        **common,
    ))

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
        if cat_data and cat_data["articles"]:
            cards      = "".join(_card(a, slug) for a in cat_data["articles"])
            grid       = f'<div class="articles-grid">{cards}</div>'
            src_filter = _source_filter_strip(
                cat_data["articles"], cat.get("sources", []), color, s
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
        cat_carousel = _carousel(_gather_carousel(
            articles_by_cat,
            [(slug, cat["name"], cat.get("icon", ""))],
            per_slug=16,
        ), s=s)
        # Economy tabs widget on economy, business, and travel pages
        if slug in {"economy", "business", "travel"}:
            cat_ticker = _economy_widget(s, active_tab=slug)
        else:
            cat_ticker = ""
        # RSS link: category-specific feed when available
        cat_rss = f"rss-{slug}.xml" if slug in articles_by_cat else "rss.xml"
        _wrt(f"{slug}.html", _page(
            title=cat_title,
            nav_html=_nav(categories, articles_by_cat, active=slug,
                          s=s, region_slugs=region_slugs, has_world=has_world,
                          media_slugs=media_slugs_local, has_media=has_media),
            main_html=cat_section,
            canonical=f"{slug}.html",
            world_subnav_html=page_world_subnav,
            ticker_html=cat_ticker,
            carousel_html=cat_carousel,
            rss_url=cat_rss,
            lang_switcher_html=_lsw(f"{slug}.html"),
            **common,
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
                canonical="prices.html",
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
                cards    = "".join(_card(a, slug) for a in preview)
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
        ), s=s)
        _wrt("world.html", _page(
            title=site_title,
            nav_html=_nav(categories, articles_by_cat, active="world",
                          s=s, region_slugs=region_slugs, has_world=has_world,
                          media_slugs=media_slugs_local, has_media=has_media),
            main_html=world_sections,
            world_subnav_html=_world_subnav(world_regions=world_regions, s=s),
            canonical="world.html",
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

            if cat_data and cat_data["articles"]:
                preview  = cat_data["articles"][:PREVIEW_PER_CAT]
                cards    = "".join(_card(a, slug) for a in preview)
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
        ), s=s)
        _wrt("media.html", _page(
            title=site_title,
            nav_html=_nav(categories, articles_by_cat, active="media",
                          s=s, region_slugs=region_slugs, has_world=has_world,
                          media_slugs=media_slugs_local, has_media=has_media),
            main_html=media_sections,
            world_subnav_html=_media_subnav(media_regions=media_regions_list, s=s),
            canonical="media.html",
            carousel_html=media_carousel,
            lang_switcher_html=_lsw("media.html"),
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
        _sitemap_pages = ["index.html", "about.html", "privacy.html"]
        for cat in categories:
            _slug = cat.get("slug", "")
            if _slug:
                _sitemap_pages.append(f"{_slug}.html")
        if has_world:
            _sitemap_pages.append("world.html")
            for r in world_regions:
                _sitemap_pages.append(f'{r["slug"]}.html')
        if has_media:
            _sitemap_pages.append("media.html")
            for r in media_regions_list:
                _sitemap_pages.append(f'{r["slug"]}.html')
        if any(cat.get("slug") == "economy" for cat in categories):
            _sitemap_pages.append("prices.html")

        _today = datetime.now().strftime("%Y-%m-%d")
        _urls = "\n".join(
            f"  <url><loc>{_base}/{p}</loc><lastmod>{_today}</lastmod>"
            f"<changefreq>hourly</changefreq><priority>0.8</priority></url>"
            for p in _sitemap_pages
        )
        _sitemap_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'{_urls}\n'
            '</urlset>\n'
        )
        _wrt("sitemap.xml", _sitemap_xml)

        # Update robots.txt with the absolute sitemap URL
        _robots = (
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /admin\n\n"
            f"Sitemap: {_base}/sitemap.xml\n"
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
