"""SQLite is the canonical archive and settings store; UI process owns writes."""
import json
import sqlite3
import uuid
from pathlib import Path

from .config import Settings


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.db.close()
            raise ValueError("Base créée par une version plus récente de JARVIS.")
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    updated TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL, model TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('complete','streaming','cancelled','error','interrupted')),
                    created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
                CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id,id);
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                PRAGMA user_version=1;
            """)
            self.db.execute("UPDATE messages SET status='interrupted' WHERE status='streaming'")

    def close(self):
        self.db.close()

    def settings(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='profile'").fetchone()
        return Settings(**json.loads(row[0])).validate() if row else Settings()

    def save_settings(self, settings):
        settings.validate()
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES ('profile',?)",
                            (json.dumps(settings.to_dict(), ensure_ascii=False),))

    def sessions(self):
        return self.db.execute("SELECT * FROM sessions ORDER BY updated DESC, rowid DESC").fetchall()

    def new_session(self):
        sid = uuid.uuid4().hex
        with self.db:
            self.db.execute("INSERT INTO sessions(id,title) VALUES (?,?)", (sid, "Nouvelle conversation"))
        return sid

    def messages(self, sid):
        return self.db.execute("SELECT * FROM messages WHERE session_id=? ORDER BY id", (sid,)).fetchall()

    def context(self, sid):
        # Failed/cancelled turns are archived, but never silently treated as complete.
        rows = self.messages(sid)
        result = []
        for i in range(0, len(rows) - 1, 2):
            user, assistant = rows[i:i + 2]
            if user["role"] == "user" and assistant["role"] == "assistant" and assistant["status"] == "complete":
                result.extend({"role": r["role"], "content": r["content"]} for r in (user, assistant))
        return result

    def begin_turn(self, sid, text, model):
        with self.db:
            self.db.execute("INSERT INTO messages(session_id,role,content,status) VALUES (?,'user',?,'complete')", (sid, text))
            cur = self.db.execute("INSERT INTO messages(session_id,role,content,model,status) VALUES (?,'assistant','',?,'streaming')", (sid, model))
            self.db.execute("UPDATE sessions SET title=CASE WHEN title='Nouvelle conversation' THEN ? ELSE title END, updated=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (text.replace('\n', ' ')[:60], sid))
            return cur.lastrowid

    def update_response(self, mid, content, status="streaming"):
        with self.db:
            self.db.execute("UPDATE messages SET content=?,status=? WHERE id=?", (content, status, mid))

    def delete_session(self, sid):
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE id=?", (sid,))
