import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "news.db")


def set_db_path(path: str) -> None:
    """Override the active database path (e.g. for a second language pipeline)."""
    global DB_PATH
    DB_PATH = os.path.abspath(path)


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db() -> None:
    schema = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    conn = get_connection()
    with open(schema, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    # migrate: add image_url if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
    if "image_url" not in cols:
        conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT DEFAULT ''")
    conn.commit()
    conn.close()


def save_article(title: str, url: str, source_name: str, category_name: str, category_slug: str, image_url: str = "") -> None:
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO articles
               (title, url, image_url, source_name, category_name, category_slug)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, url, image_url, source_name, category_name, category_slug),
        )
        conn.commit()
    finally:
        conn.close()


def save_articles_batch(articles: list[dict]) -> int:
    """Insert many articles in one transaction. Returns number of rows inserted."""
    if not articles:
        return 0
    conn = get_connection()
    try:
        cur = conn.executemany(
            """INSERT OR IGNORE INTO articles
               (title, url, image_url, source_name, category_name, category_slug)
               VALUES (:title, :url, :image_url, :source, :category_name, :category_slug)""",
            articles,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def get_articles_by_category(days: int = 7) -> dict:
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        """SELECT * FROM articles
           WHERE scraped_at >= ? AND is_active = 1
           ORDER BY category_slug, scraped_at DESC""",
        (cutoff,),
    ).fetchall()
    conn.close()

    grouped: dict = {}
    for row in rows:
        slug = row["category_slug"]
        if slug not in grouped:
            grouped[slug] = {"name": row["category_name"], "articles": []}
        grouped[slug]["articles"].append({
            "title":  row["title"],
            "url":    row["url"],
            "image":  row["image_url"] or "",
            "source": row["source_name"],
            "date":   row["scraped_at"][:10],
        })
    return grouped


def clean_old_articles(days: int = 30) -> int:
    """Delete articles older than *days*. Returns number of rows deleted."""
    conn = get_connection()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute("DELETE FROM articles WHERE scraped_at < ?", (cutoff,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return deleted
