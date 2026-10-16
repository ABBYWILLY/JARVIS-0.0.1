"""Explicit local memories and lexical archive lookup; never infer new facts."""
import hashlib
import json
import re
import sqlite3
import unicodedata

from .context import _STOP, _words


KINDS = ("durable", "summary", "project", "document")


def _canonical(text):
    return unicodedata.normalize("NFC", text.strip())


def _topic(text):
    return " ".join(_canonical(text).casefold().split())


def _fold(text):
    return "".join(character for character in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(character))


def _fingerprint(kind, content):
    return hashlib.sha256((kind + "\0" + _canonical(content)).encode("utf-8")).hexdigest()


def create_memory_schema(db):
    """Called inside Store's migration transaction; an FTS absence is explicit."""
    db.execute("""CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL CHECK(kind IN ('durable','summary','project','document')),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','disabled')),
        title TEXT NOT NULL DEFAULT '', topic TEXT NOT NULL DEFAULT '', topic_key TEXT NOT NULL DEFAULT '',
        content TEXT NOT NULL CHECK(length(content)>0), provenance TEXT NOT NULL DEFAULT '{}',
        fingerprint TEXT NOT NULL UNIQUE,
        created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
        updated TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
    db.execute("CREATE INDEX IF NOT EXISTS memories_topic ON memories(topic_key,status)")
    trigger_names = [table + suffix for table in ("memories", "messages_final") for suffix in ("_ai", "_ad", "_au")]
    indexed = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name IN (?,?,?,?,?,?)", trigger_names)}
    try:
        db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            title,topic,content,content='memories',content_rowid='id',tokenize='unicode61 remove_diacritics 2')""")
        db.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            content,content='messages',content_rowid='id',tokenize='unicode61 remove_diacritics 2')""")
    except sqlite3.OperationalError as exc:
        if "no such module: fts5" not in str(exc).casefold():
            raise
        # A database may have been created by another SQLite build. Without
        # FTS5, remove index-only triggers so ordinary writes remain possible.
        for name in trigger_names + ["messages_ai", "messages_ad", "messages_au"]:
            db.execute("DROP TRIGGER IF EXISTS " + name)
        return False
    db.execute("""CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
        INSERT INTO memories_fts(rowid,title,topic,content) VALUES(new.id,new.title,new.topic,new.content); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
        INSERT INTO memories_fts(memories_fts,rowid,title,topic,content)
        VALUES('delete',old.id,old.title,old.topic,old.content); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF title,topic,content ON memories BEGIN
        INSERT INTO memories_fts(memories_fts,rowid,title,topic,content)
        VALUES('delete',old.id,old.title,old.topic,old.content);
        INSERT INTO memories_fts(rowid,title,topic,content) VALUES(new.id,new.title,new.topic,new.content); END""")
    if not all("memories" + suffix in indexed for suffix in ("_ai", "_ad", "_au")):
        db.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
    # Index a reply once it is finalized, rather than rewriting its growing
    # FTS document for every streamed fragment. Partial archived replies remain
    # searchable once cancelled, failed or recovered after interruption.
    for name in ("messages_ai", "messages_ad", "messages_au"):
        db.execute("DROP TRIGGER IF EXISTS " + name)
    db.execute("""CREATE TRIGGER IF NOT EXISTS messages_final_ai AFTER INSERT ON messages
        WHEN new.status<>'streaming' BEGIN
        INSERT INTO messages_fts(rowid,content) VALUES(new.id,new.content); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS messages_final_ad AFTER DELETE ON messages
        WHEN old.status<>'streaming' BEGIN
        INSERT INTO messages_fts(messages_fts,rowid,content) VALUES('delete',old.id,old.content); END""")
    db.execute("""CREATE TRIGGER IF NOT EXISTS messages_final_au AFTER UPDATE OF content,status ON messages BEGIN
        INSERT INTO messages_fts(messages_fts,rowid,content)
            SELECT 'delete',old.id,old.content WHERE old.status<>'streaming';
        INSERT INTO messages_fts(rowid,content) SELECT new.id,new.content WHERE new.status<>'streaming'; END""")
    if not all("messages_final" + suffix in indexed for suffix in ("_ai", "_ad", "_au")):
        db.execute("INSERT INTO messages_fts(messages_fts) VALUES('delete-all')")
        db.execute("INSERT INTO messages_fts(rowid,content) SELECT id,content FROM messages WHERE status<>'streaming'")
    return True


class MemoryRepository:
    def __init__(self, db, backup_callback, *, fts_available=True):
        self.db = db
        self.backup_callback = backup_callback
        self.fts_available = fts_available
        # The fallback is still an explicit SQL LIKE scan, with French Unicode
        # case/accent handling; it is not a semantic search or an embedding.
        db.create_function("jarvis_search_fold", 1, _fold, deterministic=True)

    def _values(self, content, kind, title, topic, provenance):
        if kind not in KINDS:
            raise ValueError("Type de souvenir inconnu.")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Le contenu du souvenir ne peut pas être vide.")
        if len(content.encode("utf-8")) > 256 * 1024:
            raise ValueError("Un souvenir ou document est limité à 256 Kio de texte UTF-8.")
        if not isinstance(title, str) or not isinstance(topic, str):
            raise ValueError("Le titre et le sujet du souvenir doivent être du texte.")
        if provenance is not None and not isinstance(provenance, dict):
            raise ValueError("La provenance du souvenir doit être un objet JSON.")
        encoded = json.dumps(provenance or {}, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
        return (kind, title, topic, _topic(topic), content, encoded, _fingerprint(kind, content))

    def _require(self, mid):
        row = self.get(mid)
        if row is None:
            raise ValueError("Souvenir introuvable.")
        return row

    def _duplicate(self, fingerprint, exclude=None):
        row = self.db.execute("SELECT id FROM memories WHERE fingerprint=? AND id<>?",
                              (fingerprint, exclude if exclude is not None else -1)).fetchone()
        if row:
            raise ValueError(f"Ce souvenir existe déjà (#{row['id']}). Aucun doublon n’a été créé.")

    def create(self, content, kind="durable", title="", topic="", provenance=None):
        values = self._values(content, kind, title, topic, provenance)
        self._duplicate(values[-1])
        try:
            with self.db:
                cursor = self.db.execute("""INSERT INTO memories
                    (kind,title,topic,topic_key,content,provenance,fingerprint) VALUES(?,?,?,?,?,?,?)""", values)
                return cursor.lastrowid
        except sqlite3.IntegrityError:
            self._duplicate(values[-1])
            raise

    def get(self, mid):
        if not isinstance(mid, int) or isinstance(mid, bool) or mid < 1:
            raise ValueError("Identifiant de souvenir invalide.")
        return self.db.execute("SELECT * FROM memories WHERE id=?", (mid,)).fetchone()

    def list(self):
        return self.db.execute("SELECT * FROM memories ORDER BY updated DESC,id DESC").fetchall()

    def approve(self, mid, confirmed=False):
        if confirmed is not True:
            raise ValueError("Confirmez explicitement l’approbation de ce souvenir.")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self._require(mid)
            if row["topic_key"]:
                conflicts = self.db.execute("""SELECT id,content FROM memories
                    WHERE status='approved' AND topic_key=? AND id<>?""", (row["topic_key"], mid)).fetchall()
                conflicts = [other["id"] for other in conflicts
                             if _canonical(other["content"]) != _canonical(row["content"])]
                if conflicts:
                    references = ", ".join("#" + str(other) for other in conflicts)
                    raise ValueError(f"Conflit de sujet entre #{mid} et {references} : leurs contenus diffèrent. "
                                     "Corrigez ou désactivez le souvenir précédent avant approbation.")
            self.db.execute("""UPDATE memories SET status='approved',
                updated=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""", (mid,))

    def update(self, mid, content, title="", topic="", provenance=None):
        previous = self._require(mid)
        if provenance is None:
            provenance = json.loads(previous["provenance"])
        values = self._values(content, previous["kind"], title, topic, provenance)
        self._duplicate(values[-1], exclude=mid)
        backup = self.backup_callback("memory-update-" + str(mid))
        try:
            with self.db:
                self.db.execute("""UPDATE memories SET kind=?,title=?,topic=?,topic_key=?,content=?,
                    provenance=?,fingerprint=?,status='pending',updated=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                    WHERE id=?""", (*values, mid))
        except sqlite3.IntegrityError:
            self._duplicate(values[-1], exclude=mid)
            raise
        return backup

    def disable(self, mid):
        self._require(mid)
        with self.db:
            self.db.execute("""UPDATE memories SET status='disabled',
                updated=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?""", (mid,))

    def delete(self, mid, confirmed=False):
        if confirmed is not True:
            raise ValueError("Confirmez explicitement la suppression de ce souvenir.")
        self._require(mid)
        backup = self.backup_callback("memory-delete-" + str(mid))
        with self.db:
            self.db.execute("DELETE FROM memories WHERE id=?", (mid,))
        return backup

    def _terms(self, query, limit):
        if not isinstance(query, str):
            raise ValueError("La recherche doit être du texte.")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("La recherche doit demander entre 1 et 100 résultats.")
        useful = _words(query)
        terms = [term for term in re.findall(r"[^\W_]+", query)
                 if _fold(term) in useful or (term.isdigit() and len(term) >= 2)
                 or (2 <= len(term) <= 5 and term.isupper() and _fold(term) not in _STOP)]
        return list(dict.fromkeys(terms))[:32]

    def search(self, query, limit=5, approved_only=True):
        terms = self._terms(query, limit)
        if not terms:
            return []
        status = " AND m.status='approved'" if approved_only else ""
        if self.fts_available:
            match = " OR ".join('"' + term + '"' for term in terms)
            rows = self.db.execute("""SELECT m.* FROM memories_fts JOIN memories m ON m.id=memories_fts.rowid
                WHERE memories_fts MATCH ?""" + status + " ORDER BY bm25(memories_fts,2,3,1),m.id DESC LIMIT ?",
                                   (match, limit)).fetchall()
        else:
            columns = ("title", "topic", "content")
            conditions = ["jarvis_search_fold(m." + column + ") LIKE ?" for term in terms for column in columns]
            values = ["%" + _fold(term) + "%" for term in terms for _ in columns]
            rows = self.db.execute("SELECT m.* FROM memories m WHERE (" + " OR ".join(conditions) + ")" +
                                   status + " ORDER BY m.id DESC LIMIT ?", (*values, limit)).fetchall()
        return [dict(row) for row in rows]

    def search_messages(self, query, limit=10):
        terms = self._terms(query, limit)
        if not terms:
            return []
        if self.fts_available:
            match = " OR ".join('"' + term + '"' for term in terms)
            rows = self.db.execute("""SELECT m.* FROM messages_fts JOIN messages m ON m.id=messages_fts.rowid
                WHERE messages_fts MATCH ? ORDER BY bm25(messages_fts),m.id DESC LIMIT ?""", (match, limit)).fetchall()
        else:
            conditions = ["jarvis_search_fold(m.content) LIKE ?" for term in terms]
            values = ["%" + _fold(term) + "%" for term in terms]
            rows = self.db.execute("SELECT m.* FROM messages m WHERE m.status<>'streaming' AND (" +
                                   " OR ".join(conditions) + ") ORDER BY m.id DESC LIMIT ?",
                                   (*values, limit)).fetchall()
        return [dict(row) for row in rows]
