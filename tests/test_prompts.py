"""Gabarit, message et schéma de sortie du bloc alimentation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from catalog.extraction.cible import charger_cible
from catalog.extraction.prompts import (
    CONSIGNES,
    ReponseBloc,
    gabarit,
    message_utilisateur,
    schema_sortie,
)
from catalog.reading.page import Page

CIBLE = charger_cible("camera", "alimentation")


def test_chaque_cible_a_une_consigne() -> None:
    assert set(CONSIGNES) == set(CIBLE.par_cle())


def test_gabarit_cite_chaque_champ_et_les_regles() -> None:
    texte = gabarit(CIBLE)
    for cle in CIBLE.par_cle():
        assert f"- {cle} (" in texte
    assert "Citation is mandatory" in texte
    assert "Never infer" in texte
    assert "number in mA" in texte
    assert '"802.3af", "802.3at", "802.3bt"' in texte


def test_schema_strict() -> None:
    schema = schema_sortie(CIBLE)
    assert schema["additionalProperties"] is False
    assert schema["required"] == [champ.cle for champ in CIBLE.champs]
    for propriete in schema["properties"].values():
        assert propriete["additionalProperties"] is False
        assert propriete["required"] == list(propriete["properties"])
        # L'extrait est demandé avant la valeur.
        assert list(propriete["properties"])[:3] == ["extrait", "page", "valeur"]


def test_schema_nullable_et_enum() -> None:
    proprietes = schema_sortie(CIBLE)["properties"]
    assert proprietes["power_w_peak"]["properties"]["valeur"] == {
        "type": ["number", "null"]
    }
    classe = proprietes["ports.poe.class"]["properties"]["valeur"]
    texte, nul = classe["anyOf"]
    assert texte["type"] == "string" and "8" in texte["enum"]
    assert nul == {"type": "null"}


def test_message_porte_reference_et_pages() -> None:
    pages = [Page(numero=2, texte="Power 5 W"), Page(numero=3, texte="x", titre="Spec")]
    texte = message_utilisateur("XND-8083RV", pages)
    assert texte.startswith("Target reference: XND-8083RV")
    assert "=== Page 2 ===\nPower 5 W" in texte
    assert "=== Page 3 - Spec ===" in texte


def _rendu(valeur: object) -> dict[str, object]:
    return {"extrait": None, "page": None, "valeur": valeur, "doute": False}


def test_reponse_lue_avec_des_cles_a_points() -> None:
    donnees = {cle: _rendu(None) for cle in CIBLE.par_cle()}
    donnees["ports.poe.class"] = _rendu("4")
    reponse = ReponseBloc.model_validate(donnees)
    assert reponse.root["ports.poe.class"].valeur == "4"


def test_reponse_incomplete_refusee() -> None:
    donnees = {cle: _rendu(None) for cle in CIBLE.par_cle()}
    del donnees["ports.dc"]
    with pytest.raises(ValidationError, match="ports.dc"):
        ReponseBloc.model_validate(donnees)


def test_ports_faux_demandent_une_citation() -> None:
    assert "For true or false, quote" in CONSIGNES["ports.dc"]
    assert "For true or false, quote" in CONSIGNES["ports.poe"]
