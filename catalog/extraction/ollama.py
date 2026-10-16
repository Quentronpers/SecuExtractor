"""Ce qu'Ollama dit du modèle chargé : contexte réel, digest, part sur le GPU.

Sur ``/v1``, Ollama coupe sans prévenir un prompt plus long que son contexte.
Le contexte réel et le digest du modèle, lus dans ``/api/ps``, entrent donc
dans la clé des réponses brutes et règlent les contrôles de troncature
(plan eval-alimentation, §3). ``/api/ps`` ne liste que les modèles chargés :
un appel à ``/api/generate`` sans prompt charge le modèle d'abord.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from catalog.extraction.client import (
    DELAI_S,
    EchecAppel,
    Transport,
    transport_requests,
)

# Vaut pour le chargement seulement : chaque appel /v1 reprend ensuite le
# maintien par défaut du serveur (``OLLAMA_KEEP_ALIVE``, 5 min).
MAINTIEN = "30m"

LireJSON = Callable[[str], dict[str, Any]]


class ModeleAbsent(EchecAppel):
    """Ollama ne connaît pas le modèle demandé : il faut le télécharger."""


@dataclass(frozen=True)
class ModeleCharge:
    """Le modèle tel qu'Ollama l'a chargé."""

    contexte_jetons: int
    empreinte: str
    part_gpu: float  # 1.0 : tout en VRAM ; moins : débordement sur le processeur


def lire_json(url: str) -> dict[str, Any]:
    """GET JSON par ``requests`` ; erreurs réseau rendues en ``EchecAppel``."""
    try:
        reponse = requests.get(url, timeout=30)
        reponse.raise_for_status()
        lu: object = reponse.json()
    except (requests.RequestException, ValueError) as erreur:
        raise EchecAppel(f"{url} : {erreur}") from erreur
    return lu if isinstance(lu, dict) else {}


def racine_ollama(url_base: str) -> str:
    """L'URL de l'API native à partir de celle de ``/v1``."""
    return url_base.rstrip("/").removesuffix("/v1")


def _trouver(ps: dict[str, Any], modele: str) -> ModeleCharge | None:
    """Le modèle dans la liste de ``/api/ps`` ; ``qwen3`` y est « qwen3:latest »."""
    noms = {modele, modele if ":" in modele else f"{modele}:latest"}
    for entree in ps.get("models") or []:
        if not noms & {entree.get("name"), entree.get("model")}:
            continue
        taille = int(entree.get("size") or 0)
        en_vram = int(entree.get("size_vram") or 0)
        return ModeleCharge(
            contexte_jetons=int(entree.get("context_length") or 0),
            empreinte=str(entree.get("digest") or ""),
            part_gpu=en_vram / taille if taille else 0.0,
        )
    return None


def decrire_modele(
    url_base: str,
    modele: str,
    lire: LireJSON = lire_json,
    transport: Transport = transport_requests,
) -> ModeleCharge:
    """Charge le modèle si besoin et rend son contexte réel et son digest.

    Lève ``EchecAppel`` si Ollama ne donne pas le contexte ou le digest :
    sans eux, la troncature silencieuse ne serait pas détectée.
    """
    racine = racine_ollama(url_base)
    charge = _trouver(lire(f"{racine}/api/ps"), modele)
    if charge is None:
        corps = {"model": modele, "keep_alive": MAINTIEN}
        reponse = transport(f"{racine}/api/generate", {}, corps, DELAI_S)
        if reponse.statut == 404:
            raise ModeleAbsent(f"{modele} absent du serveur")
        if reponse.statut != 200:
            raise EchecAppel(f"chargement de {modele} : HTTP {reponse.statut}")
        charge = _trouver(lire(f"{racine}/api/ps"), modele)
    if charge is None or not charge.contexte_jetons or not charge.empreinte:
        raise EchecAppel(f"{modele} : contexte ou digest absent de /api/ps")
    return charge


def version_ollama(url_base: str, lire: LireJSON = lire_json) -> str:
    """Version du serveur Ollama (``/api/version``), enregistrée avec les résultats."""
    return str(lire(f"{racine_ollama(url_base)}/api/version").get("version") or "")
