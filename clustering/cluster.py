"""
Story Clustering — TF-IDF cosine similarity.

Groups articles about the same event from different sources.
Runs at build time; output is data/clusters_{lang}.json.

Output format:
  { url: {"cluster_id": "abc12345", "source_count": 3, "sources": ["BBC", "Reuters", ...]} }
"""

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
from collections import Counter, defaultdict

logger = logging.getLogger("clustering")

# Tuning parameters
SIMILARITY_THRESHOLD  = 0.32   # cosine similarity floor to link two articles
MIN_DISTINCT_SOURCES  = 2      # cluster must have ≥ 2 different sources
MAX_DF_RATIO          = 0.70   # ignore tokens appearing in > 70% of category articles

# Arabic stop-words (very common function words — useless for similarity)
_STOP_AR = frozenset({
    "في", "من", "إلى", "على", "عن", "مع", "هذا", "هذه", "هذان", "هؤلاء",
    "التي", "الذي", "الذين", "اللذين", "اللتان", "وهو", "وهي", "كان",
    "كانت", "تم", "يتم", "بعد", "قبل", "عند", "حين", "منذ", "خلال",
    "حول", "بين", "أمام", "لكن", "لأن", "حتى", "إذا", "إذ", "كما",
    "أيضا", "أيضاً", "وفي", "وعلى", "ومن", "وإلى", "بما", "فيما",
    "وما", "مما", "وأن", "المزيد", "اقرأ", "للاطلاع", "تفاصيل",
    "عاجل", "خاص", "جديد", "جديدة", "حول",
})

# English / French / Spanish / Turkish stop-words
_STOP_LATIN = frozenset({
    "the", "and", "for", "that", "this", "with", "are", "was", "were",
    "from", "have", "has", "been", "will", "not", "they", "their", "its",
    "new", "but", "more", "also", "can", "who", "his", "her", "which",
    "what", "how", "all", "says", "said", "over", "into", "after", "about",
    "out", "than", "when", "just", "two", "three", "breaking", "update",
    # French
    "les", "des", "une", "dans", "sur", "avec", "par", "pour", "est",
    "qui", "que", "pas", "son", "plus", "ses", "aux", "comme", "ces",
    "leur", "dit", "lors", "selon", "après", "avant", "entre",
    # Spanish
    "los", "las", "del", "por", "con", "que", "una", "sus", "han", "este",
    "esta", "son", "fue", "como", "más", "pero", "cuando", "entre",
    # Turkish
    "bir", "ve", "ile", "için", "bu", "den", "dan", "nin", "nın", "nun",
    "nün", "lar", "ler", "daki", "deki", "taki", "teki", "ama", "veya",
})


def _tokenize(text: str) -> list[str]:
    """Extract meaningful tokens from title text."""
    text = text.lower()
    # Match Arabic word chars (≥3 chars) OR Latin word chars (≥3 chars)
    raw_tokens = re.findall(r'[؀-ۿ\w]{3,}', text)
    return [
        t for t in raw_tokens
        if t not in _STOP_AR and t not in _STOP_LATIN
    ]


def _build_tfidf(title_list: list[str]) -> list[dict[str, float]]:
    """Compute TF-IDF sparse vectors for a list of title strings."""
    n = len(title_list)
    if n < 2:
        return [{} for _ in title_list]

    tokenized = [_tokenize(t) for t in title_list]

    # Document frequency
    df: Counter = Counter()
    for tokens in tokenized:
        df.update(set(tokens))

    max_df = max(1, int(n * MAX_DF_RATIO))
    # IDF with smoothing: log((N+1)/(df+1)) + 1
    idf = {
        t: math.log((n + 1) / (freq + 1)) + 1.0
        for t, freq in df.items()
        if freq <= max_df
    }

    vectors: list[dict[str, float]] = []
    for tokens in tokenized:
        if not tokens:
            vectors.append({})
            continue
        tf = Counter(tokens)
        total = len(tokens)
        vec = {
            t: (count / total) * idf[t]
            for t, count in tf.items()
            if t in idf
        }
        vectors.append(vec)

    return vectors


def _cosine(v1: dict, v2: dict) -> float:
    """Cosine similarity between two sparse TF-IDF vectors."""
    if not v1 or not v2:
        return 0.0
    common = set(v1) & set(v2)
    if not common:
        return 0.0
    dot  = sum(v1[k] * v2[k] for k in common)
    mag1 = math.sqrt(sum(x * x for x in v1.values()))
    mag2 = math.sqrt(sum(x * x for x in v2.values()))
    return dot / (mag1 * mag2) if mag1 and mag2 else 0.0


def _cluster_indices(articles: list[dict],
                     threshold: float = SIMILARITY_THRESHOLD) -> list[list[int]]:
    """
    Return list of clusters (each = list of article indices in *articles*).
    Uses Union-Find on pairs that exceed the cosine threshold.
    """
    n = len(articles)
    if n < 2:
        return []

    vectors = _build_tfidf([a["title"] for a in articles])

    # Union-Find with path compression
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # O(n²) — fine for typical per-category counts (~50-150 articles)
    for i in range(n):
        if not vectors[i]:
            continue
        for j in range(i + 1, n):
            if not vectors[j]:
                continue
            if _cosine(vectors[i], vectors[j]) >= threshold:
                union(i, j)

    # Collect groups
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    return [idxs for idxs in groups.values() if len(idxs) >= 2]


def build_cluster_map(db_path: str,
                      threshold: float = SIMILARITY_THRESHOLD) -> dict[str, dict]:
    """
    Read articles from *db_path*, cluster per category, return:
      { url: {"cluster_id": str, "source_count": int, "sources": list} }
    Only URLs that are part of a multi-source cluster are included.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT title, url, source_name, category_slug "
            "FROM articles WHERE is_active = 1 "
            "ORDER BY scraped_at DESC"
        ).fetchall()
    finally:
        conn.close()

    # Group by category
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category_slug"]].append({
            "title":  r["title"],
            "url":    r["url"],
            "source": r["source_name"],
        })

    result: dict[str, dict] = {}
    n_clusters = 0

    for slug, arts in by_cat.items():
        if len(arts) < 2:
            continue

        for cluster_idxs in _cluster_indices(arts, threshold):
            cluster_arts = [arts[i] for i in cluster_idxs]

            # Require distinct sources
            sources = list({a["source"] for a in cluster_arts})
            if len(sources) < MIN_DISTINCT_SOURCES:
                continue

            # Stable ID from sorted URLs
            cid = hashlib.md5(
                "|".join(sorted(a["url"] for a in cluster_arts)).encode()
            ).hexdigest()[:8]

            for art in cluster_arts:
                result[art["url"]] = {
                    "cluster_id":   cid,
                    "source_count": len(sources),
                    "sources":      sources,
                }

            n_clusters += 1

    logger.info(
        "Clustering [%s]: %d clusters, %d articles tagged",
        os.path.basename(db_path), n_clusters, len(result),
    )
    return result


def run_clustering(lang: str, db_path: str, out_dir: str) -> dict[str, dict]:
    """
    Cluster articles from *db_path*, save JSON to *out_dir*/clusters_{lang}.json.
    Returns the cluster map so callers can use it without re-reading the file.
    """
    cluster_map = build_cluster_map(db_path)

    out_path = os.path.join(out_dir, f"clusters_{lang}.json")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cluster_map, f, ensure_ascii=False, indent=None)

    print(f"  [{lang.upper()}] {len(cluster_map):4d} articles in clusters "
          f"({out_path})")
    return cluster_map
