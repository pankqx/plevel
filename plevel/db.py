"""SQLite storage for chats and messages."""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path


def default_db_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    folder = base / "plevel"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "chats.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT 'New chat',
    model TEXT NOT NULL DEFAULT '',
    system_prompt TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
"""


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or default_db_path())
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        cols = [r["name"] for r in self.conn.execute("PRAGMA table_info(chats)")]
        if "project" not in cols:  # migrate older databases
            self.conn.execute("ALTER TABLE chats ADD COLUMN project TEXT NOT NULL DEFAULT ''")
        self.conn.commit()

    # ---- chats -------------------------------------------------------
    def create_chat(self, model: str = "", system_prompt: str = "", title: str = "New chat",
                    project: str = "") -> int:
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO chats (title, model, system_prompt, project, created, updated) "
            "VALUES (?,?,?,?,?,?)",
            (title, model, system_prompt, project, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_chats(self, search: str = "") -> list[sqlite3.Row]:
        if search.strip():
            like = f"%{search.strip()}%"
            return self.conn.execute(
                """SELECT DISTINCT c.* FROM chats c
                   LEFT JOIN messages m ON m.chat_id = c.id
                   WHERE c.title LIKE ? OR m.content LIKE ?
                   ORDER BY c.updated DESC""",
                (like, like),
            ).fetchall()
        return self.conn.execute("SELECT * FROM chats ORDER BY updated DESC").fetchall()

    def get_chat(self, chat_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)).fetchone()

    def update_chat(self, chat_id: int, **fields) -> None:
        allowed = {"title", "model", "system_prompt", "project"}
        cols = [k for k in fields if k in allowed]
        if not cols:
            return
        sets = ", ".join(f"{c} = ?" for c in cols)
        self.conn.execute(
            f"UPDATE chats SET {sets}, updated = ? WHERE id = ?",
            [fields[c] for c in cols] + [time.time(), chat_id],
        )
        self.conn.commit()

    def delete_chat(self, chat_id: int) -> None:
        self.conn.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        self.conn.commit()

    # ---- messages ----------------------------------------------------
    def add_message(self, chat_id: int, role: str, content: str) -> int:
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO messages (chat_id, role, content, created) VALUES (?,?,?,?)",
            (chat_id, role, content, now),
        )
        self.conn.execute("UPDATE chats SET updated = ? WHERE id = ?", (now, chat_id))
        self.conn.commit()
        return int(cur.lastrowid)

    def get_messages(self, chat_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY id", (chat_id,)
        ).fetchall()

    def delete_last_message(self, chat_id: int) -> None:
        self.conn.execute(
            "DELETE FROM messages WHERE id = (SELECT MAX(id) FROM messages WHERE chat_id = ?)",
            (chat_id,),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
