"""SQLite is the canonical archive and settings store; UI process owns writes."""
import json
import sqlite3
import uuid
from pathlib import Path

from .config import Settings


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.migration_backup = None
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise ValueError("Base créée par une version plus récente de JARVIS.")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA journal_mode=WAL")
            if version == 1:
                self.migration_backup = self._backup_v1(path)
            # DDL needs an explicit transaction; executescript would commit it.
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                if version == 1:
                    self.db.execute("ALTER TABLE messages ADD COLUMN source TEXT NOT NULL DEFAULT 'text' CHECK(source IN ('text','voice'))")
                    self.db.execute("ALTER TABLE messages ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'")
                self._create_schema()
                self.db.execute("UPDATE messages SET status='interrupted' WHERE status='streaming'")
                self.db.execute("PRAGMA user_version=2")
        except Exception:
            self.db.close()
            raise

    def _backup_v1(self, path):
        backup_path = Path(str(path) + ".v1-backup.sqlite3")
        if backup_path.exists():
            backup_path = Path(str(path) + ".v1-backup-" + uuid.uuid4().hex + ".sqlite3")
        # Reserve a fresh file: never overwrite a previous migration backup.
        backup_path.touch(exist_ok=False)
        try:
            backup = sqlite3.connect(backup_path)
            try:
                self.db.backup(backup)
            finally:
                backup.close()
        except Exception:
            backup_path.unlink()
            raise
        return backup_path

    def _create_schema(self):
        statements = (
                """CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    updated TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""",
                """CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                    content TEXT NOT NULL, model TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('complete','streaming','cancelled','error','interrupted')),
                    created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    source TEXT NOT NULL DEFAULT 'text' CHECK(source IN ('text','voice')),
                    metadata TEXT NOT NULL DEFAULT '{}')""",
                "CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id,id)",
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        )
        for statement in statements:
            self.db.execute(statement)

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

    def get_preference(self, key, default=None):
        row = self.db.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_preference(self, key, value):
        encoded = _json(value)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO preferences(key,value) VALUES (?,?)",
                            (key, encoded))

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
        return [{"role": row["role"], "content": row["content"]}
                for row in self.context_records(sid)]

    def message(self, mid):
        """Read the canonical original for a context provenance reference."""
        return self.db.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()

    def context_records(self, sid):
        # Failed/cancelled turns are archived, but never silently treated as complete.
        rows = self.messages(sid)
        result = []
        for i in range(0, len(rows) - 1, 2):
            user, assistant = rows[i:i + 2]
            if user["role"] == "user" and assistant["role"] == "assistant" and assistant["status"] == "complete":
                result.extend({key: row[key] for key in ("id", "session_id", "role", "content", "created")}
                              for row in (user, assistant))
        return result

    def begin_turn(self, sid, text, model, source="text", metadata=None):
        if source not in {"text", "voice"}:
            raise ValueError("La provenance doit être textuelle ou vocale.")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("Les métadonnées doivent être un objet JSON.")
        encoded = _json(metadata if metadata is not None else {})
        with self.db:
            self.db.execute("INSERT INTO messages(session_id,role,content,model,status,source,metadata) VALUES (?,'user',?,?,'complete',?,?)", (sid, text, model, source, encoded))
            cur = self.db.execute("INSERT INTO messages(session_id,role,content,model,status,source,metadata) VALUES (?,'assistant','',?,'streaming',?,?)", (sid, model, source, encoded))
            self.db.execute("UPDATE sessions SET title=CASE WHEN title='Nouvelle conversation' THEN ? ELSE title END, updated=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?", (text.replace('\n', ' ')[:60], sid))
            return cur.lastrowid

    def update_response(self, mid, content, status="streaming"):
        with self.db:
            self.db.execute("UPDATE messages SET content=?,status=? WHERE id=?", (content, status, mid))

    def update_message_metadata(self, mid, values):
        if not isinstance(values, dict):
            raise ValueError("Les métadonnées doivent être un objet JSON.")
        with self.db:
            row = self.db.execute("SELECT metadata FROM messages WHERE id=?", (mid,)).fetchone()
            if row is None:
                raise ValueError("Message introuvable.")
            metadata = json.loads(row[0])
            metadata.update(values)
            self.db.execute("UPDATE messages SET metadata=? WHERE id=?", (_json(metadata), mid))

    def delete_session(self, sid):
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE id=?", (sid,))
