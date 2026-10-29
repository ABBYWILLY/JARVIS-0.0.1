#!/usr/bin/env python3
"""Seed/verify an exclusively owned packaging fixture, never a user's profile.

The verifier opens SQLite read-only and does not construct Store: that would
recover streaming rows and could hide a failed application's restart recovery.
No model, device or server is contacted by this helper.
"""
import argparse
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DATABASE = "jarvis.sqlite3"
SNAPSHOT = "update-fixture.json"
FIXTURE = "jarvis-update-smoke-v1"
TABLES = {"sessions": "id", "messages": "id", "settings": "key",
          "preferences": "key", "memories": "id"}


def _rows(db):
    return {name: [dict(row) for row in db.execute(f"SELECT * FROM {name} ORDER BY {key}")]
            for name, key in TABLES.items()}


def seed(directory):
    """Reserve a NEW directory before SQLite is opened; leave existing files alone."""
    from jarvis.config import Settings
    from jarvis.cognitive_state import CognitiveHudSettings
    from jarvis.gpu_config import GpuSettings
    from jarvis.markdown_view import ConversationTypography
    from jarvis.presence import PresenceSettings
    from jarvis.storage import Store
    from jarvis.voice_config import VoiceSettings

    directory = Path(directory)
    directory.mkdir(parents=False, exist_ok=False)
    store = Store(directory / DATABASE)
    try:
        sid = store.new_session()
        mid = store.begin_turn(sid, "Recette locale : été, cœur et 12,50 €.", "fixture-local",
                               metadata={"fixture": FIXTURE, "source": {"original": "épreuve 🧪"}})
        store.update_response(mid, "# ArchiveRecette\nTexte **préservé** 😊 et `code`.", "complete")
        partial = store.begin_turn(sid, "Conserver le fragment en cas d'interruption.", "fixture-local",
                                   source="voice", metadata={"fixture": FIXTURE, "voice": {"profile": "story"}})
        store.update_response(partial, "FragmentRecette : réponse non terminée…")
        memory = store.memory.create("ZephyrRecette reste local et demande une permission explicite.",
            title="Souvenir de recette", topic="ZephyrRecette", provenance={"message_id": mid, "source": "fixture"})
        store.memory.approve(memory, confirmed=True)
        store.save_settings(Settings(model="fixture-local", reasoning_mode="auto", cognitive_mode="creative",
                                     temperature=.4, system_prompt="Recette locale synthétique — ne rien exécuter."))
        preferences = {
            "voice": VoiceSettings(voice="fr_FR-siwis-medium", speed=.92,
                                   acoustic_mode="headphones", speech_profile="story").to_dict(),
            "presence": asdict(PresenceSettings(wave_expressivity=83, reduced_motion=True)),
            "presence_gpu": GpuSettings(profile="eco", halo_radius=115).to_dict(),
            "presence_engine": {"mode": "gpu", "automatic_engine": "gpu", "gpu_failed": False,
                                "reason": "", "future_engine_option": {"keep": True}},
            "conversation": ConversationTypography(size=14, spacing="compact").to_dict(),
            "cognitive_hud": CognitiveHudSettings(level="diagnostic", show_provenance=True).to_dict(),
            "control_center": {"favorites": ["voice", "presence_engine"], "view": "personalize"},
            "show_generation_metrics": True,
            "sidebar_collapsed": True,
            "future_fixture_preference": {"unknown": ["conserver", 42, True]},
        }
        for key, value in preferences.items():
            if isinstance(value, dict):
                value = {**value, "future_fixture_option": "conserver sans réécriture"}
            store.set_preference(key, value)
        expected = _rows(store.db)
        for row in expected["messages"]:
            if row["status"] == "streaming":
                row["status"] = "interrupted"
        snapshot = {"fixture": FIXTURE, "schema": store.db.execute("PRAGMA user_version").fetchone()[0],
                    "tables": expected, "fts_available": store.memory.fts_available,
                    "memory_id": memory, "partial_id": partial}
        with (directory / SNAPSHOT).open("x", encoding="utf-8") as stream:
            json.dump(snapshot, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
    finally:
        store.close()
    return {"fixture": FIXTURE, "status": "seeded", "private_data": "synthetic_only"}


def verify(directory):
    """Read the expected fixture and database without modifying either of them."""
    directory = Path(directory)
    with (directory / SNAPSHOT).open(encoding="utf-8") as stream:
        expected = json.load(stream)
    if expected.get("fixture") != FIXTURE or set(expected.get("tables", {})) != set(TABLES):
        raise ValueError("Ce dossier ne contient pas la recette de compilation attendue.")
    uri = (directory / DATABASE).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Intégrité SQLite de la recette en échec.")
        if db.execute("PRAGMA user_version").fetchone()[0] != expected["schema"]:
            raise ValueError("Version de schéma de la recette modifiée.")
        actual = _rows(db)
        for name in TABLES:
            if actual[name] != expected["tables"][name]:
                raise ValueError(f"Recette non préservée : table {name}.")
        if expected["fts_available"]:
            memory_ids = [row[0] for row in db.execute(
                "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ?", ("ZephyrRecette",))]
            partial_ids = [row[0] for row in db.execute(
                "SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?", ("FragmentRecette",))]
            if memory_ids != [expected["memory_id"]] or partial_ids != [expected["partial_id"]]:
                raise ValueError("Index FTS de la recette non préservés ou fragment non récupéré.")
    return {"fixture": FIXTURE, "status": "preserved", "integrity": "ok",
            "archive_and_metadata": "unchanged", "all_preferences_and_settings": "unchanged",
            "approved_memory": "unchanged", "streaming_fragment": "recovered_as_interrupted",
            "fts": "verified" if expected["fts_available"] else "unavailable",
            "private_data": "synthetic_only", "hardware_validation": "not_performed"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seed", "verify"))
    parser.add_argument("directory", type=Path, help="Nouveau dossier jetable pour seed ; recette existante pour verify")
    parser.add_argument("--report", type=Path, help="Nouveau rapport JSON, jamais écrasé")
    args = parser.parse_args(argv)
    if args.report is not None and args.report.exists():
        parser.error("Le rapport existe déjà ; choisissez un nouveau chemin.")
    try:
        result = seed(args.directory) if args.mode == "seed" else verify(args.directory)
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        if args.report is not None:
            with args.report.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
        print(encoded, end="")
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Recette de conservation : {type(error).__name__}: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
