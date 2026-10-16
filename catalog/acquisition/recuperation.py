"""Récupération des notices d'un jeu d'évaluation, par empreinte.

Un tiers qui clone le dépôt n'a pas les notices (elles ne sont pas
redistribuées) : il les retélécharge depuis les URL de ``eval/notices.csv``
et vérifie que chaque document est bien celui du corrigé, par son empreinte
SHA-256. Une notice dont l'empreinte a changé a été modifiée par le
fabricant depuis l'annotation : elle est signalée et jamais archivée, le
corrigé ne vaut plus pour elle.

Le téléchargement passe par le fetcher (``robots.txt``, cadence, reprises).
Sans ``archiver``, rien n'est écrit : on vérifie seulement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from catalog.acquisition import fetcher, manifest

Statut = Literal["present", "conforme", "recupere", "modifie", "echec"]


@dataclass(frozen=True)
class Demande:
    """Une notice à retrouver : où la prendre et quelle empreinte attendre."""

    id: str
    fabricant: str
    url: str
    format: str  # "pdf" ou "html"
    sha256: str


def deja_archivee(demande: Demande) -> bool:
    """Vrai si le manifeste a déjà ce document, fichier présent sur disque."""
    return any(
        entree.get("empreinte_sha256") == demande.sha256
        and entree.get("statut") != "remplace"
        and (manifest.SOURCES_DIR / entree["fichier"]).exists()
        for entree in manifest.charger()
    )


def telecharger(demande: Demande) -> bytes | None:
    """Les octets du document, tels qu'archivés à l'origine ; ``None`` si échec.

    Une page web est archivée en texte UTF-8 après décodage : on refait de
    même pour retrouver la même empreinte.
    """
    if demande.format == "pdf":
        return fetcher.fetch_binaire(demande.url)
    resultat = fetcher.fetch_texte(demande.url)
    return resultat.contenu.encode("utf-8") if resultat else None


def _archiver(demande: Demande, contenu: bytes) -> None:
    """Écrit le document sous ``<fabricant>/<id>.<format>`` et l'inscrit."""
    dossier = re.sub(r"[^a-z0-9]+", "-", demande.fabricant.lower()).strip("-")
    fichier = f"{dossier}/{demande.id}.{demande.format}"
    (manifest.SOURCES_DIR / dossier).mkdir(parents=True, exist_ok=True)
    (manifest.SOURCES_DIR / fichier).write_bytes(contenu)
    manifest.enregistrer(fichier, demande.url, demande.format, "requests")


def recuperer(demande: Demande, archiver: bool = False) -> Statut:
    """Retrouve une notice ; l'archive si demandé et si l'empreinte concorde."""
    if deja_archivee(demande):
        return "present"
    contenu = telecharger(demande)
    if contenu is None:
        return "echec"
    if manifest.empreinte_sha256(contenu) != demande.sha256:
        return "modifie"
    if not archiver:
        return "conforme"
    _archiver(demande, contenu)
    return "recupere"
