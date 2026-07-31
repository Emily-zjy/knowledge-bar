"""SQLite-backed mind map storage.

Replaces the in-memory dict for S9D persistence across restarts.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "mindmaps.db"
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
    return conn


def init_db() -> None:
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mindmaps (
            task_id TEXT PRIMARY KEY,
            user_id TEXT,
            title TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'processing',
            raw_text TEXT NOT NULL,
            generation_params TEXT NOT NULL DEFAULT '{}',
            draft_json TEXT,
            render_json TEXT,
            validation_json TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()


def save(
    task_id: str,
    user_id: str | None,
    title: str,
    status: str,
    raw_text: str,
    generation_params: dict,
    draft_json: dict | None,
    render_json: dict | None,
    validation_json: dict | None,
    error_message: str | None,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO mindmaps
           (task_id, user_id, title, status, raw_text, generation_params,
            draft_json, render_json, validation_json, error_message,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            user_id,
            title,
            status,
            raw_text,
            json.dumps(generation_params, ensure_ascii=False),
            json.dumps(draft_json, ensure_ascii=False) if draft_json else None,
            json.dumps(render_json, ensure_ascii=False) if render_json else None,
            json.dumps(validation_json, ensure_ascii=False) if validation_json else None,
            error_message,
            created_at.isoformat(),
            updated_at.isoformat(),
        ),
    )
    conn.commit()


def get(task_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM mindmaps WHERE task_id = ?", (task_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_dict(row)


def list_by_user(user_id: str | None) -> list[dict]:
    conn = _get_conn()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM mindmaps WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM mindmaps WHERE user_id IS NULL ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def update_draft_and_render(
    task_id: str,
    title: str,
    draft_json: dict,
    render_json: dict,
    updated_at: datetime,
) -> None:
    conn = _get_conn()
    conn.execute(
        """UPDATE mindmaps
           SET title = ?, draft_json = ?, render_json = ?, updated_at = ?
           WHERE task_id = ?""",
        (
            title,
            json.dumps(draft_json, ensure_ascii=False),
            json.dumps(render_json, ensure_ascii=False),
            updated_at.isoformat(),
            task_id,
        ),
    )
    conn.commit()


def delete(task_id: str, user_id: str | None) -> bool:
    conn = _get_conn()
    if user_id:
        cur = conn.execute(
            "DELETE FROM mindmaps WHERE task_id = ? AND user_id = ?",
            (task_id, user_id),
        )
    else:
        cur = conn.execute("DELETE FROM mindmaps WHERE task_id = ?", (task_id,))
    conn.commit()
    return cur.rowcount > 0


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("generation_params", "draft_json", "render_json", "validation_json"):
        if d.get(field):
            d[field] = json.loads(d[field])
    return d
