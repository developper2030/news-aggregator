import csv
import glob as _glob
import hmac
import io
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE    = os.path.dirname(os.path.abspath(__file__))
PYTHON  = sys.executable or "python"
sys.path.insert(0, BASE)

from config.loader import load_config, save_config, reset_config
from database.db   import get_connection as _db_conn, clean_old_articles, DB_PATH

BLACKLIST_PATH = os.path.join(BASE, "config", "blacklist.json")

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("admin")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "newsadmin123")
_sessions: dict = {}
SESSION_TTL = 4 * 3600


# ── session helpers ──────────────────────────────────────────────────────────
def _new_session() -> str:
    sid = os.urandom(20).hex()
    _sessions[sid] = time.time() + SESSION_TTL
    return sid

def _purge_expired() -> None:
    for k in [k for k, v in _sessions.items() if v < time.time()]:
        del _sessions[k]

def _valid_session(cookie_header: str) -> bool:
    _purge_expired()
    for part in cookie_header.split(";"):
        k, _, v = part.strip().partition("=")
        if k.strip() == "sid":
            return v.strip() in _sessions
    return False


# ── DB helpers ───────────────────────────────────────────────────────────────
def _db_stats() -> dict:
    if not os.path.exists(DB_PATH):
        return {"total": 0, "by_cat": [], "oldest": "", "newest": "", "db_size_kb": 0, "total_sources": 0}
    conn   = _db_conn()
    total  = conn.execute("SELECT COUNT(*) FROM articles WHERE is_active=1").fetchone()[0]
    by_cat = conn.execute("""
        SELECT category_slug, category_name, COUNT(*) cnt
        FROM articles WHERE is_active=1
        GROUP BY category_slug ORDER BY cnt DESC
    """).fetchall()
    oldest = conn.execute("SELECT MIN(scraped_at) FROM articles WHERE is_active=1").fetchone()[0] or ""
    newest = conn.execute("SELECT MAX(scraped_at) FROM articles WHERE is_active=1").fetchone()[0] or ""
    conn.close()
    cfg    = load_config()
    nsrc   = sum(len(c.get("sources", [])) for c in cfg.get("categories", []))
    return {
        "total":         total,
        "by_cat":        [{"slug": r[0], "name": r[1], "count": r[2]} for r in by_cat],
        "oldest":        oldest[:10],
        "newest":        newest[:10],
        "db_size_kb":    os.path.getsize(DB_PATH) // 1024,
        "total_sources": nsrc,
    }


def _db_articles(cat: str = "", q: str = "", page: int = 1, limit: int = 25) -> dict:
    if not os.path.exists(DB_PATH):
        return {"items": [], "total": 0, "page": 1, "pages": 1}
    conn   = _db_conn()
    where  = ["is_active=1"]
    params: list = []
    if cat:
        where.append("category_slug=?");              params.append(cat)
    if q:
        where.append("(title LIKE ? OR source_name LIKE ?)"); params.extend([f"%{q}%", f"%{q}%"])
    wc     = " AND ".join(where)
    total  = conn.execute(f"SELECT COUNT(*) FROM articles WHERE {wc}", params).fetchone()[0]
    offset = (page - 1) * limit
    rows   = conn.execute(
        f"SELECT id,title,url,source_name,category_slug,scraped_at "
        f"FROM articles WHERE {wc} ORDER BY scraped_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page":  page,
        "pages": max(1, (total + limit - 1) // limit),
    }


def _db_delete_article(art_id: int) -> bool:
    if not os.path.exists(DB_PATH):
        return False
    conn = _db_conn()
    conn.execute("UPDATE articles SET is_active=0 WHERE id=?", (art_id,))
    conn.commit(); conn.close()
    return True


def _db_export_csv() -> str:
    if not os.path.exists(DB_PATH):
        return "id,title,url,source,category,scraped_at\n"
    conn = _db_conn()
    rows = conn.execute(
        "SELECT id,title,url,source_name,category_name,scraped_at "
        "FROM articles WHERE is_active=1 ORDER BY scraped_at DESC"
    ).fetchall()
    conn.close()
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["id", "title", "url", "source", "category", "scraped_at"])
    for r in rows:
        w.writerow(list(r))
    return buf.getvalue()


# ── blacklist helpers ────────────────────────────────────────────────────────
def _load_blacklist() -> dict:
    if os.path.exists(BLACKLIST_PATH):
        with open(BLACKLIST_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"keywords": []}

