"""Lecture de ``/api/ps`` d'Ollama, avec un faux serveur."""

from __future__ import annotations

from typing import Any

import pytest

from catalog.extraction.client import EchecAppel, ReponseHTTP
from catalog.extraction.ollama import decrire_modele, racine_ollama, version_ollama

CHARGE = {
    "name": "qwen3:14b",
    "model": "qwen3:14b",
    "size": 1000,
    "size_vram": 1000,
    "digest": "abc123",
    "context_length": 16384,
}


class FauxOllama:
    """``/api/ps`` rend les listes prévues, ``/api/generate`` répond 200."""

    def __init__(self, *listes: list[dict[str, Any]]) -> None:
        """Une liste de modèles chargés par lecture de ``/api/ps``."""
        self.listes = list(listes)
        self.lus: list[str] = []
        self.postes: list[tuple[str, dict[str, Any]]] = []

    def lire(self, url: str) -> dict[str, Any]:
        self.lus.append(url)
        return {"models": self.listes.pop(0)}

    def transport(
        self, url: str, entetes: dict[str, str], corps: dict[str, Any], delai_s: float
    ) -> ReponseHTTP:
        self.postes.append((url, corps))
        return ReponseHTTP(statut=200, corps={"done": True})


def test_racine_sans_v1() -> None:
    assert racine_ollama("http://host.docker.internal:11434/v1/") == (
        "http://host.docker.internal:11434"
    )


def test_modele_deja_charge() -> None:
    serveur = FauxOllama([CHARGE])
    charge = decrire_modele(
        "http://h:11434/v1", "qwen3:14b", serveur.lire, serveur.transport
    )
    assert (charge.contexte_jetons, charge.empreinte, charge.part_gpu) == (
        16384,
        "abc123",
        1.0,
    )
    assert serveur.lus == ["http://h:11434/api/ps"]
    assert serveur.postes == []


def test_modele_charge_d_abord() -> None:
    serveur = FauxOllama([], [{**CHARGE, "size_vram": 500}])
    charge = decrire_modele(
        "http://h:11434/v1", "qwen3:14b", serveur.lire, serveur.transport
    )
    assert serveur.postes[0][0] == "http://h:11434/api/generate"
    assert serveur.postes[0][1]["model"] == "qwen3:14b"
    assert charge.part_gpu == 0.5


def test_contexte_absent_refuse() -> None:
    sans_contexte = {k: v for k, v in CHARGE.items() if k != "context_length"}
    serveur = FauxOllama([sans_contexte])
    with pytest.raises(EchecAppel, match="contexte ou digest"):
        decrire_modele(
            "http://h:11434/v1", "qwen3:14b", serveur.lire, serveur.transport
        )


def test_modele_sans_etiquette_trouve_en_latest() -> None:
    serveur = FauxOllama([{**CHARGE, "name": "qwen3:latest", "model": "qwen3:latest"}])
    charge = decrire_modele(
        "http://h:11434/v1", "qwen3", serveur.lire, serveur.transport
    )
    assert charge.empreinte == "abc123"


def test_version_ollama() -> None:
    def lire(url: str) -> dict[str, Any]:
        assert url == "http://h:11434/api/version"
        return {"version": "0.12.6"}

    assert version_ollama("http://h:11434/v1", lire) == "0.12.6"
