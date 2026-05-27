import json
import os
from copy import deepcopy

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "sources.json")

DEFAULT_CONFIG = {
    "categories": [
        {
            "name": "سياسة",
            "slug": "politics",
            "icon": "🏛️",
            "sources": [
                {
                    "name": "الجزيرة نت",
                    "url": "https://www.aljazeera.net",
                    "selectors": {
                        "article_selector": "article.gc__content, .article-card, .card",
                        "heading_tags": ["h1", "h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner", "ad", "advertisement"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 15,
                    },
                },
                {
                    "name": "هسبريس",
                    "url": "https://www.hespress.com",
                    "selectors": {
                        "article_selector": "article, .post, .article",
                        "heading_tags": ["h1", "h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
                {
                    "name": "هوية بريس",
                    "url": "https://howiyapress.com",
                    "selectors": {
                        "article_selector": "article, .post, .article, .entry",
                        "heading_tags": ["h1", "h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
                {
                    "name": "شوف تيفي",
                    "url": "https://chouftv.ma",
                    "selectors": {
                        "article_selector": "article, .post, .article, .news-box",
                        "heading_tags": ["h1", "h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
                {
                    "name": "اليوم 24",
                    "url": "https://alyaoum24.com",
                    "selectors": {
                        "article_selector": "article, .post, .article, .entry",
                        "heading_tags": ["h1", "h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
                {
                    "name": "بي بي سي عربي",
                    "url": "https://www.bbc.com/arabic",
                    "selectors": {
                        "article_selector": "article, .lx-stream__post, .gc__content, .bbc-1cvxiy9",
                        "heading_tags": ["h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "navigation", "orb-nav", "orb-footer"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar", "orbit", "orb"],
                        "min_title_length": 20,
                    },
                },
            ],
        },
        {
            "name": "اقتصاد",
            "slug": "economy",
            "icon": "💰",
            "sources": [
                {
                    "name": "العربية",
                    "url": "https://www.alarabiya.net",
                    "selectors": {
                        "article_selector": "article, .article-card, .news-item",
                        "heading_tags": ["h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
                {
                    "name": "سكاي نيوز عربية",
                    "url": "https://www.skynewsarabia.com",
                    "selectors": {
                        "article_selector": "article, .news-item, .post-item",
                        "heading_tags": ["h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
            ],
        },
        {
            "name": "تكنولوجيا",
            "slug": "tech",
            "icon": "💻",
            "sources": [
                {
                    "name": "TechRadar",
                    "url": "https://www.techradar.com/news",
                    "selectors": {
                        "article_selector": "article, .listingResult, .news-article",
                        "heading_tags": ["h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner", "deals"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
                {
                    "name": "Wired",
                    "url": "https://www.wired.com",
                    "selectors": {
                        "article_selector": "article, .summary-item, .card",
                        "heading_tags": ["h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner", "advertisement"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
            ],
        },
        {
            "name": "رياضة",
            "slug": "sports",
            "icon": "⚽",
            "sources": [
                {
                    "name": "كورة",
                    "url": "https://www.kooora.com",
                    "selectors": {
                        "article_selector": "article, .news-item, .post",
                        "heading_tags": ["h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
                {
                    "name": "يلا كورة",
                    "url": "https://www.yallakora.com",
                    "selectors": {
                        "article_selector": "article, .news-item, .post",
                        "heading_tags": ["h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
            ],
        },
        {
            "name": "صحة وعلوم",
            "slug": "health",
            "icon": "🔬",
            "sources": [
                {
                    "name": "WebMD",
                    "url": "https://www.webmd.com/news",
                    "selectors": {
                        "article_selector": "article, .article-feed-item, .news-item",
                        "heading_tags": ["h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
                {
                    "name": "Nature",
                    "url": "https://www.nature.com/news",
                    "selectors": {
                        "article_selector": "article, .c-article-item, .app-article-list-row",
                        "heading_tags": ["h2", "h3"],
                        "exclude_classes": ["footer", "nav", "menu", "header", "sidebar", "widget", "banner"],
                        "exclude_id_patterns": ["footer", "nav", "menu", "header", "sidebar"],
                        "min_title_length": 20,
                    },
                },
            ],
        },
    ],
    "settings": {
        "max_articles_per_source": 10,
        "oldest_days": 7,
        "output_file": "static/index.html",
        "site_title": "ملخص الأخبار الأسبوعي",
        "site_description": "أهم العناوين من مصادر متعددة في مكان واحد",
    },
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def reset_config():
    save_config(deepcopy(DEFAULT_CONFIG))