def _save_blacklist(data: dict) -> None:
    with open(BLACKLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── health check ─────────────────────────────────────────────────────────────
def _check_health(url: str) -> dict:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return {"ok": True, "status": resp.status, "ms": int((time.time()-t0)*1000)}
    except urllib.error.HTTPError as e:
        ms = int((time.time()-t0)*1000)
        if e.code in (405, 403, 301, 302, 200):
            return {"ok": True, "status": e.code, "ms": ms}
        return {"ok": False, "status": e.code, "ms": ms, "error": str(e)[:80]}
    except Exception as e:
        return {"ok": False, "ms": int((time.time()-t0)*1000), "error": str(e)[:80]}


def _check_all_health(categories: list) -> list:
    results: list = []
    lock = threading.Lock()
    def chk(cat_name: str, src: dict) -> None:
        r = _check_health(src["url"])
        with lock:
            results.append({"cat": cat_name, "name": src["name"], "url": src["url"], **r})
    threads = [
        threading.Thread(target=chk, args=(c["name"], s), daemon=True)
        for c in categories for s in c.get("sources", [])
    ]
    for t in threads: t.start()
    for t in threads: t.join(timeout=12)
    return sorted(results, key=lambda x: (not x.get("ok", False), x.get("name", "")))


# ── source health (all languages) ────────────────────────────────────────────
_LANG_CONFIGS = [
    ("ar", "config/sources.json",    "data/news.db"),
    ("en", "config/sources-en.json", "data/news-en.db"),
    ("fr", "config/sources-fr.json", "data/news-fr.db"),
    ("es", "config/sources-es.json", "data/news-es.db"),
    ("tr", "config/sources-tr.json", "data/news-tr.db"),
]

def _source_health_all() -> dict:
    """Cross-reference all sources*.json with all DBs → per-source article counts."""
    results: list = []
    for lang, cfg_rel, db_rel in _LANG_CONFIGS:
        cfg_path = os.path.join(BASE, cfg_rel)
        db_path  = os.path.join(BASE, db_rel)
        if not os.path.exists(cfg_path):
            continue
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg_data = json.load(f)
        except Exception:
            continue
        # collect per-source stats from DB
        db_stats: dict = {}
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect(db_path)
                rows = conn.execute("""
                    SELECT source_name, COUNT(*) as cnt, MAX(scraped_at) as last
                    FROM articles
                    WHERE is_active=1
                      AND datetime(scraped_at) >= datetime('now','-7 days')
                    GROUP BY source_name
                """).fetchall()
                conn.close()
                for row in rows:
                    db_stats[row[0]] = {"count": row[1], "last": (row[2] or "")[:10]}
            except Exception:
                pass
        for cat in cfg_data.get("categories", []):
            slug = cat.get("slug", "")
            for src in cat.get("sources", []):
                name  = src.get("name", "")
                stats = db_stats.get(name, {"count": 0, "last": ""})
                results.append({
                    "lang":  lang,
                    "cat":   cat.get("name", ""),
                    "slug":  slug,
                    "name":  name,
                    "url":   src.get("url", ""),
                    "count": stats["count"],
                    "last":  stats["last"],
                })
    # sort: zero-count first, then ascending count
    results.sort(key=lambda x: (x["count"] > 0, x["count"]))
    total = len(results)
    zero  = sum(1 for r in results if r["count"] == 0)
    low   = sum(1 for r in results if 0 < r["count"] < 5)
    ok    = sum(1 for r in results if r["count"] >= 5)
    return {"sources": results, "total": total, "zero": zero, "low": low, "ok": ok}


# ── HTTP handler ──────────────────────────────────────────────────────────────
class AdminHandler(BaseHTTPRequestHandler):

    def _is_auth(self) -> bool:
        return _valid_session(self.headers.get("Cookie", ""))

    def _require_auth(self) -> bool:
        if self._is_auth(): return True
        self._json({"ok": False, "error": "Unauthorized"}, 401)
        return False

    # ── GET ───────────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        if path == "/":
            self._html(ADMIN_HTML)
        elif path == "/api/config":
            if not self._require_auth(): return
            self._json(load_config())
        elif path == "/api/stats":
            if not self._require_auth(): return
            self._json(_db_stats())
        elif path == "/api/articles":
            if not self._require_auth(): return
            self._json(_db_articles(
                cat   = qs.get("cat",   [""])[0],
                q     = qs.get("q",     [""])[0],
                page  = int(qs.get("page",  ["1"])[0]),
                limit = int(qs.get("limit", ["25"])[0]),
            ))
        elif path == "/api/blacklist":
            if not self._require_auth(): return
            self._json(_load_blacklist())
        elif path == "/api/db/export":
            if not self._require_auth(): return
            data = _db_export_csv().encode("utf-8-sig")
            self.send_response(200)
            self.send_header("Content-Type",        "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="articles.csv"')
            self.send_header("Content-Length",      str(len(data)))
            self.end_headers(); self.wfile.write(data)
        elif path == "/api/export/config":
            if not self._require_auth(): return
            data = json.dumps(load_config(), ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type",        "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="sources.json"')
            self.send_header("Content-Length",      str(len(data)))
            self.end_headers(); self.wfile.write(data)
        elif path == "/api/run":
            if not self._require_auth(): return
            self._exec("run.py", "Pipeline finished")
        elif path == "/api/scrape":
            if not self._require_auth(): return
            self._exec("run.py", "Scraping done", ["--scrape-only"])
        elif path == "/api/generate":
            if not self._require_auth(): return
            self._exec("run.py", "Site generated", ["--generate-only"])
        elif path == "/api/source-health":
            if not self._require_auth(): return
            self._json(_source_health_all())
        elif path.startswith("/static/"):
            self._static(path.lstrip("/"))
        else:
            self.send_error(404)

    # ── POST ──────────────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/login":
            pwd = body.get("password", "")
            if hmac.compare_digest(str(pwd), ADMIN_PASSWORD):
                sid = _new_session()
                payload = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type",   "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Set-Cookie", f"sid={sid}; Path=/; HttpOnly; SameSite=Strict")
                self.end_headers(); self.wfile.write(payload)
                logger.info("Login successful")
            else:
                logger.warning("Failed login attempt")
                self._json({"ok": False, "error": "كلمة المرور غير صحيحة"}, 401)
            return

        if not self._require_auth(): return

        if path == "/api/config":
            if not isinstance(body, dict) or "categories" not in body:
                self._json({"ok": False, "error": "Invalid config"}, 400); return
            save_config(body); self._json({"ok": True})
        elif path == "/api/config/reset":
            reset_config(); self._json({"ok": True, "msg": "Reset to defaults"})
        elif path == "/api/logout":
            for part in self.headers.get("Cookie", "").split(";"):
                k, _, v = part.strip().partition("=")
                if k.strip() == "sid": _sessions.pop(v.strip(), None)
            self._json({"ok": True})
        elif path == "/api/article/delete":
            art_id = body.get("id")
            if not isinstance(art_id, int):
                self._json({"ok": False, "error": "Invalid id"}, 400); return
            _db_delete_article(art_id); self._json({"ok": True})
        elif path == "/api/health":
            url = body.get("url")
            if url:
                r = _check_health(url)
                self._json({"ok": True, "results": [{**r, "url": url, "name": url}]})
            else:
                cfg = load_config()
                results = _check_all_health(cfg.get("categories", []))
                ok_count = sum(1 for r in results if r.get("ok"))
                self._json({"ok": True, "results": results,
                            "summary": f"{ok_count}/{len(results)} مصدر يعمل"})
        elif path == "/api/blacklist":
            if not isinstance(body, dict) or "keywords" not in body:
                self._json({"ok": False, "error": "Invalid"}, 400); return
            _save_blacklist(body); self._json({"ok": True})
        elif path == "/api/db/cleanup":
            days    = int(body.get("days", 30))
            deleted = clean_old_articles(days)
            self._json({"ok": True, "deleted": deleted})
        elif path == "/api/import/config":
            if not isinstance(body, dict) or "categories" not in body:
                self._json({"ok": False, "error": "ملف غير صالح"}, 400); return
            save_config(body); self._json({"ok": True, "msg": "تم الاستيراد"})
        else:
            self.send_error(404)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length).decode("utf-8", errors="replace") if length else "{}"
        try:   return json.loads(raw) if raw.strip() else {}
        except: return {}

    def _html(self, text: str):
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type",   "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control",  "no-store")
        self.end_headers(); self.wfile.write(data)

    def _json(self, obj: dict, status: int = 200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def _exec(self, script: str, msg: str, args: list = []):
        script_path = os.path.normpath(os.path.join(BASE, script))
        real_base   = os.path.realpath(BASE)
        real_script = os.path.realpath(script_path)
        if not real_script.startswith(real_base + os.sep):
            self._json({"ok": False, "error": "Invalid path"}, 403); return
        if not os.path.isfile(real_script):
            self._json({"ok": False, "error": f"Not found: {script}"}, 404); return
        try:
            result = subprocess.run(
                [PYTHON, real_script] + args, capture_output=True, text=True,
                timeout=300, cwd=BASE, encoding="utf-8", errors="replace",
            )
            self._json({
                "ok": result.returncode == 0, "msg": msg,
                "stdout": result.stdout[-3000:], "stderr": result.stderr[-1000:],
                "returncode": result.returncode,
            })
        except subprocess.TimeoutExpired:
            self._json({"ok": False, "error": "Timed out after 3 minutes"})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)})

    def _static(self, path: str):
        safe = os.path.normpath(path)
        if safe.startswith("..") or os.path.isabs(safe):
            self.send_error(403); return
        fp = os.path.join(BASE, safe)
        if not os.path.realpath(fp).startswith(os.path.realpath(BASE) + os.sep):
            self.send_error(403); return
        if not os.path.isfile(fp):
            self.send_error(404); return
        ct = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
              ".js": "application/javascript; charset=utf-8"}.get(
              os.path.splitext(fp)[1].lower(), "application/octet-stream")
        with open(fp, "rb") as f: data = f.read()
        self.send_response(200)
        self.send_header("Content-Type",   ct)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def log_message(self, fmt, *args):
        logger.debug("[Admin] " + fmt, *args)


# ═════════════════════════════════════════════════════════════════════════════
ADMIN_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>لوحة التحكم</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI',Tahoma,sans-serif;background:#f8fafc;color:#1e293b;min-height:100vh;font-size:14px;font-weight:500}
a{color:inherit;text-decoration:none}

