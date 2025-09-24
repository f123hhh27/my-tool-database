#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Personal Tools DB CLI (SQLite + CSV)

欄位設計（CSV 與 SQLite 同步）：
- name          : 工具/套件名稱（PRIMARY KEY）
- language      : 程式語言（e.g., Python, Go, JavaScript）
- version       : 版本（e.g., 3.11, 1.7.6, ES6）
- platform      : 平台/環境（e.g., Linux, Windows, macOS, Colab, Docker）
- purpose       : 一句話主要用途
- link          : 官方文件/筆記/GitHub 連結
- tags          : 逗號分隔的標籤（建議小寫單數，如: etl,data,viz）
- snippet_path  : 對應 repo 中檔案（e.g., snippets/xxx.py）
- notes         : 備註
- created_at    : 建立時間（ISO8601 UTC, e.g., 2025-09-25T09:12:00Z）
- updated_at    : 最後更新時間（ISO8601 UTC）

子指令：
- init                         : 初始化資料庫（建立 data/tools.db 與資料表）
- add                          : 新增/更新一筆（upsert）
- list                         : 列出全部
- find                         : 查詢（支援關鍵字/標籤/平台/語言/版本）
- export-csv <path>            : 匯出成 CSV
- import-csv <path>            : 從 CSV 匯入（upsert by name）
- make-csv-template [--path ...] [--with-example]
                               : 產生 CSV 標頭（可選擇含示範列）
