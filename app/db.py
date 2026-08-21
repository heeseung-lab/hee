import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.getenv("DATABASE_PATH", "data/reviews.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS stores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  address TEXT NOT NULL DEFAULT '',
  place_id TEXT,
  place_type TEXT,
  last_status TEXT NOT NULL DEFAULT 'pending',
  last_error TEXT,
  last_checked_at TEXT,
  UNIQUE(name, address)
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id INTEGER NOT NULL,
  external_id TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT,
  rating REAL,
  bad_hits TEXT NOT NULL DEFAULT '',
  good_hits TEXT NOT NULL DEFAULT '',
  score INTEGER NOT NULL DEFAULT 0,
  level TEXT NOT NULL DEFAULT '정상',
  collected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(store_id, external_id),
  FOREIGN KEY(store_id) REFERENCES stores(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS keywords (
  kind TEXT NOT NULL,
  word TEXT NOT NULL,
  PRIMARY KEY(kind, word)
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  stores_total INTEGER NOT NULL DEFAULT 0,
  stores_ok INTEGER NOT NULL DEFAULT 0,
  stores_failed INTEGER NOT NULL DEFAULT 0,
  new_reviews INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'running'
);
CREATE TABLE IF NOT EXISTS review_actions (
  review_id INTEGER PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'open',
  memo TEXT NOT NULL DEFAULT '',
  assignee TEXT NOT NULL DEFAULT '',
  updated_by TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(review_id) REFERENCES reviews(id) ON DELETE CASCADE
);
"""

DEFAULT_BAD = ["불친절", "맛없", "별로", "최악", "위생", "더럽", "머리카락", "늦", "오래 걸", "짜증", "불쾌", "실망", "비싸"]
DEFAULT_GOOD = ["친절", "맛있", "추천", "깨끗", "만족", "좋아요", "재방문", "최고"]


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA)
        for word in DEFAULT_BAD:
            con.execute("INSERT OR IGNORE INTO keywords(kind, word) VALUES('bad', ?)", (word,))
        for word in DEFAULT_GOOD:
            con.execute("INSERT OR IGNORE INTO keywords(kind, word) VALUES('good', ?)", (word,))
        con.commit()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
    finally:
        con.close()


def get_keywords():
    with connect() as con:
        rows = con.execute("SELECT kind, word FROM keywords ORDER BY kind, word").fetchall()
    return {
        "bad": [r["word"] for r in rows if r["kind"] == "bad"],
        "good": [r["word"] for r in rows if r["kind"] == "good"],
    }


def replace_keywords(kind: str, words: list[str]):
    if kind not in {"bad", "good"}:
        raise ValueError("kind must be bad or good")
    cleaned = sorted({w.strip() for w in words if w and w.strip()})
    with connect() as con:
        con.execute("DELETE FROM keywords WHERE kind=?", (kind,))
        con.executemany("INSERT INTO keywords(kind, word) VALUES(?, ?)", [(kind, w) for w in cleaned])
        con.commit()


def reanalyze_all(analyzer):
    keys = get_keywords()
    with connect() as con:
        rows = con.execute("SELECT id, body FROM reviews").fetchall()
        for row in rows:
            result = analyzer(row["body"], keys["bad"], keys["good"])
            con.execute(
                "UPDATE reviews SET bad_hits=?, good_hits=?, score=?, level=? WHERE id=?",
                (",".join(result.bad_hits), ",".join(result.good_hits), result.score, result.level, row["id"]),
            )
        con.commit()
    return len(rows)


def upsert_store(name: str, address: str = "") -> int:
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO stores(name, address) VALUES(?, ?)", (name, address))
        row = con.execute("SELECT id FROM stores WHERE name=? AND address=?", (name, address)).fetchone()
        con.commit()
        return int(row["id"])


def list_stores():
    with connect() as con:
        return [dict(r) for r in con.execute("""
          SELECT s.*,
                 COUNT(r.id) AS review_count,
                 SUM(CASE WHEN r.bad_hits <> '' THEN 1 ELSE 0 END) AS bad_review_count,
                 SUM(CASE WHEN r.bad_hits <> '' AND COALESCE(a.status,'open') <> 'done' THEN 1 ELSE 0 END) AS open_bad_count,
                 COALESCE(MAX(r.score), 0) AS max_score
          FROM stores s
          LEFT JOIN reviews r ON r.store_id=s.id
          LEFT JOIN review_actions a ON a.review_id=r.id
          GROUP BY s.id
          ORDER BY open_bad_count DESC, max_score DESC, bad_review_count DESC, s.name
        """).fetchall()]


def save_review(store_id: int, external_id: str, body: str, created_at, rating, bad_hits, good_hits, score: int, level: str) -> bool:
    with connect() as con:
        cur = con.execute("""
          INSERT OR IGNORE INTO reviews(store_id, external_id, body, created_at, rating, bad_hits, good_hits, score, level)
          VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (store_id, external_id, body, created_at, rating, ",".join(bad_hits), ",".join(good_hits), score, level))
        con.commit()
        return cur.rowcount > 0


def update_store_result(store_id: int, status: str, error: str | None, place_id: str | None = None, place_type: str | None = None):
    with connect() as con:
        con.execute("""
          UPDATE stores SET last_status=?, last_error=?, place_id=COALESCE(?, place_id), place_type=COALESCE(?, place_type), last_checked_at=CURRENT_TIMESTAMP
          WHERE id=?
        """, (status, error, place_id, place_type, store_id))
        con.commit()


def recent_reviews(limit: int = 100):
    with connect() as con:
        rows = con.execute("""
          SELECT r.*, s.name AS store_name, s.address AS store_address,
                 COALESCE(a.status,'open') AS action_status,
                 COALESCE(a.memo,'') AS action_memo,
                 COALESCE(a.assignee,'') AS assignee,
                 COALESCE(a.updated_by,'') AS action_updated_by,
                 a.updated_at AS action_updated_at
          FROM reviews r
          JOIN stores s ON s.id=r.store_id
          LEFT JOIN review_actions a ON a.review_id=r.id
          ORDER BY CASE WHEN r.bad_hits <> '' AND COALESCE(a.status,'open') <> 'done' THEN 0 ELSE 1 END,
                   r.score DESC, r.collected_at DESC, r.id DESC LIMIT ?
        """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def set_review_action(review_id: int, status: str, memo: str, assignee: str, updated_by: str):
    if status not in {"open", "in_progress", "done"}:
        raise ValueError("invalid status")
    with connect() as con:
        exists = con.execute("SELECT id FROM reviews WHERE id=?", (review_id,)).fetchone()
        if not exists:
            raise KeyError("review not found")
        con.execute("""
          INSERT INTO review_actions(review_id,status,memo,assignee,updated_by,updated_at)
          VALUES(?,?,?,?,?,CURRENT_TIMESTAMP)
          ON CONFLICT(review_id) DO UPDATE SET
            status=excluded.status, memo=excluded.memo, assignee=excluded.assignee,
            updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP
        """, (review_id, status, memo.strip(), assignee.strip(), updated_by))
        con.commit()


def dashboard_summary():
    with connect() as con:
        row = con.execute("""
          SELECT
            (SELECT COUNT(*) FROM stores) AS stores,
            (SELECT COUNT(*) FROM reviews) AS reviews,
            (SELECT COUNT(*) FROM reviews WHERE bad_hits <> '') AS bad_reviews,
            (SELECT COUNT(*) FROM reviews r LEFT JOIN review_actions a ON a.review_id=r.id WHERE r.bad_hits <> '' AND COALESCE(a.status,'open') <> 'done') AS open_bad_reviews,
            (SELECT COUNT(DISTINCT store_id) FROM reviews WHERE level='집중관리') AS critical_stores,
            (SELECT COUNT(DISTINCT store_id) FROM reviews WHERE level='주의') AS warning_stores
        """).fetchone()
    return dict(row)