/* ── LOGIN ────────────────────────────────────────────────────────────────── */
.overlay{position:fixed;inset:0;background:#f8fafc;display:flex;align-items:center;justify-content:center;z-index:9999}
.login-box{background:#ffffff;border:1px solid #cbd5e1;border-radius:16px;padding:40px;width:360px;text-align:center;box-shadow:0 20px 60px rgba(0,0,0,.08)}
.login-box h2{font-size:1.4em;margin-bottom:5px;color:#1e293b;font-weight:700}
.login-box p{color:#64748b;font-size:.85em;margin-bottom:22px}
.login-box input{width:100%;padding:12px 16px;border-radius:8px;border:1px solid #cbd5e1;background:#f8fafc;color:#1e293b;font-size:.95em;font-family:inherit;margin-bottom:10px;text-align:center;outline:none;direction:ltr;font-weight:500}
.login-box input:focus{border-color:#3b82f6}
.login-box button{width:100%;padding:12px;border:none;border-radius:8px;background:linear-gradient(135deg,#3b82f6,#6366f1);color:#fff;font-size:.95em;cursor:pointer;font-family:inherit;transition:.2s;font-weight:700}
.login-box button:hover{filter:brightness(1.1)}
.login-box button:disabled{opacity:.5;cursor:default}
.err{color:#dc2626;font-size:.82em;margin-top:8px;min-height:16px;font-weight:600}

/* ── SHELL ────────────────────────────────────────────────────────────────── */
#main{display:none}
.topbar{background:#ffffff;border-bottom:1px solid #e2e8f0;padding:12px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.topbar h1{font-size:1.15em;font-weight:800;display:flex;align-items:center;gap:8px}
.topbar h1 span{color:#6366f1}
.tbar-r{display:flex;gap:8px;align-items:center}
.badge{background:#f1f5f9;border:1px solid #e2e8f0;color:#475569;padding:3px 11px;border-radius:20px;font-size:.78em;font-weight:600}
.badge.ok{border-color:#22c55e;color:#16a34a;background:#f0fdf4}
.wrap{max-width:1280px;margin:0 auto;padding:20px 16px}

/* ── TABS ─────────────────────────────────────────────────────────────────── */
.tabs{display:flex;gap:1px;margin-bottom:20px;border-bottom:1px solid #e2e8f0;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{padding:10px 18px;cursor:pointer;border:none;background:none;color:#64748b;font-size:.85em;border-bottom:2px solid transparent;margin-bottom:-1px;transition:.2s;font-family:inherit;white-space:nowrap;font-weight:600}
.tab.on{color:#2563eb;border-bottom-color:#3b82f6;font-weight:700}
.tab:hover:not(.on){color:#1e293b}
.panel{display:none}.panel.on{display:block}

/* ── BUTTONS ──────────────────────────────────────────────────────────────── */
.btn{padding:8px 16px;border:none;border-radius:7px;cursor:pointer;font-size:.82em;font-family:inherit;transition:.2s;display:inline-flex;align-items:center;gap:5px;font-weight:600}
.bp{background:#3b82f6;color:#fff}.bp:hover{background:#2563eb}
.bd{background:#ef4444;color:#fff}.bd:hover{background:#dc2626}
.bg{background:#22c55e;color:#fff}.bg:hover{background:#16a34a}
.bo{background:#ffffff;color:#475569;border:1px solid #cbd5e1}.bo:hover{background:#f1f5f9;color:#1e293b}
.by{background:#f59e0b;color:#000}.by:hover{background:#d97706}
.sm{padding:5px 10px;font-size:.78em}
.xs{padding:3px 7px;font-size:.73em}
.btn:disabled{opacity:.4;cursor:default;pointer-events:none}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}

/* ── CARD ─────────────────────────────────────────────────────────────────── */
.card{background:#ffffff;border-radius:10px;padding:18px;margin-bottom:14px;border:1px solid #e2e8f0;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.card-title{font-size:.88em;font-weight:700;color:#2563eb;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;gap:8px}

/* ── DASHBOARD STAT CARDS ────────────────────────────────────────────────── */
.scards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.scard{background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:18px;text-align:center;border-top:3px solid #3b82f6;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.scard:nth-child(2){border-top-color:#22c55e}
.scard:nth-child(3){border-top-color:#f59e0b}
.scard:nth-child(4){border-top-color:#a855f7}
.scard-val{font-size:2em;font-weight:800;color:#1e293b;line-height:1}
.scard-label{font-size:.75em;color:#64748b;margin-top:6px;font-weight:600}

/* ── CHART ────────────────────────────────────────────────────────────────── */
.chart-row{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.chart-label{font-size:.8em;color:#374151;width:160px;text-align:right;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.chart-bar-wrap{flex:1;background:#e2e8f0;border-radius:4px;height:22px;overflow:hidden}
.chart-bar{height:100%;background:linear-gradient(90deg,#3b82f6,#6366f1);border-radius:4px;display:flex;align-items:center;justify-content:flex-end;padding-right:6px;min-width:24px;transition:width .5s}
.chart-bar span{font-size:.73em;font-weight:700;color:#fff;white-space:nowrap}

/* ── SOURCES ──────────────────────────────────────────────────────────────── */
.cat-block{margin-bottom:12px;border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;border-left:3px solid #3b82f6}
.cat-block.cat-disabled{opacity:.6}
.cat-block.cat-disabled .cat-hdr{background:#fee2e2}
.sec-table{width:100%;border-collapse:collapse;font-size:.85em}
.sec-table th{text-align:right;padding:8px 10px;background:#f1f5f9;color:#475569;font-weight:700;border-bottom:2px solid #e2e8f0}
.sec-table td{padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
.sec-table tbody tr:hover{background:#f8fafc}
.sec-table tr.sec-off{opacity:.55;background:#fef2f2}
.sec-ic{font-size:1.2em;text-align:center}
.sec-nm{font-weight:700;color:#1e293b}
.sec-sl{font-family:monospace;color:#64748b;direction:ltr}
.sec-ct{text-align:center;font-weight:600}
.sec-ord{white-space:nowrap}
.cat-hdr{background:#f1f5f9;padding:9px 12px;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.cat-hdr input{background:#ffffff;border:1px solid #cbd5e1;color:#1e293b;border-radius:5px;padding:4px 8px;font-family:inherit;font-size:.82em;outline:none;font-weight:600}
.cat-hdr input:focus{border-color:#3b82f6}
.ci-icon{width:44px;text-align:center}
.ci-name{flex:1;min-width:100px}
.ci-slug{width:120px;direction:ltr;color:#64748b;font-weight:600}
input.color-pick{width:34px;height:28px;padding:2px;border-radius:6px;cursor:pointer;flex-shrink:0}
.cat-body{padding:10px 12px}
.src-row{display:grid;grid-template-columns:1fr 1fr auto auto auto;align-items:center;gap:7px;padding:7px 9px;background:#f8fafc;border-radius:7px;margin-bottom:5px;border:1px solid #e2e8f0}
.src-name{font-size:.85em;font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#1e293b}
.src-url{font-size:.75em;color:#64748b;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;direction:ltr;font-weight:500}
.hbadge{font-size:.75em;font-weight:700;padding:2px 7px;border-radius:10px;white-space:nowrap;cursor:default}
.hbadge.ok{background:rgba(34,197,94,.12);color:#16a34a;border:1px solid rgba(34,197,94,.3)}
.hbadge.fail{background:rgba(239,68,68,.12);color:#dc2626;border:1px solid rgba(239,68,68,.3)}
.hbadge.loading{background:rgba(251,191,36,.12);color:#d97706;border:1px solid rgba(251,191,36,.3)}
.hbadge.idle{background:#f1f5f9;color:#64748b;border:1px solid #cbd5e1}
.sel-panel{background:#f8fafc;border:1px solid #e2e8f0;border-radius:7px;padding:12px;margin:5px 0 8px;display:none}
.sel-panel label{font-size:.75em;color:#374151;display:block;margin-bottom:3px;margin-top:8px;font-weight:700}
.sel-panel label:first-child{margin-top:0}
.sel-panel input{width:100%;background:#ffffff;border:1px solid #cbd5e1;color:#1e293b;border-radius:5px;padding:5px 9px;font-size:.82em;font-family:inherit;outline:none;font-weight:500}
.sel-panel input:focus{border-color:#3b82f6}
.sel-panel input[type=number]{width:80px}
.add-row{display:flex;gap:7px;margin-top:9px;flex-wrap:wrap}
.add-row input{flex:1;min-width:100px;padding:6px 10px;border-radius:5px;border:1px solid #cbd5e1;background:#ffffff;color:#1e293b;font-size:.82em;font-family:inherit;outline:none;font-weight:500}
.add-row input:focus{border-color:#3b82f6}
.del-btn{background:none;border:none;color:#ef4444;cursor:pointer;padding:3px 7px;border-radius:4px;font-size:.9em;line-height:1}
.del-btn:hover{background:rgba(239,68,68,.12)}
.move-btn{background:none;border:none;color:#94a3b8;cursor:pointer;padding:3px 5px;font-size:.8em;line-height:1}
.move-btn:hover{color:#1e293b}

/* ── ARTICLES TABLE ───────────────────────────────────────────────────────── */
.art-filter{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center}
.art-filter input,.art-filter select{padding:7px 11px;border-radius:6px;border:1px solid #cbd5e1;background:#ffffff;color:#1e293b;font-size:.82em;font-family:inherit;outline:none;font-weight:500}
.art-filter input{flex:1;min-width:150px}
.art-filter input:focus,.art-filter select:focus{border-color:#3b82f6}
.art-table{width:100%;border-collapse:collapse;font-size:.82em}
.art-table th{background:#f1f5f9;padding:9px 10px;text-align:right;font-weight:700;color:#374151;border-bottom:1px solid #e2e8f0;white-space:nowrap}
.art-table td{padding:8px 10px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
.art-table tr:hover td{background:#f8fafc}
.art-title{max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:default;font-weight:600}
.art-date{color:#64748b;white-space:nowrap;direction:ltr}
.art-src{color:#374151;font-weight:600}
.art-cat{display:inline-block;padding:2px 8px;border-radius:10px;background:#dbeafe;color:#1d4ed8;font-size:.75em;font-weight:700}
.pager{display:flex;align-items:center;justify-content:space-between;margin-top:12px;font-size:.82em;color:#475569;font-weight:500}
.pager-btns{display:flex;gap:6px}
.lnk{color:#2563eb;font-size:.95em;font-weight:600}
.lnk:hover{color:#1d4ed8}

/* ── BLACKLIST ────────────────────────────────────────────────────────────── */
.kw-chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;min-height:32px}
.kw-chip{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;padding:4px 8px 4px 11px;border-radius:20px;font-size:.82em;display:inline-flex;align-items:center;gap:6px;font-weight:600}
.kw-chip button{background:none;border:none;color:#94a3b8;cursor:pointer;padding:0;font-size:1em;line-height:1}
.kw-chip button:hover{color:#ef4444}
.kw-add{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.kw-add input{flex:1;min-width:180px;padding:8px 12px;border-radius:6px;border:1px solid #cbd5e1;background:#ffffff;color:#1e293b;font-size:.85em;font-family:inherit;outline:none;font-weight:500}
.kw-add input:focus{border-color:#3b82f6}

/* ── SETTINGS ─────────────────────────────────────────────────────────────── */
.sg{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.field{display:flex;flex-direction:column;gap:4px}
.field label{font-size:.75em;color:#374151;font-weight:700}
.field input{padding:8px 10px;border-radius:6px;border:1px solid #cbd5e1;background:#ffffff;color:#1e293b;font-size:.85em;font-family:inherit;outline:none;font-weight:500}
.field input:focus{border-color:#3b82f6}
.full{grid-column:1/-1}
.file-input{padding:7px 10px;border-radius:6px;border:1px solid #cbd5e1;background:#ffffff;color:#64748b;cursor:pointer;font-size:.82em;width:100%;font-weight:500}

/* ── OUTPUT ───────────────────────────────────────────────────────────────── */
.out{background:#f0fdf4;border:1px solid #bbf7d0;padding:14px;border-radius:8px;font-family:monospace;font-size:.78em;max-height:400px;overflow-y:auto;white-space:pre-wrap;color:#166534;line-height:1.55;font-weight:500}
.out.fail{color:#dc2626;background:#fef2f2;border-color:#fecaca}
.sbar{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-size:.8em;color:#475569;font-weight:600}
.dot{width:8px;height:8px;border-radius:50%;background:#cbd5e1;flex-shrink:0}
.dot.run{background:#f59e0b;animation:blink 1s infinite}
.dot.ok{background:#22c55e}.dot.fail{background:#ef4444}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}

/* ── HEALTH SUMMARY ───────────────────────────────────────────────────────── */
.health-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px;margin-top:12px}
.health-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px;display:flex;align-items:center;gap:10px}
.health-card.ok{border-left:3px solid #22c55e}
.health-card.fail{border-left:3px solid #ef4444}
.hc-name{flex:1;font-size:.82em;overflow:hidden}
.hc-title{font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#1e293b}
.hc-url{font-size:.72em;color:#64748b;direction:ltr;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hc-badge{font-size:.75em;font-weight:700;white-space:nowrap;padding:3px 8px;border-radius:8px}

/* ── DB STATS ─────────────────────────────────────────────────────────────── */
.db-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}
.db-card{background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:14px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.db-val{font-size:1.5em;font-weight:800;color:#1e293b}
.db-lbl{font-size:.72em;color:#64748b;margin-top:4px;font-weight:600}

/* ── SOURCE HEALTH TAB ────────────────────────────────────────────────────── */
.sh-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:16px}
.sh-stat{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.sh-stat-val{font-size:1.6em;font-weight:800;line-height:1}
.sh-stat-lbl{font-size:.72em;color:#64748b;margin-top:6px;font-weight:600}
.sh-table{width:100%;border-collapse:collapse;font-size:.82em}
.sh-table th{background:#f1f5f9;padding:8px 10px;text-align:right;font-weight:700;color:#374151;border-bottom:1px solid #e2e8f0;white-space:nowrap}
.sh-table td{padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
.sh-table tr:hover td{background:#f8fafc}
.sh-badge{display:inline-flex;align-items:center;justify-content:center;min-width:58px;padding:3px 9px;border-radius:10px;font-size:.78em;font-weight:700;white-space:nowrap}
.sh-badge.zero{background:rgba(239,68,68,.12);color:#dc2626;border:1px solid rgba(239,68,68,.3)}
.sh-badge.low{background:rgba(245,158,11,.12);color:#d97706;border:1px solid rgba(245,158,11,.3)}
.sh-badge.ok{background:rgba(34,197,94,.12);color:#16a34a;border:1px solid rgba(34,197,94,.3)}
.sh-lang{display:inline-block;padding:2px 7px;border-radius:6px;font-size:.75em;font-weight:700;background:#dbeafe;color:#1d4ed8}
.sh-bar-wrap{height:4px;background:#e2e8f0;border-radius:2px;margin-top:4px;width:100%}
.sh-bar{height:4px;border-radius:2px;background:#22c55e}

/* ── RESPONSIVE ───────────────────────────────────────────────────────────── */
@media(max-width:768px){
  .scards,.db-cards{grid-template-columns:1fr 1fr}
  .sg{grid-template-columns:1fr}
  .src-row{grid-template-columns:1fr auto auto auto}
  .src-url{display:none}
  .chart-label{width:100px}
  .art-title{max-width:160px}
}
@media(max-width:480px){
  .scards,.db-cards{grid-template-columns:1fr}
  .art-src,.art-date{display:none}
}
</style>
</head>
<body>

<!-- ══ LOGIN ══════════════════════════════════════════════════════════════ -->
<div class="overlay" id="overlay">
  <div class="login-box">
    <div style="font-size:2.2em;margin-bottom:10px">📰</div>
    <h2>لوحة التحكم</h2>
    <p>أدخل كلمة المرور للمتابعة</p>
    <input type="password" id="pwd" placeholder="كلمة المرور" autocomplete="current-password">
    <button id="login-btn" onclick="doLogin()">دخول ←</button>
    <p class="err" id="err"></p>
  </div>
</div>

<!-- ══ MAIN ════════════════════════════════════════════════════════════════ -->
<div id="main">
  <div class="topbar">
    <h1>📰 <span>لوحة التحكم</span> — News Aggregator</h1>
    <div class="tbar-r">
      <span class="badge" id="src-badge">— مصدر</span>
      <span class="badge" id="art-badge">— مقالة</span>
      <a href="/static/index.html" target="_blank" class="btn bo sm">👁 الموقع</a>
      <button class="btn bo sm" onclick="doLogout()">خروج</button>
    </div>
  </div>
  <div class="wrap">

    <!-- TABS -->
    <div class="tabs">
      <button class="tab on"  data-t="dash"      onclick="switchTab('dash')">📊 المعلومات</button>
      <button class="tab"     data-t="sections"  onclick="switchTab('sections')">📂 إدارة الأقسام</button>
      <button class="tab"     data-t="sources"   onclick="switchTab('sources')">📋 المصادر</button>
      <button class="tab"     data-t="articles"  onclick="switchTab('articles')">📰 المقالات</button>
      <button class="tab"     data-t="blacklist" onclick="switchTab('blacklist')">🔒 الكلمات المحظورة</button>
      <button class="tab"     data-t="db"        onclick="switchTab('db')">🗄️ قاعدة البيانات</button>
      <button class="tab"     data-t="settings"  onclick="switchTab('settings')">⚙️ الإعدادات</button>
      <button class="tab"     data-t="run"       onclick="switchTab('run')">▶️ التشغيل</button>
      <button class="tab"     data-t="health"    onclick="switchTab('health')">💊 صحة المصادر</button>
    </div>

    <!-- ══ DASHBOARD ══ -->
    <div id="p-dash" class="panel on">
      <div class="scards">
        <div class="scard"><div class="scard-val" id="st-arts">—</div><div class="scard-label">إجمالي المقالات</div></div>
        <div class="scard"><div class="scard-val" id="st-src">—</div><div class="scard-label">إجمالي المصادر</div></div>
        <div class="scard"><div class="scard-val" id="st-db">—</div><div class="scard-label">حجم قاعدة البيانات</div></div>
        <div class="scard"><div class="scard-val" id="st-new">—</div><div class="scard-label">آخر تحديث</div></div>
      </div>
      <div class="card">
        <div class="card-title">📊 المقالات حسب القسم <button class="btn bp sm" onclick="loadDash()">↻ تحديث</button></div>
        <div id="dash-chart"></div>
      </div>
      <div class="card">
        <div class="card-title">⚡ تشغيل سريع</div>
        <div class="row">
          <button class="btn bp" id="qb-scrape"   onclick="runOp('scrape',this)">🕷️ جلب الأخبار</button>
          <button class="btn bg" id="qb-generate" onclick="runOp('generate',this)">🌐 توليد الموقع</button>
          <button class="btn bo" id="qb-run"      onclick="runOp('run',this)">▶️ تشغيل الكل</button>
          <a href="/static/index.html" target="_blank" class="btn by">🔗 فتح الموقع</a>
        </div>
      </div>
    </div>

    <!-- ══ SOURCES ══ -->
    <div id="p-sources" class="panel">
      <div class="card">
        <div class="card-title">
          🔍 فحص صحة المصادر
          <button class="btn by sm" id="health-btn" onclick="checkAllHealth()">🔍 فحص الكل</button>
        </div>
        <div id="health-results"></div>
      </div>
      <div id="cats-wrap"></div>
      <button class="btn bg sm" onclick="addCat()" style="margin-bottom:14px">+ إضافة تصنيف</button>
      <div class="row">
        <button class="btn bp" onclick="saveCfg()">💾 حفظ التغييرات</button>
        <button class="btn bd" onclick="resetCfg()">🔄 استعادة الافتراضي</button>
      </div>
    </div>

    <!-- ══ SECTIONS MANAGER ══ -->
    <div id="p-sections" class="panel">
      <div class="card">
        <div class="card-title">
          📂 إدارة الأقسام
          <button class="btn bg sm" onclick="addCat();renderSections()">+ قسم جديد</button>
        </div>
        <p style="font-size:.82em;color:#64748b;margin:6px 0 14px">تحكّم سريع بكل الأقسام: الترتيب، الإظهار/الإخفاء من الموقع، الإفراغ، الحذف. لإدارة المصادر داخل قسم استخدم تبويب «المصادر».</p>
        <div id="sections-wrap"></div>
      </div>
      <div class="row">
        <button class="btn bp" onclick="saveCfg()">💾 حفظ التغييرات</button>
      </div>
    </div>

    <!-- ══ ARTICLES ══ -->
    <div id="p-articles" class="panel">
      <div class="art-filter">
        <input id="art-q" placeholder="بحث في العناوين أو المصادر..." onkeydown="if(event.key==='Enter')loadArticles(true)">
        <select id="art-cat" onchange="loadArticles(true)">
          <option value="">كل الأقسام</option>
        </select>
        <button class="btn bp sm" onclick="loadArticles(true)">🔍 بحث</button>
        <button class="btn bo sm" onclick="clearArtFilter()">✕ إلغاء</button>
      </div>
      <div class="card" style="padding:0;overflow:hidden">
        <table class="art-table">
          <thead>
            <tr>
              <th>العنوان</th>
              <th>المصدر</th>
              <th>القسم</th>
              <th>التاريخ</th>
              <th>رابط</th>
              <th>حذف</th>
            </tr>
          </thead>
          <tbody id="art-tbody">
            <tr><td colspan="6" style="text-align:center;padding:30px;color:#475569">جارٍ التحميل...</td></tr>
          </tbody>
        </table>
      </div>
      <div class="pager">
        <span id="art-info">—</span>
        <div class="pager-btns">
          <button class="btn bo sm" id="art-prev" onclick="artPageChange(-1)">→ السابق</button>
          <button class="btn bo sm" id="art-next" onclick="artPageChange(1)">التالي ←</button>
        </div>
      </div>
    </div>

    <!-- ══ BLACKLIST ══ -->
    <div id="p-blacklist" class="panel">
      <div class="card">
        <div class="card-title">🔒 الكلمات المحظورة
          <span style="font-size:.78em;color:#64748b;font-weight:400">سيتم استبعاد المقالات التي تحتوي على هذه الكلمات عند توليد الموقع</span>
        </div>
        <div id="kw-list" class="kw-chips"></div>
        <div class="kw-add">
          <input id="kw-inp" placeholder="أضف كلمة محظورة..." onkeydown="if(event.key==='Enter')addKw()">
          <button class="btn bp sm" onclick="addKw()">+ إضافة</button>
          <button class="btn bg sm" onclick="saveBlacklist()">💾 حفظ</button>
        </div>
      </div>
      <div class="card" style="margin-top:0">
        <div class="card-title">💡 أمثلة على كلمات الحظر</div>
        <div class="row" style="flex-wrap:wrap">
          <button class="btn bo xs" onclick="addKwVal('إعلان')">إعلان</button>
          <button class="btn bo xs" onclick="addKwVal('برعاية')">برعاية</button>
          <button class="btn bo xs" onclick="addKwVal('مسابقة')">مسابقة</button>
          <button class="btn bo xs" onclick="addKwVal('عرض خاص')">عرض خاص</button>
          <button class="btn bo xs" onclick="addKwVal('اشترك الآن')">اشترك الآن</button>
        </div>
      </div>
    </div>

    <!-- ══ DATABASE ══ -->
    <div id="p-db" class="panel">
      <div class="db-cards">
        <div class="db-card"><div class="db-val" id="db-total">—</div><div class="db-lbl">إجمالي المقالات</div></div>
        <div class="db-card"><div class="db-val" id="db-size">—</div><div class="db-lbl">حجم قاعدة البيانات</div></div>
        <div class="db-card"><div class="db-val" id="db-newest">—</div><div class="db-lbl">أحدث مقالة</div></div>
        <div class="db-card"><div class="db-val" id="db-oldest">—</div><div class="db-lbl">أقدم مقالة</div></div>
      </div>
      <div class="card">
        <div class="card-title">📊 توزيع المقالات <button class="btn bp sm" onclick="loadDbStats()">↻ تحديث</button></div>
        <div id="db-chart"></div>
      </div>
      <div class="row" style="gap:14px;flex-wrap:wrap">
        <div class="card" style="flex:1;min-width:240px">
          <div class="card-title">🗑️ تنظيف البيانات القديمة</div>
          <div class="row" style="margin-bottom:10px">
            <label style="color:#64748b;font-size:.82em">حذف المقالات الأقدم من</label>
            <input type="number" id="cleanup-days" value="30" min="1" max="365"
                   style="width:65px;padding:5px 8px;border-radius:5px;border:1px solid #1e3a5f;background:#0a0f1e;color:#f1f5f9;font-size:.82em;outline:none;text-align:center">
            <span style="color:#64748b;font-size:.82em">يوم</span>
          </div>
          <button class="btn bd sm" onclick="doCleanup()">🗑️ حذف</button>
        </div>
        <div class="card" style="flex:1;min-width:240px">
          <div class="card-title">📤 تصدير البيانات</div>
          <div class="row">
            <button class="btn bg sm" onclick="window.open('/api/db/export','_blank')">⬇️ تصدير CSV</button>
            <button class="btn bp sm" onclick="window.open('/api/export/config','_blank')">⬇️ تصدير الإعدادات</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ══ SETTINGS ══ -->
    <div id="p-settings" class="panel">
      <div class="card">
        <div class="card-title">⚙️ إعدادات الموقع</div>
        <div class="sg">
          <div class="field full"><label>عنوان الموقع</label><input id="s-title"></div>
          <div class="field full"><label>وصف الموقع</label><input id="s-desc"></div>
          <div class="field"><label>أقصى عدد مقالات لكل مصدر</label><input type="number" id="s-max" min="1" max="50"></div>
          <div class="field"><label>عرض أخبار آخر (أيام)</label><input type="number" id="s-days" min="1" max="30"></div>
        </div>
        <div style="margin-top:14px">
          <button class="btn bp" onclick="saveSettings()">💾 حفظ الإعدادات</button>
        </div>
      </div>
      <div class="row" style="gap:14px;flex-wrap:wrap">
        <div class="card" style="flex:1;min-width:240px">
          <div class="card-title">⬇️ تصدير الإعدادات</div>
          <p style="color:#64748b;font-size:.82em;margin-bottom:12px">تحميل ملف sources.json الحالي</p>
          <button class="btn bg sm" onclick="window.open('/api/export/config','_blank')">⬇️ تحميل sources.json</button>
        </div>
        <div class="card" style="flex:1;min-width:240px">
          <div class="card-title">⬆️ استيراد الإعدادات</div>
          <p style="color:#64748b;font-size:.82em;margin-bottom:10px">رفع ملف sources.json جديد</p>
          <input type="file" id="import-file" accept=".json" class="file-input" style="margin-bottom:10px">
          <button class="btn bp sm" onclick="importConfig()">⬆️ استيراد</button>
        </div>
      </div>
    </div>

    <!-- ══ RUN ══ -->
    <div id="p-run" class="panel">
      <div class="card">
        <div class="card-title">▶️ تشغيل العمليات</div>
        <p style="color:#475569;font-size:.82em;margin-bottom:14px">قد تستغرق العمليات عدة دقائق. ستظهر المخرجات أدناه.</p>
        <div class="row">
          <button class="btn bp" id="b-scrape"   onclick="runOp('scrape',this)">🕷️ جلب الأخبار</button>
          <button class="btn bg" id="b-generate" onclick="runOp('generate',this)">🌐 توليد الموقع</button>
          <button class="btn bo" id="b-run"      onclick="runOp('run',this)">▶️ تشغيل الكل</button>
        </div>
      </div>
      <div class="card">
        <div class="card-title">📄 المخرجات</div>
        <div class="sbar"><span class="dot" id="dot"></span><span id="run-status">لم يتم تشغيل أي عملية بعد</span></div>
        <div class="out" id="run-out">—</div>
      </div>
      <div class="card">
        <div class="card-title">🔗 روابط سريعة</div>
        <div class="row">
          <a href="/static/index.html"   target="_blank" class="btn bo">🌐 الصفحة الرئيسية</a>
          <a href="/static/about.html"   target="_blank" class="btn bo">ℹ️ من نحن</a>
          <a href="/static/privacy.html" target="_blank" class="btn bo">🔒 الخصوصية</a>
        </div>
      </div>
    </div>

    <!-- ══ SOURCE HEALTH ══ -->
    <div id="p-health" class="panel">
      <div class="sh-stats">
        <div class="sh-stat"><div class="sh-stat-val" id="sh-total" style="color:#3b82f6">—</div><div class="sh-stat-lbl">إجمالي المصادر (5 لغات)</div></div>
        <div class="sh-stat"><div class="sh-stat-val" id="sh-ok"    style="color:#22c55e">—</div><div class="sh-stat-lbl">✅ تعمل جيداً (≥5 مقالات)</div></div>
        <div class="sh-stat"><div class="sh-stat-val" id="sh-low"   style="color:#f59e0b">—</div><div class="sh-stat-lbl">⚠️ قليلة (1–4 مقالات)</div></div>
        <div class="sh-stat"><div class="sh-stat-val" id="sh-zero"  style="color:#ef4444">—</div><div class="sh-stat-lbl">🔴 صفر مقالات</div></div>
      </div>
      <div class="card" style="padding:0;overflow:hidden">
        <div style="padding:12px 14px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
          <select id="sh-lang-f" onchange="renderHealth()">
            <option value="">🌐 كل اللغات</option>
            <option value="ar">🇸🇦 العربية (AR)</option>
            <option value="en">🇬🇧 الإنجليزية (EN)</option>
            <option value="fr">🇫🇷 الفرنسية (FR)</option>
            <option value="es">🇪🇸 الإسبانية (ES)</option>
            <option value="tr">🇹🇷 التركية (TR)</option>
          </select>
          <select id="sh-status-f" onchange="renderHealth()">
            <option value="">كل الحالات</option>
            <option value="zero">🔴 صفر مقالات</option>
            <option value="low">🟡 قليلة (1–4)</option>
            <option value="ok">🟢 تعمل (≥5)</option>
          </select>
          <input id="sh-search" placeholder="بحث باسم المصدر أو القسم..." style="flex:1;min-width:140px;padding:6px 10px;border-radius:6px;border:1px solid #cbd5e1;background:#fff;color:#1e293b;font-size:.82em;font-family:inherit;outline:none" oninput="renderHealth()">
          <button class="btn bp sm" onclick="loadHealth()">↻ تحديث</button>
        </div>
        <div style="overflow-x:auto">
          <table class="sh-table">
            <thead>
              <tr>
                <th>المصدر</th>
                <th>القسم</th>
                <th>اللغة</th>
                <th>مقالات (7 أيام)</th>
                <th>آخر جلب</th>
                <th>رابط</th>
              </tr>
            </thead>
            <tbody id="sh-tbody">
              <tr><td colspan="6" style="text-align:center;padding:30px;color:#475569">اضغط ↻ تحديث لتحميل بيانات الصحة من جميع اللغات</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

  </div><!-- /wrap -->
</div><!-- /main -->

<script>
'use strict';

// ══ GLOBALS ══════════════════════════════════════════════════════════════════
let cfg = null;
let artPage = 1, artCat = '', artQ = '';
let blist = [];

// ══ AUTH ══════════════════════════════════════════════════════════════════════
async function doLogin() {
  const pwd = document.getElementById('pwd').value;
  if (!pwd) return;
  const btn = document.getElementById('login-btn');
  const err = document.getElementById('err');
  btn.disabled = true; btn.textContent = 'جارٍ التحقق...'; err.textContent = '';
  try {
    const r = await fetch('/api/login', {method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({password: pwd}), credentials:'same-origin'});
    const d = await r.json();
    if (d.ok) { showMain(); }
    else { err.textContent = d.error || 'كلمة المرور غير صحيحة';
           document.getElementById('pwd').value = '';
           document.getElementById('pwd').focus(); }
  } catch(e) { err.textContent = 'خطأ في الاتصال'; }
  finally { btn.disabled = false; btn.textContent = 'دخول ←'; }
}
document.getElementById('pwd').addEventListener('keydown', e => { if(e.key==='Enter') doLogin(); });

async function doLogout() {
  await api('/api/logout', {method:'POST'});
  location.reload();
}

// ══ API ═══════════════════════════════════════════════════════════════════════
async function api(url, opts={}) {
  try {
    const r = await fetch(url, {credentials:'same-origin', ...opts,
      headers:{'Content-Type':'application/json', ...(opts.headers||{})}});
    if (r.status === 401) {
      document.getElementById('overlay').style.display = 'flex';
      document.getElementById('main').style.display = 'none';
      return null;
    }
    return await r.json();
  } catch(e) { console.error(e); return null; }
}

// ══ INIT ══════════════════════════════════════════════════════════════════════
function showMain() {
  document.getElementById('overlay').style.display = 'none';
  document.getElementById('main').style.display = 'block';
  loadAll();
}

async function loadAll() {
  const d = await api('/api/config');
  if (!d) return;
  cfg = d;
  renderSources();
  loadSettings();
  updateBadge();
  loadDash();
  loadBlacklist();
  populateCatFilter();
}

function updateBadge() {
  const n = cfg.categories.reduce((s,c) => s + c.sources.length, 0);
  document.getElementById('src-badge').textContent = n + ' مصدر';
}

(async function boot() {
  try {
    const r = await fetch('/api/config', {credentials:'same-origin'});
    if (r.ok) { const d = await r.json(); if (d?.categories) { cfg=d; showMain(); return; } }
  } catch(e) {}
  document.getElementById('pwd').focus();
})();

// ══ TABS ══════════════════════════════════════════════════════════════════════
const TAB_INIT = {articles: false, db: false, health: false};
function switchTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('on', t.dataset.t===name));
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('on', p.id==='p-'+name));
  if (name === 'articles' && !TAB_INIT.articles) { TAB_INIT.articles=true; loadArticles(true); }
  if (name === 'db'       && !TAB_INIT.db)       { TAB_INIT.db=true;       loadDbStats(); }
  if (name === 'health'   && !TAB_INIT.health)   { TAB_INIT.health=true;   loadHealth(); }
  if (name === 'sections') { renderSections(); }
}

// ══ DASHBOARD ════════════════════════════════════════════════════════════════
async function loadDash() {
  const d = await api('/api/stats');
  if (!d) return;
  document.getElementById('st-arts').textContent = d.total;
  document.getElementById('st-src').textContent  = d.total_sources;
  document.getElementById('st-db').textContent   = d.db_size_kb + ' KB';
  document.getElementById('st-new').textContent  = d.newest || '—';
  document.getElementById('art-badge').textContent = d.total + ' مقالة';
  const max = Math.max(...d.by_cat.map(c=>c.count), 1);
  const colors = ['#3b82f6','#22c55e','#f59e0b','#a855f7','#ec4899','#ef4444','#06b6d4','#84cc16'];
  document.getElementById('dash-chart').innerHTML = d.by_cat.map((c,i) => `
    <div class="chart-row">
      <span class="chart-label" title="${esc(c.name)}">${esc(c.name)}</span>
      <div class="chart-bar-wrap">
        <div class="chart-bar" style="width:${Math.max(4,Math.round(c.count/max*100))}%;background:${colors[i%colors.length]}">
          <span>${c.count}</span>
        </div>
      </div>
    </div>`).join('');
}

// ══ SOURCES ══════════════════════════════════════════════════════════════════
function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function renderSources() {
  document.getElementById('cats-wrap').innerHTML = cfg.categories.map((c,ci) => {
    const color = c.color || '#3b82f6';
    return `
    <div class="cat-block ${c.enabled===false?'cat-disabled':''}" data-ci="${ci}" style="border-left-color:${esc(color)}">
      <div class="cat-hdr">
        <input type="color" class="color-pick" value="${esc(color)}"
               oninput="cfg.categories[${ci}].color=this.value;this.closest('.cat-block').style.borderLeftColor=this.value">
        <input class="ci-icon" value="${esc(c.icon||'📰')}" title="أيقونة"
               oninput="cfg.categories[${ci}].icon=this.value">
        <input class="ci-name" value="${esc(c.name)}" placeholder="اسم التصنيف"
               oninput="cfg.categories[${ci}].name=this.value">
        <input class="ci-slug" value="${esc(c.slug)}" placeholder="slug"
               oninput="cfg.categories[${ci}].slug=this.value.replace(/[^a-z0-9-]/g,'')">
        <button class="move-btn" title="رفع" onclick="moveCat(${ci},-1)">▲</button>
        <button class="move-btn" title="تنزيل" onclick="moveCat(${ci},1)">▼</button>
        <button class="btn ${c.enabled===false?'bo':'bg'} xs" onclick="toggleCat(${ci})"
                title="${c.enabled===false?'مخفي من الموقع — اضغط للإظهار':'ظاهر — اضغط للإخفاء من الموقع'}">${c.enabled===false?'🚫 مخفي':'👁️ ظاهر'}</button>
        <button class="btn bd xs" onclick="delCat(${ci})">✕ حذف</button>
      </div>
      <div class="cat-body">
        ${c.sources.map((s,si) => renderSrcRow(ci, si, s)).join('')}
        <div class="add-row">
          <input placeholder="اسم المصدر"  id="nn-${ci}">
          <input placeholder="https://..." id="nu-${ci}" style="direction:ltr">
          <button class="btn bp xs" onclick="addSrc(${ci})">+ إضافة</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

function renderSrcRow(ci, si, s) {
  const sel = s.selectors || {};
  return `
    <div class="src-row">
      <span class="src-name">${esc(s.name)}</span>
      <span class="src-url">${esc(s.url)}</span>
      <span class="hbadge idle" id="h-${ci}-${si}" data-health-url="${esc(s.url)}"
            title="لم يتم الفحص">●</span>
      <button class="btn bo xs" onclick="toggleSel(${ci},${si})" title="تعديل المحددات">⚙️</button>
      <button class="move-btn" onclick="moveSrc(${ci},${si},-1)">▲</button>
      <button class="move-btn" onclick="moveSrc(${ci},${si},1)">▼</button>
      <button class="del-btn"  onclick="delSrc(${ci},${si})">✕</button>
    </div>
    <div class="sel-panel" id="se-${ci}-${si}">
      <label>article_selector</label>
      <input id="sel-as-${ci}-${si}" value="${esc(sel.article_selector||'article, .post, .article')}" placeholder="article, .post">
      <label>heading_tags (مفصولة بفاصلة)</label>
      <input id="sel-ht-${ci}-${si}" value="${esc((sel.heading_tags||['h2','h3']).join(', '))}" placeholder="h2, h3">
      <label>exclude_classes (مفصولة بفاصلة)</label>
      <input id="sel-ec-${ci}-${si}" value="${esc((sel.exclude_classes||['footer','nav','header']).join(', '))}">
      <label>exclude_id_patterns (مفصولة بفاصلة)</label>
      <input id="sel-ep-${ci}-${si}" value="${esc((sel.exclude_id_patterns||['footer','nav','header']).join(', '))}">
      <label>الحد الأدنى لطول العنوان</label>
      <input type="number" id="sel-ml-${ci}-${si}" value="${sel.min_title_length||20}" min="5" max="100">
      <div class="row" style="margin-top:10px">
        <button class="btn bp xs" onclick="saveSelector(${ci},${si})">✔ تطبيق</button>
        <button class="btn bo xs" onclick="toggleSel(${ci},${si})">إلغاء</button>
      </div>
    </div>`;
}

function toggleSel(ci,si) {
  const el = document.getElementById('se-'+ci+'-'+si);
  el.style.display = el.style.display==='block' ? 'none' : 'block';
}

function saveSelector(ci,si) {
  const src = cfg.categories[ci].sources[si];
  src.selectors = {
    article_selector:    document.getElementById('sel-as-'+ci+'-'+si).value,
    heading_tags:        document.getElementById('sel-ht-'+ci+'-'+si).value.split(',').map(s=>s.trim()).filter(Boolean),
    exclude_classes:     document.getElementById('sel-ec-'+ci+'-'+si).value.split(',').map(s=>s.trim()).filter(Boolean),
    exclude_id_patterns: document.getElementById('sel-ep-'+ci+'-'+si).value.split(',').map(s=>s.trim()).filter(Boolean),
    min_title_length:    +document.getElementById('sel-ml-'+ci+'-'+si).value || 20,
  };
  toggleSel(ci,si);
  toast('⚙️ تم تحديث المحددات — لا تنسَ الحفظ');
}

function moveCat(ci,dir) {
  const j = ci+dir;
  if (j<0||j>=cfg.categories.length) return;
  [cfg.categories[ci],cfg.categories[j]] = [cfg.categories[j],cfg.categories[ci]];
  renderSources();
}
function moveSrc(ci,si,dir) {
  const srcs = cfg.categories[ci].sources;
  const j = si+dir;
  if (j<0||j>=srcs.length) return;
  [srcs[si],srcs[j]] = [srcs[j],srcs[si]];
  renderSources();
}
function delCat(ci) {
  if (!confirm('حذف التصنيف "'+cfg.categories[ci].name+'" وجميع مصادره؟')) return;
  cfg.categories.splice(ci,1); renderSources(); updateBadge();
}
function toggleCat(ci) {
  // Toggle section visibility on the live site (enabled:false hides it everywhere).
  // Missing flag = enabled; first click hides it.
  const c = cfg.categories[ci];
  c.enabled = (c.enabled === false);   // false→true (show) ; true/undefined→false (hide)
  renderSources();
  renderSections();
}
function emptyCat(ci) {
  // Feature #3 — empty a section of all its sources, keeping the section itself.
  const c = cfg.categories[ci];
  const n = (c.sources || []).length;
  if (!n) { alert('القسم "'+c.name+'" فارغ أصلاً.'); return; }
  if (!confirm('إفراغ "'+c.name+'" من كل مصادره ('+n+' مصدر)؟\nالقسم نفسه يبقى — تضيف مصادر جديدة لاحقاً.')) return;
  c.sources = [];
  renderSources(); renderSections(); updateBadge();
}
// ══ SECTIONS MANAGER (dedicated tab — feature: section-only management) ═══════
function renderSections() {
  const wrap = document.getElementById('sections-wrap');
  if (!wrap || !window.cfg || !cfg.categories) return;
  const rows = cfg.categories.map((c, ci) => {
    const off = c.enabled === false;
    const nSrc = (c.sources || []).length;
    return `<tr class="${off ? 'sec-off' : ''}">
      <td class="sec-ord">
        <button class="move-btn" title="رفع"   onclick="moveCat(${ci},-1);renderSections()">▲</button>
        <button class="move-btn" title="تنزيل" onclick="moveCat(${ci},1);renderSections()">▼</button>
      </td>
      <td class="sec-ic">${esc(c.icon || '📰')}</td>
      <td class="sec-nm">${esc(c.name)}</td>
      <td class="sec-sl">${esc(c.slug)}</td>
      <td class="sec-ct">${nSrc}</td>
      <td><button class="btn ${off ? 'bo' : 'bg'} xs" onclick="toggleCat(${ci})"
             title="${off ? 'مخفي من الموقع — اضغط للإظهار' : 'ظاهر — اضغط للإخفاء'}">${off ? '🚫 مخفي' : '👁️ ظاهر'}</button></td>
      <td><button class="btn bo xs" onclick="emptyCat(${ci})" title="حذف كل المصادر، إبقاء القسم">🗑️ إفراغ</button></td>
      <td><button class="btn bd xs" onclick="delCat(${ci});renderSections()" title="حذف القسم نهائياً">✕</button></td>
    </tr>`;
  }).join('');
  wrap.innerHTML = `<table class="sec-table"><thead><tr>
    <th>الترتيب</th><th></th><th>الاسم</th><th>المعرّف</th><th>مصادر</th><th>الحالة</th><th>إفراغ</th><th>حذف</th>
  </tr></thead><tbody>${rows}</tbody></table>`;
}
function addCat() {
  cfg.categories.push({name:'تصنيف جديد',slug:'cat-'+Date.now(),icon:'📰',color:'#3b82f6',sources:[]});
  renderSources(); updateBadge();
}
function delSrc(ci,si) {
  cfg.categories[ci].sources.splice(si,1); renderSources(); updateBadge();
}
function addSrc(ci) {
  const name = document.getElementById('nn-'+ci).value.trim();
  const url  = document.getElementById('nu-'+ci).value.trim();
  if (!name||!url) { alert('يرجى ملء الاسم والرابط'); return; }
  if (!/^https?:\\/\\//i.test(url)) { alert('يجب أن يبدأ الرابط بـ https://'); return; }
  cfg.categories[ci].sources.push({name, url, selectors:{
    article_selector:'article, .post, .article, .news-item',
    heading_tags:['h2','h3'],
    exclude_classes:['footer','nav','menu','header','sidebar','banner'],
    exclude_id_patterns:['footer','nav','menu','header','sidebar'],
    min_title_length:20
  }});
  renderSources(); updateBadge();
}

async function saveCfg() {
  const d = await api('/api/config',{method:'POST',body:JSON.stringify(cfg)});
  if (d?.ok) toast('✅ تم الحفظ بنجاح');
  else alert('خطأ: '+(d?.error||'؟'));
}
async function resetCfg() {
  if (!confirm('استعادة الإعدادات الافتراضية؟ سيتم فقدان كل التعديلات.')) return;
  const d = await api('/api/config/reset',{method:'POST'});
  if (d?.ok) { await loadAll(); toast('✅ تمت الاستعادة'); }
}

// ── HEALTH CHECK ─────────────────────────────────────────────────────────────
async function checkAllHealth() {
  const btn = document.getElementById('health-btn');
  btn.disabled = true; btn.textContent = '⟳ جارٍ الفحص...';
  document.querySelectorAll('.hbadge').forEach(b=>{b.textContent='⟳';b.className='hbadge loading';b.title='جارٍ الفحص...'});
  document.getElementById('health-results').innerHTML = '<p style="color:#64748b;font-size:.82em;padding:8px 0">جارٍ فحص '+
    document.querySelectorAll('.hbadge').length+' مصدراً...</p>';
  const d = await api('/api/health',{method:'POST',body:'{}'});
  btn.disabled = false; btn.textContent = '🔍 فحص الكل';
  if (!d?.results) return;
  d.results.forEach(r => {
    const el = document.querySelector('[data-health-url="'+CSS.escape(r.url)+'"]');
    if (el) {
      el.textContent = r.ok ? '✔' : '✕';
      el.className = 'hbadge '+(r.ok?'ok':'fail');
      el.title = r.ok ? 'HTTP '+r.status+' — '+r.ms+'ms' : (r.error||'فشل HTTP '+(r.status||''));
    }
  });
  const okN = d.results.filter(r=>r.ok).length;
  const tot = d.results.length;
  document.getElementById('health-results').innerHTML = `
    <p style="color:${okN===tot?'#22c55e':'#f59e0b'};font-size:.85em;margin-bottom:10px">
      ✔ ${okN} / ${tot} مصدر يعمل بشكل صحيح</p>
    <div class="health-grid">${d.results.map(r=>`
      <div class="health-card ${r.ok?'ok':'fail'}">
        <div class="hc-name">
          <div class="hc-title">${esc(r.name)}</div>
          <div class="hc-url">${esc(r.url)}</div>
        </div>
        <span class="hc-badge" style="background:${r.ok?'rgba(34,197,94,.15)':'rgba(239,68,68,.15)'};color:${r.ok?'#22c55e':'#ef4444'}">
          ${r.ok?'✔ '+r.status:'✕ '+(r.status||'ERR')} ${r.ms?r.ms+'ms':''}
        </span>
      </div>`).join('')}</div>`;
}

// ══ ARTICLES ══════════════════════════════════════════════════════════════════
function populateCatFilter() {
  const sel = document.getElementById('art-cat');
  cfg.categories.forEach(c => {
    if (c.sources.length === 0) return;
    const opt = document.createElement('option');
    opt.value = c.slug; opt.textContent = c.icon+' '+c.name;
    sel.appendChild(opt);
  });
}

async function loadArticles(reset=false) {
  if (reset) artPage = 1;
  artCat = document.getElementById('art-cat').value;
  artQ   = document.getElementById('art-q').value.trim();
  const url = '/api/articles?cat='+encodeURIComponent(artCat)+'&q='+encodeURIComponent(artQ)+'&page='+artPage+'&limit=25';
  const d   = await api(url);
  if (!d) return;
  const tbody = document.getElementById('art-tbody');
  if (!d.items.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:28px;color:#475569">لا توجد نتائج</td></tr>';
  } else {
    tbody.innerHTML = d.items.map(a => {
      const title = a.title.length>65 ? a.title.substring(0,65)+'…' : a.title;
      return `<tr>
        <td class="art-title" title="${esc(a.title)}">${esc(title)}</td>
        <td class="art-src">${esc(a.source_name)}</td>
        <td><span class="art-cat">${esc(a.category_slug)}</span></td>
        <td class="art-date">${(a.scraped_at||'').substring(0,10)}</td>
        <td><a href="${esc(a.url)}" target="_blank" class="lnk" title="فتح المقالة">🔗</a></td>
        <td><button class="del-btn" onclick="deleteArt(${a.id},this)">✕</button></td>
      </tr>`;
    }).join('');
  }
  document.getElementById('art-info').textContent = d.total+' مقالة — صفحة '+d.page+' من '+d.pages;
  document.getElementById('art-prev').disabled = d.page <= 1;
  document.getElementById('art-next').disabled = d.page >= d.pages;
}

async function deleteArt(id, btn) {
  btn.disabled = true;
  const d = await api('/api/article/delete',{method:'POST',body:JSON.stringify({id})});
  if (d?.ok) btn.closest('tr').remove();
  else btn.disabled = false;
}

function artPageChange(dir) {
  artPage = Math.max(1, artPage+dir);
  loadArticles();
}

function clearArtFilter() {
  document.getElementById('art-q').value = '';
  document.getElementById('art-cat').value = '';
  loadArticles(true);
}

// ══ BLACKLIST ════════════════════════════════════════════════════════════════
async function loadBlacklist() {
  const d = await api('/api/blacklist');
  if (!d) return;
  blist = d.keywords || [];
  renderBlacklist();
}

function renderBlacklist() {
  document.getElementById('kw-list').innerHTML = blist.length
    ? blist.map((kw,i) => `<span class="kw-chip">${esc(kw)}<button onclick="removeKw(${i})">×</button></span>`).join('')
    : '<span style="color:#475569;font-size:.82em">لا توجد كلمات محظورة حتى الآن</span>';
}

function addKwVal(kw) { document.getElementById('kw-inp').value=kw; addKw(); }

function addKw() {
  const inp = document.getElementById('kw-inp');
  const kw  = inp.value.trim();
  if (!kw || blist.includes(kw)) { inp.value=''; return; }
  blist.push(kw); inp.value = '';
  renderBlacklist();
}

function removeKw(i) { blist.splice(i,1); renderBlacklist(); }

async function saveBlacklist() {
  const d = await api('/api/blacklist',{method:'POST',body:JSON.stringify({keywords:blist})});
  if (d?.ok) toast('✅ تم حفظ قائمة الكلمات المحظورة');
}

// ══ DATABASE ══════════════════════════════════════════════════════════════════
async function loadDbStats() {
  const d = await api('/api/stats');
  if (!d) return;
  document.getElementById('db-total').textContent  = d.total;
  document.getElementById('db-size').textContent   = d.db_size_kb+' KB';
  document.getElementById('db-newest').textContent = d.newest||'—';
  document.getElementById('db-oldest').textContent = d.oldest||'—';
  const max = Math.max(...d.by_cat.map(c=>c.count),1);
  const colors = ['#3b82f6','#22c55e','#f59e0b','#a855f7','#ec4899','#ef4444','#06b6d4','#84cc16','#f97316'];
  document.getElementById('db-chart').innerHTML = d.by_cat.map((c,i)=>`
    <div class="chart-row">
      <span class="chart-label" title="${esc(c.name)}">${esc(c.name)}</span>
      <div class="chart-bar-wrap">
        <div class="chart-bar" style="width:${Math.max(3,Math.round(c.count/max*100))}%;background:${colors[i%colors.length]}">
          <span>${c.count}</span>
        </div>
      </div>
    </div>`).join('');
}

async function doCleanup() {
  const days = +document.getElementById('cleanup-days').value;
  if (!days||days<1) return;
  if (!confirm('حذف جميع المقالات الأقدم من '+days+' يوم؟')) return;
  const d = await api('/api/db/cleanup',{method:'POST',body:JSON.stringify({days})});
  if (d?.ok) { toast('🗑️ تم حذف '+d.deleted+' مقالة'); loadDbStats(); }
}

// ══ SETTINGS ══════════════════════════════════════════════════════════════════
function loadSettings() {
  const s = cfg.settings||{};
  document.getElementById('s-title').value = s.site_title||'';
  document.getElementById('s-desc').value  = s.site_description||'';
  document.getElementById('s-max').value   = s.max_articles_per_source||10;
  document.getElementById('s-days').value  = s.oldest_days||7;
}

async function saveSettings() {
  if (!cfg.settings) cfg.settings = {};
  cfg.settings.site_title              = document.getElementById('s-title').value.trim();
  cfg.settings.site_description        = document.getElementById('s-desc').value.trim();
  cfg.settings.max_articles_per_source = +document.getElementById('s-max').value;
  cfg.settings.oldest_days             = +document.getElementById('s-days').value;
  await saveCfg();
}

async function importConfig() {
  const file = document.getElementById('import-file').files[0];
  if (!file) { alert('الرجاء اختيار ملف أولاً'); return; }
  try {
    const text = await file.text();
    const data = JSON.parse(text);
    const d = await api('/api/import/config',{method:'POST',body:JSON.stringify(data)});
    if (d?.ok) { await loadAll(); toast('✅ تم الاستيراد بنجاح'); }
    else toast('❌ '+(d?.error||'خطأ'), 'fail');
  } catch(e) { toast('❌ ملف JSON غير صالح', 'fail'); }
}

// ══ RUN ═══════════════════════════════════════════════════════════════════════
const OP_LABELS = {scrape:'🕷️ جلب الأخبار', generate:'🌐 توليد الموقع', run:'▶️ تشغيل الكل'};

async function runOp(op, btn) {
  btn.disabled = true; btn.textContent = '⟳ جارٍ...';
  const dot = document.getElementById('dot');
  const st  = document.getElementById('run-status');
  const out = document.getElementById('run-out');
  if (dot) { dot.className='dot run'; st.textContent='جارٍ: '+OP_LABELS[op]; }
  if (out) { out.className='out'; out.textContent='الرجاء الانتظار...'; }
  switchTab('run');
  const d = await api('/api/'+op);
  btn.disabled = false; btn.textContent = OP_LABELS[op];
  if (!d) { if(dot) dot.className='dot fail'; if(st) st.textContent='فشل الاتصال'; return; }
  if (dot) { dot.className='dot '+(d.ok?'ok':'fail'); }
  if (st)  { st.textContent = d.ok ? '✅ اكتمل بنجاح' : '❌ فشل (كود: '+(d.returncode??'؟')+')'; }
  if (out) {
    out.textContent = (d.stdout||'') + (d.stderr ? '\\n\\n[STDERR]\\n'+d.stderr : '') || d.msg || d.error || '(لا مخرجات)';
    out.className   = 'out'+(d.ok?'':' fail');
    out.scrollTop   = out.scrollHeight;
  }
  if (d.ok) { loadDash(); }
}

// ══ SOURCE HEALTH ════════════════════════════════════════════════════════════
let shData = null;
const SH_FLAGS = {ar:'🇸🇦',en:'🇬🇧',fr:'🇫🇷',es:'🇪🇸',tr:'🇹🇷'};

async function loadHealth() {
  document.getElementById('sh-tbody').innerHTML =
    '<tr><td colspan="6" style="text-align:center;padding:30px;color:#475569">⟳ جارٍ قراءة جميع قواعد البيانات...</td></tr>';
  const d = await api('/api/source-health');
  if (!d) return;
  shData = d;
  document.getElementById('sh-total').textContent = d.total;
  document.getElementById('sh-ok').textContent    = d.ok;
  document.getElementById('sh-low').textContent   = d.low;
  document.getElementById('sh-zero').textContent  = d.zero;
  renderHealth();
}

function renderHealth() {
  if (!shData) return;
  const lang   = document.getElementById('sh-lang-f').value;
  const status = document.getElementById('sh-status-f').value;
  const q      = (document.getElementById('sh-search').value || '').toLowerCase();

  const rows = shData.sources.filter(r => {
    if (lang   && r.lang !== lang)                           return false;
    if (status === 'zero' && r.count !== 0)                  return false;
    if (status === 'low'  && !(r.count > 0 && r.count < 5)) return false;
    if (status === 'ok'   && r.count < 5)                    return false;
    if (q && !r.name.toLowerCase().includes(q)
          && !r.cat.toLowerCase().includes(q))               return false;
    return true;
  });

  if (!rows.length) {
    document.getElementById('sh-tbody').innerHTML =
      '<tr><td colspan="6" style="text-align:center;padding:28px;color:#475569">لا توجد نتائج مطابقة</td></tr>';
    return;
  }

  document.getElementById('sh-tbody').innerHTML = rows.map(r => {
    const cls   = r.count === 0 ? 'zero' : r.count < 5 ? 'low' : 'ok';
    const icon  = r.count === 0 ? '🔴' : r.count < 5 ? '⚠️' : '✅';
    const label = icon + ' ' + (r.count === 0 ? 'صفر' : r.count);
    const flag  = SH_FLAGS[r.lang] || r.lang.toUpperCase();
    return `<tr>
      <td style="font-weight:600;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.name)}">${esc(r.name)}</td>
      <td style="color:#475569;font-size:.82em;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(r.cat)}">${esc(r.cat)}</td>
      <td><span class="sh-lang">${flag} ${r.lang.toUpperCase()}</span></td>
      <td><span class="sh-badge ${cls}">${label}</span></td>
      <td style="color:#64748b;font-size:.82em;direction:ltr;white-space:nowrap">${r.last || '—'}</td>
      <td><a href="${esc(r.url)}" target="_blank" class="lnk" title="${esc(r.url)}">🔗</a></td>
    </tr>`;
  }).join('');
}

// ══ TOAST ══════════════════════════════════════════════════════════════════════
function toast(msg, type) {
  const t = Object.assign(document.createElement('div'), {textContent: msg});
  const bg = type==='fail' ? '#ef4444' : '#22c55e';
  Object.assign(t.style, {position:'fixed',bottom:'24px',left:'24px',background:bg,
    color:'#fff',padding:'11px 18px',borderRadius:'8px',fontFamily:'inherit',
    fontSize:'.85em',zIndex:'9999',boxShadow:'0 4px 16px rgba(0,0,0,.3)',maxWidth:'280px',
    transition:'opacity .4s'});
  document.body.appendChild(t);
  setTimeout(()=>{ t.style.opacity='0'; setTimeout(()=>t.remove(),400); }, 2800);
}
</script>
</body>
</html>"""


def main():
    port   = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = ThreadingHTTPServer(("127.0.0.1", port), AdminHandler)
    url    = f"http://127.0.0.1:{port}"
    logger.info("Admin panel: %s  (password: %s)", url, ADMIN_PASSWORD)
    try:   webbrowser.open(url)
    except: pass
    try:   server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped")
        server.server_close()


if __name__ == "__main__":
    main()