"""

import argparse
import csv
import os
import sqlite3
from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo

# 專案根目錄 = 本檔所在目錄的上一層
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(ROOT, "data", "tools.db")

# CSV 欄位（順序同 export）
CSV_HEADERS = [
    "name", "language", "version", "platform", "purpose", "link",
    "tags", "snippet_path", "notes", "created_at", "updated_at"
]

# ---------- 基礎工具 ----------

def _ensure_data_dir():
    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)

def conn():
    _ensure_data_dir()
    return sqlite3.connect(DB_PATH)

def _now_iso_utc():
    # 例：2025-09-25T09:12:00Z（UTC）
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------- 清洗 / 正規化 ----------

_WHITESPACE_RE = re.compile(r"\s+")
_NAME_SAFE_RE = re.compile(r"[^a-z0-9_-]+")

LANGUAGE_MAP = {
    "py": "Python",
    "python": "Python",
    "golang": "Go",
    "go": "Go",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "bash": "Bash",
    "shell": "Bash",
}

PLATFORM_MAP = {
    "google colaboratory": "Colab",
    "google colab": "Colab",
    "colab": "Colab",
    "linux": "Linux",
    "windows": "Windows",
    "win": "Windows",
    "mac": "macOS",
    "macos": "macOS",
    "osx": "macOS",
    "docker": "Docker",
}

def _collapse_ws(s: str) -> str:
    return _WHITESPACE_RE.sub(" ", s.strip())

def _slugify_name(name: str) -> str:
    s = name.strip().lower()
    s = s.replace(" ", "_")
    s = _NAME_SAFE_RE.sub("", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unnamed"

def _normalize_language(s: str) -> str:
    key = s.strip().lower()
    return LANGUAGE_MAP.get(key, s.strip().title() if s else "")

def _normalize_platform(s: str) -> str:
    key = s.strip().lower()
    return PLATFORM_MAP.get(key, _collapse_ws(s)) if s else ""

def _normalize_version(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    s = s.lstrip("vV").strip()
    s = _collapse_ws(s)
    return s

def _normalize_tags(s: str) -> str:
    if not s:
        return ""
    # 允許以逗號、分號或空白切割
    parts = re.split(r"[,\s;]+", s)
    parts = [p.strip().lower() for p in parts if p.strip()]
    # 去重 + 排序（字母序，確保一致）
    parts = sorted(set(parts))
    return ",".join(parts)

def _normalize_link(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    # 若像是網址但缺 http，幫補（簡易檢查）
    if re.match(r"^[a-zA-Z]+://", s):
        return s
    if re.match(r"^(www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$", s):
        return "https://" + s.lstrip("/")
    return _collapse_ws(s)

def _normalize_path(p: str) -> str:
    if not p:
        return ""
    # 標準化斜線與 .. 等
    norm = os.path.normpath(p.strip())
    # 若在專案底下就存成相對路徑（可讀性佳、可移植）
    try:
        abs_root = os.path.abspath(ROOT)
        abs_path = os.path.abspath(norm)
        if abs_path.startswith(abs_root + os.sep):
            return os.path.relpath(abs_path, abs_root).replace("\\", "/")
    except Exception:
        pass
    return norm.replace("\\", "/")

def _normalize_iso_utc(s: str) -> str:
    """把外部提供的時間嘗試矯正為 ISO8601 UTC（秒級），否則回空字串交給系統自動補。"""
    if not s or not s.strip():
        return ""
    s = s.strip()
    # 常見格式：YYYY-MM-DD HH:MM:SS / 含 T / 含 Z / 含時區
    try:
        # 先嘗試 fromisoformat（不支援 Z，要先去掉 Z）
        z = s.endswith("Z")
        base = s[:-1] if z else s
        dt = datetime.fromisoformat(base.replace(" ", "T"))
        # 若含偏移時區，轉成 UTC
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.replace(microsecond=0).isoformat() + "Z"
    except Exception:
        # 最後再嘗試幾種簡單樣式
        for fmt in ("%Y-%m-%d %H:%M:%S",
                    "%Y/%m/%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                return dt.replace(microsecond=0).isoformat() + "Z"
            except Exception:
                continue
    # 失敗就清空，交由系統自動補
    return ""

def _utc_to_taipei_str(utc_str: str) -> str:
    """把 'YYYY-MM-DDTHH:MM:SSZ' 轉成台北時間的易讀字串。輸入為空就回空。"""
    if not utc_str:
        return ""
    # 將 Z 轉為 +00:00，讓 fromisoformat 可解析
    dt_utc = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    dt_tpe = dt_utc.astimezone(ZoneInfo("Asia/Taipei"))
    # 你想顯示成什麼樣都可以；這裡用常見格式
    return dt_tpe.strftime("%Y-%m-%d %H:%M:%S %Z")  # 例如：2025-09-25 18:00:00 CST

def normalize_row(row: dict) -> dict:
    """回傳一份**新的** row（不就地修改），套用清洗規則。"""
    out = dict(row)  # copy

    # 統一去除前後空白 + 壓縮空白
    for k, v in list(out.items()):
        if isinstance(v, str):
            out[k] = _collapse_ws(v)

    # name
    if out.get("name"):
        out["name"] = _slugify_name(out["name"])

    # language / platform / version
    out["language"] = _normalize_language(out.get("language", ""))
    out["platform"] = _normalize_platform(out.get("platform", ""))
    out["version"]  = _normalize_version(out.get("version", ""))

    # tags
    out["tags"] = _normalize_tags(out.get("tags", ""))

    # link
    out["link"] = _normalize_link(out.get("link", ""))

    # snippet_path
    out["snippet_path"] = _normalize_path(out.get("snippet_path", ""))

    # purpose / notes 再壓一次空白（避免多空白）
    out["purpose"] = _collapse_ws(out.get("purpose", ""))
    out["notes"]   = _collapse_ws(out.get("notes", ""))

    # 若外部有提供 created_at / updated_at，嘗試轉成 ISO8601 UTC（否則留空給邏輯自動補）
    out["created_at"] = _normalize_iso_utc(out.get("created_at", ""))
    out["updated_at"] = _normalize_iso_utc(out.get("updated_at", ""))

    return out

# ---------- DB Schema 與初始化 ----------

def init_db():
    """初始化 SQLite 資料庫與資料表（若不存在就建立）"""
    with conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS tools (
            name         TEXT PRIMARY KEY,
            language     TEXT,
            version      TEXT,
            platform     TEXT,
            purpose      TEXT,
            link         TEXT,
            tags         TEXT,
            snippet_path TEXT,
            notes        TEXT,
            created_at   TEXT,
            updated_at   TEXT
        )
        """)
    print("Database initialized at:", DB_PATH)

def _get_existing_created_at(name: str):
    with conn() as c:
        row = c.execute("SELECT created_at FROM tools WHERE name = ?", (name,)).fetchone()
        return row[0] if row and row[0] else None

# ---------- Upsert / List / Find ----------

