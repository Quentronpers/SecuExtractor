"""Tests des réglages des fournisseurs de modèle."""

from __future__ import annotations

import pytest

from catalog.extraction.fournisseurs import (
    MAX_JETONS,
    URLS,
    champ_max_jetons,
    reflexion_admise,
)


def test_ollama_lit_max_tokens_les_heberges_max_completion_tokens() -> None:
    assert champ_max_jetons("ollama") == "max_tokens"
    assert champ_max_jetons("groq") == "max_completion_tokens"
    assert champ_max_jetons("scaleway") == "max_completion_tokens"


@pytest.mark.parametrize("fournisseur", ["groq", "scaleway"])
def test_heberge_refuse_la_reflexion_none(fournisseur: str) -> None:
    assert not reflexion_admise(fournisseur, "none")
    assert reflexion_admise(fournisseur, "low")


def test_ollama_admet_toutes_les_reflexions() -> None:
    assert all(reflexion_admise("ollama", r) for r in MAX_JETONS)


def test_budgets_et_serveurs_publies_inchanges() -> None:
    assert MAX_JETONS == {"none": 2048, "low": 8192, "medium": 8192}
    assert sorted(URLS) == ["groq", "ollama", "scaleway"]
