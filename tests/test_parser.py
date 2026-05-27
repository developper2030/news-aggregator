import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scraper.scrape import extract_articles_bs4, extract_articles_fallback, _is_junk_title

SAMPLE_HTML = """
<html><body>
<main>
<article>
    <h2><a href="/story1">عنوان الخبر الأول يبلغ طوله أكثر من عشرين حرفا</a></h2>
</article>
<article>
    <h2><a href="/story2">خبر ثاني طويل بما فيه الكفاية لاجتياز الفلتر</a></h2>
</article>
<div class="card">
    <h3><a href="/story3">هذا خبر ثالث من بطاقة مختلف بطول مناسب</a></h3>
</div>
</main>
<a href="/short">قصير</a>
</body></html>
"""


def test_extract_articles_bs4():
    selectors = {
        "article_selector": "main article, .card",
        "heading_tags": ["h2", "h3"],
        "exclude_classes": ["footer", "nav", "menu"],
        "exclude_id_patterns": ["footer", "nav"],
        "min_title_length": 12,
    }
    arts = extract_articles_bs4(SAMPLE_HTML, "https://example.com", "TestSource", 5, selectors)
    assert len(arts) == 3, f"Expected 3 articles, got {len(arts)}"
    for a in arts:
        assert "title" in a
        assert "url" in a
        assert "source" in a
        assert len(a["title"]) >= 10


def test_extract_articles_bs4_respects_max():
    selectors = {
        "heading_tags": ["h2", "h3"],
        "exclude_classes": [],
        "exclude_id_patterns": [],
        "min_title_length": 12,
    }
    arts = extract_articles_bs4(SAMPLE_HTML, "https://example.com", "TestSource", 2, selectors)
    assert len(arts) == 2, f"Expected 2 articles, got {len(arts)}"


def test_extract_articles_fallback():
    html = """
    <html><body>
    <a href="/long1">هذا رابط طويل بما يكفي ليكون خبرا مناسبا للاختبار</a>
    <a href="/long2">هذا رابط طويل ثاني يكفي لاجتياز فلتر الطول الأدنى</a>
    <a href="#local">محلي</a>
    </body></html>
    """
    arts = extract_articles_fallback(html, "https://example.com", "TestSource", 5)
    assert len(arts) == 2, f"Expected 2 articles, got {len(arts)}"


def test_extract_articles_duplicates():
    html = """
    <html><body>
    <article><h2><a href="/dup">هذا خبر مكرر مع طول مناسب لاجتياز الاختبار</a></h2></article>
    <div><a href="/dup">هذا خبر مكرر مع طول مناسب لاجتياز الاختبار</a></div>
    </body></html>
    """
    arts = extract_articles_bs4(html, "https://example.com", "TestSource", 5)
    assert len(arts) == 1, f"Expected 1 article (dedup), got {len(arts)}"


def test_empty_html():
    arts = extract_articles_bs4("<html></html>", "https://example.com", "TestSource", 5)
    assert arts == [], "Expected empty list"


def test_junk_title_filter():
    assert _is_junk_title("Sign in")
    assert _is_junk_title("Login now")
    assert _is_junk_title("{{promoBar.promoMessage}}")
    assert _is_junk_title("privacy policy")
    assert _is_junk_title("Terms & Conditions")
    assert _is_junk_title(".css-v2kfba{height:100%}")
    assert not _is_junk_title("ترامب يصل الصين في زيارة نادرة")
    assert not _is_junk_title("علماء يكتشفون علاجا جديدا للسرطان")