def upsert_tool(row: dict):
    """
    新增或更新（以 name 為主鍵）。
    - 若無 created_at：新建或沿用舊值；updated_at 一律更新為現在時間。
    - 未提供的欄位自動補空字串。
    """
    defaults = {
        "language": "", "version": "", "platform": "", "purpose": "",
        "link": "", "tags": "", "snippet_path": "", "notes": ""
    }
    for k, v in defaults.items():
        row.setdefault(k, v)

    now = _now_iso_utc()
    created = row.get("created_at") or _get_existing_created_at(row["name"]) or now
    updated = now

    # 確保 updated 不早於 created（避免 CSV 給未來時間時出現倒退）
    if updated < created:
        updated = created

    with conn() as c:
        c.execute("""
        INSERT INTO tools (
            name, language, version, platform, purpose, link,
            tags, snippet_path, notes, created_at, updated_at
        )
        VALUES (
            :name, :language, :version, :platform, :purpose, :link,
            :tags, :snippet_path, :notes, :created_at, :updated_at
        )
        ON CONFLICT(name) DO UPDATE SET
            language     = excluded.language,
            version      = excluded.version,
            platform     = excluded.platform,
            purpose      = excluded.purpose,
            link         = excluded.link,
            tags         = excluded.tags,
            snippet_path = excluded.snippet_path,
            notes        = excluded.notes,
            updated_at   = excluded.updated_at
        """, {
            "name": row["name"],
            "language": row.get("language", ""),
            "version": row.get("version", ""),
            "platform": row.get("platform", ""),
            "purpose": row.get("purpose", ""),
            "link": row.get("link", ""),
            "tags": row.get("tags", ""),
            "snippet_path": row.get("snippet_path", ""),
            "notes": row.get("notes", ""),
            "created_at": created,
            "updated_at": updated
        })
    created_tpe = _utc_to_taipei_str(created)
    updated_tpe = _utc_to_taipei_str(updated)
    print(f"Upserted: {row['name']} (created_at={created_tpe}, updated_at={updated_tpe})")

def list_tools():
    """列出所有工具"""
    with conn() as c:
        cur = c.execute(f"SELECT {','.join(CSV_HEADERS)} FROM tools ORDER BY name")
        rows = cur.fetchall()
        if not rows:
            print("(empty)")
            return
        for r in rows:
            (name, language, version, platform, purpose, link,
             tags, snippet_path, notes, created_at, updated_at) = r
            print(f"- {name} | lang={language} {version} | plat={platform} | tags={tags}")
            if purpose:      print(f"  purpose: {purpose}")
            if link:         print(f"  link:    {link}")
            if snippet_path: print(f"  snippet: {snippet_path}")
            if notes:        print(f"  notes:   {notes}")
            created_tpe = _utc_to_taipei_str(created_at)
            updated_tpe = _utc_to_taipei_str(updated_at)
            print(f"  created: {created_tpe} ({created_at}) | updated: {updated_tpe} ({updated_at})\n")


def find_tools(q=None, tag=None, platform=None, language=None, version=None):
    """依條件查詢（q 會同時比對 name/purpose/link/notes）"""
    query = f"SELECT {','.join(CSV_HEADERS)} FROM tools WHERE 1=1"
    params = {}
    if q:
        query += " AND (name LIKE :q OR purpose LIKE :q OR link LIKE :q OR notes LIKE :q)"
        params["q"] = f"%{q}%"
    if tag:
        query += " AND (','||lower(tags)||',' LIKE :tag)"
        params["tag"] = f"%,{tag.lower()},%"
    if platform:
        query += " AND lower(platform) LIKE :platform"
        params["platform"] = f"%{platform.lower()}%"
    if language:
        query += " AND lower(language) LIKE :language"
        params["language"] = f"%{language.lower()}%"
    if version:
        query += " AND version LIKE :version"
        params["version"] = f"%{version}%"
    query += " ORDER BY name"

    with conn() as c:
        rows = c.execute(query, params).fetchall()
        if not rows:
            print("(no results)")
            return
        for r in rows:
            (name, lang, ver, plat, purpose, link,
             tags, snip, notes, created, updated) = r
            print(f"- {name} | lang={lang} {ver} | plat={plat} | tags={tags}")
            if purpose: print(f"  purpose: {purpose}")
            if link:    print(f"  link:    {link}")
            if snip:    print(f"  snippet: {snip}")
            if notes:   print(f"  notes:   {notes}")
            created_tpe = _utc_to_taipei_str(created)
            updated_tpe = _utc_to_taipei_str(updated)
            print(f"  created: {created_tpe} ({created}) | updated: {updated_tpe} ({updated})\n")


# ---------- 匯入 / 匯出 CSV ----------

