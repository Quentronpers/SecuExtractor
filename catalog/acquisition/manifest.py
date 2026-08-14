"""Journal des fichiers archivés : url, date de capture, empreinte, outil.

Voir docs/pipeline.md (section « Le manifeste ») pour le format d'une entrée.
Un seul fichier JSON, data/sources/manifeste.json, non versionné mais conservé.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SOURCES_DIR = DATA_DIR / "sources"
MANIFESTE_PATH = SOURCES_DIR / "manifeste.json"


def empreinte_sha256(contenu: bytes) -> str:
    return hashlib.sha256(contenu).hexdigest()


def _horodatage() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def charger() -> list[dict[str, Any]]:
    if not MANIFESTE_PATH.exists():
        return []
    with MANIFESTE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _sauvegarder(entrees: list[dict[str, Any]]) -> None:
    MANIFESTE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFESTE_PATH.open("w", encoding="utf-8") as f:
        json.dump(entrees, f, ensure_ascii=False, indent=2)


def enregistrer(fichier: str, url: str, type_document: str, outil: str, statut: str = "archive") -> dict[str, Any]:
    """Ajoute une entrée au manifeste après archivage d'un document.

    ``fichier`` est un chemin relatif à data/sources/ (ex. "dahua/notice.pdf"),
    déjà écrit sur disque au moment de l'appel : l'empreinte est calculée à
    partir de son contenu réel.
    """
    entree = {
        "fichier": fichier,
        "url": url,
        "type_document": type_document,
        "date_capture": _horodatage(),
        "empreinte_sha256": empreinte_sha256((SOURCES_DIR / fichier).read_bytes()),
        "outil": outil,
        "statut": statut,
    }
    entrees = charger()
    entrees.append(entree)
    _sauvegarder(entrees)
    return entree


def empreinte_a_change(fichier: str, nouvelle_empreinte: str) -> bool:
    """Vrai si une entrée existe déjà pour ce fichier avec une empreinte différente.

    Sert à déclencher la réextraction d'une seule référence au passage
    suivant, plutôt que de tout retraiter (docs/pipeline.md, « Le manifeste »).
    """
    for entree in reversed(charger()):
        if entree["fichier"] == fichier:
            return entree["empreinte_sha256"] != nouvelle_empreinte
    return False
