"""Explicit model installation only. JARVIS itself never downloads models."""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jarvis.config import data_directory


def verified_download(repo, revision, filename, destination):
    from huggingface_hub import HfApi, hf_hub_download
    info = HfApi().model_info(repo, revision=revision, files_metadata=True)
    metadata = next(item for item in info.siblings if item.rfilename == filename)
    cached = Path(hf_hub_download(repo, filename, revision=info.sha))
    if metadata.lfs:
        with cached.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        expected = metadata.lfs.sha256
    else:
        data = cached.read_bytes()
        digest = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        expected = metadata.blob_id
    if not expected or digest != expected:
        raise RuntimeError(f"Intégrité non vérifiée : {repo}/{filename}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, destination)
    return {"repo": repo, "revision": info.sha, "file": filename,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}


def install(root, accept, stt_size):
    from huggingface_hub import HfApi
    root.mkdir(parents=True, exist_ok=True)
    cards = root / "licenses"
    records = []
    for name in ("tom", "siwis"):
        prefix = f"fr/fr_FR/{name}/medium/"
        records.append(verified_download("rhasspy/piper-voices", "v1.0.0", prefix + "MODEL_CARD", cards / f"{name}-MODEL_CARD.txt"))
    records.append(verified_download(f"Systran/faster-whisper-{stt_size}", "main", "README.md", cards / "whisper-README.md"))
    print("Licences et fiches à lire :", cards)
    if not accept:
        print("Aucun poids installé. Après lecture, relancer avec --accept-model-licenses.")
        return
    # New installs never overwrite an existing model directory.
    for target in (root / "piper", root / "whisper"):
        if target.exists():
            raise RuntimeError(f"Dossier existant préservé : {target}. Choisissez --destination pour un autre emplacement.")
    with tempfile.TemporaryDirectory(prefix="jarvis-models-", dir=root) as temp:
        stage = Path(temp)
        for name in ("tom", "siwis"):
            filename = f"fr_FR-{name}-medium.onnx"
            prefix = f"fr/fr_FR/{name}/medium/"
            for suffix in ("", ".json"):
                records.append(verified_download("rhasspy/piper-voices", "v1.0.0", prefix + filename + suffix, stage / "piper" / (filename + suffix)))
        repo = f"Systran/faster-whisper-{stt_size}"
        info = HfApi().model_info(repo, revision="main", files_metadata=True)
        allowed = {"config.json", "model.bin", "tokenizer.json", "vocabulary.json", "vocabulary.txt", "preprocessor_config.json"}
        for item in info.siblings:
            if item.rfilename in allowed:
                records.append(verified_download(repo, info.sha, item.rfilename, stage / "whisper" / item.rfilename))
        if not (stage / "whisper/model.bin").is_file():
            raise RuntimeError("Poids STT absents ; installation non publiée.")
        (stage / "piper").rename(root / "piper")
        (stage / "whisper").rename(root / "whisper")
    (root / "manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    print("Modèles locaux installés et vérifiés :", root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=data_directory() / "models")
    parser.add_argument("--stt-size", choices=("tiny", "base", "small"), default="small")
    parser.add_argument("--accept-model-licenses", action="store_true")
    args = parser.parse_args()
    try:
        install(args.destination, args.accept_model_licenses, args.stt_size)
    except Exception as exc:
        print("Installation arrêtée (aucune vérification désactivée) :", str(exc), file=sys.stderr)
        raise SystemExit(1)