def export_csv(path: str):
    """匯出所有工具成 CSV（含 created_at / updated_at）"""
    # 建立上層資料夾（若不存在）
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with conn() as c, open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        for row in c.execute(f"SELECT {','.join(CSV_HEADERS)} FROM tools ORDER BY name"):
            writer.writerow(row)
    print("Exported to:", path)

def import_csv(path: str):
    count = 0
    # 1) 用 utf-8-sig 自動去掉 BOM
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            # 2) 鍵名去空白 + 去 BOM；值去空白
            base = {
                ((k.strip().lstrip("\ufeff")) if k else k): (v.strip() if isinstance(v, str) else v)
                for k, v in row.items()
            }

            if not base.get("name"):
                print("Skipped a row without 'name'")
                continue

            for h in CSV_HEADERS:
                base.setdefault(h, "")

            normalized = normalize_row(base)

            if not normalized.get("created_at"):
                normalized["created_at"] = _now_iso_utc()
            normalized["updated_at"] = _now_iso_utc()

            upsert_tool(normalized)
            count += 1

    print(f"Imported {count} rows from {path}")


# ---------- 產生 CSV 模板 ----------

def make_csv_template(path: str, with_example: bool = False):
    """
    產生 CSV 標頭；若 --with-example，會加入一列示範資料。
    預設輸出：data/tools.csv
    """
    # 若給的是資料夾，則輸出到該資料夾下的 tools.csv
    out_path = path
    if os.path.isdir(out_path):
        out_path = os.path.join(out_path, "tools.csv")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)
        if with_example:
            now = _now_iso_utc()
            writer.writerow([
                "example-tool", "Python", "3.11", "Linux/Colab",
                "示範用途", "https://example.com", "demo,template",
                "snippets/example_snippet.py", "這是一筆示範資料，請自行刪除或覆蓋",
                now, now
            ])
    print("CSV template written to:", out_path)

# ---------- CLI 入口 ----------

def main():
    parser = argparse.ArgumentParser(description="Personal Tools DB (SQLite-backed)")
    sub = parser.add_subparsers(dest="cmd")

    # init
    sub.add_parser("init", help="Initialize database")

    # add
    p_add = sub.add_parser("add", help="Add or update a tool (upsert)")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--language")
    p_add.add_argument("--version")
    p_add.add_argument("--platform")
    p_add.add_argument("--purpose")
    p_add.add_argument("--link")
    p_add.add_argument("--tags")
    p_add.add_argument("--snippet-path", dest="snippet_path")
    p_add.add_argument("--notes")

    # list
    sub.add_parser("list", help="List all tools")

    # find
    p_find = sub.add_parser("find", help="Find tools by keywords/filter")
    p_find.add_argument("--q")
    p_find.add_argument("--tag")
    p_find.add_argument("--platform")
    p_find.add_argument("--language")
    p_find.add_argument("--version")

    # export
    p_export = sub.add_parser("export-csv", help="Export tools to CSV")
    p_export.add_argument("path")

    # import
    p_import = sub.add_parser("import-csv", help="Import tools from CSV (upsert by name)")
    p_import.add_argument("path")

    # make-csv-template
    p_tpl = sub.add_parser("make-csv-template", help="Create a CSV template with headers")
    p_tpl.add_argument("--path", default=os.path.join(ROOT, "data", "tools.csv"),
                       help="輸出檔路徑或資料夾（預設 data/tools.csv）")
    p_tpl.add_argument("--with-example", action="store_true",
                       help="同時加入一列示範資料")

    args = parser.parse_args()

    if args.cmd == "init":
        init_db()

    elif args.cmd == "add":
        init_db()
        # 收集欄位；None → ""
        row = {
            "name": args.name,
            "language": args.language or "",
            "version": args.version or "",
            "platform": args.platform or "",
            "purpose": args.purpose or "",
            "link": args.link or "",
            "tags": args.tags or "",
            "snippet_path": args.snippet_path or "",
            "notes": args.notes or ""
        }
        row = normalize_row(row)
        upsert_tool(row)

    elif args.cmd == "list":
        init_db()
        list_tools()

    elif args.cmd == "find":
        init_db()
        find_tools(
            q=args.q,
            tag=args.tag,
            platform=args.platform,
            language=args.language,
            version=args.version
        )

    elif args.cmd == "export-csv":
        init_db()
        export_csv(args.path)

    elif args.cmd == "import-csv":
        init_db()
        import_csv(args.path)

    elif args.cmd == "make-csv-template":
        # 這個不需要 DB，也可以直接用
        make_csv_template(args.path, with_example=args.with_example)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
