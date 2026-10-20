"""Règles tirées des erreurs de Groq en L5 : typique PoE, courant au repos, Vivotek."""

from __future__ import annotations

import pytest

from catalog.extraction.cible import Valeur
from catalog.plausibility.indices import (
    typique_au_lieu_du_max,
    typique_dans_couple_max,
)
from tests.test_plausibilite import _motifs


@pytest.mark.parametrize(
    ("valeur", "extrait"),
    [
        (30.0, "Power Consumption PoE Max. 60W, typical : 30W"),  # hanwha-07
        (30.0, "Power Consumption PoE Max.60W,typical:30W"),
        (5.2, "Power consumption typ- PoE: 5.2 W / 6.2 W ical/maximum (5 MP)"),
        (4.8, "Basic 4.8 W, max 6 W"),
    ],
)
def test_typique_retenue_au_lieu_du_max(valeur: float, extrait: str) -> None:
    assert typique_au_lieu_du_max(valeur, extrait)


@pytest.mark.parametrize(
    ("valeur", "extrait"),
    [
        (60.0, "Power Consumption PoE Max. 60W, typical : 30W"),  # la bonne
        (50.0, "Tested POE Injector (60 W) : DC 54V 1.0 A, Approx. 50 W"),
        (14.0, "Typical: PoE 14.0 W, DC 14.2 W"),  # autre alimentation
        (12.0, "Typical 12 W, Class 4 (25.5 W)"),  # calibre de classe
        (12.0, "PoE: 12 W, max 15 W"),  # sans indice de typique
        (5.2, "Typical 5.2 W\nPoE: 9 W"),  # pas sur la même ligne
    ],
)
def test_pas_de_fausse_alerte(valeur: float, extrait: str) -> None:
    assert not typique_au_lieu_du_max(valeur, extrait)


def test_regle_poe_typique_met_en_douteux() -> None:
    extrait = "Power Consumption PoE Max. 60W, typical : 30W"
    motifs = _motifs(
        {"ports.poe.power_w": 30.0, "power_w_peak": 92.0},
        {"ports.poe.power_w": extrait},
    )
    assert motifs == {"ports.poe.power_w": "poe_non_maximale"}


def test_regle_poe_typique_sans_extrait() -> None:
    assert _motifs({"ports.poe.power_w": 30.0, "power_w_peak": 92.0}) == {}


def test_courant_au_repos_sans_maximal() -> None:
    # hik-04 : 1,19 A rangé au repos, rien en maximal.
    valeurs: dict[str, Valeur] = {"ports.dc.current_standby_ma": 1190.0}
    assert _motifs(valeurs) == {"ports.dc.current_standby_ma": "repos_sans_max"}


def test_courant_au_repos_avec_maximal() -> None:
    valeurs: dict[str, Valeur] = {
        "ports.dc.current_standby_ma": 500.0,
        "ports.dc.current_peak_ma": 1190.0,
    }
    assert "ports.dc.current_standby_ma" not in _motifs(valeurs)


@pytest.mark.parametrize(
    ("valeur", "extrait", "attendu"),
    [
        (11.4, "PoE: Max. 24.7/11.4 W (Heater on/off)", True),  # vivotek-01
        (24.7, "PoE: Max. 24.7/11.4 W (Heater on/off)", True),
        (12.0, "PoE: Max. 23.3/12 W (Heater on/off)", True),  # vivotek-04
        (4.8, "typ./max. : 4.8/6 W", False),  # vraie typique
        (5.2, "PoE: 5.2 W / 6.2 W", False),  # bosch-01, sans « max »
        (9.0, "PoE: Max. 24.7/11.4 W", False),  # valeur hors du couple
    ],
)
def test_typique_dans_couple_max(valeur: float, extrait: str, attendu: bool) -> None:
    assert typique_dans_couple_max(valeur, extrait) is attendu


def test_regle_typique_couple() -> None:
    extrait = "PoE: Max. 24.7/11.4 W (Heater on/off)"
    motifs = _motifs(
        {"power_w": 11.4, "power_w_peak": 24.7, "ports.poe.power_w": 24.7},
        {"power_w": extrait},
    )
    assert motifs == {"power_w": "typique_dans_couple_max"}
