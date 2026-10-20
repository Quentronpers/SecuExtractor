"""Règles tirées des erreurs de Groq en L5 : extraits, ports, classe du pire cas."""

from __future__ import annotations

import pytest

from catalog.extraction.cible import Valeur
from catalog.plausibility.indices import (
    minimum_d_un_couple_max,
    typique_au_lieu_du_max,
    typique_dans_couple_max,
)
from catalog.plausibility.regles_extraits import entree_continue_citee
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


@pytest.mark.parametrize(
    ("extrait", "attendu"),
    [
        ("36 VDC, 2.23 A ± 25% HI-PoE", True),  # dahua-03
        ("DC12V ± 25%", True),
        ("12 V DC", True),
        ("Power-over-Ethernet (48 VDC nominal)", False),  # bosch-01 : PoE
        ("High Power over Ethernet 56VDC nominal", False),  # bosch-03
        ("12VDC output, max 1.2 W", False),  # sortie accessoires
        ("PoE IEEE 802.3at, 24 VAC", False),
        ("Power output: DC12V, max 100 mA", False),  # sortie écrite avant
    ],
)
def test_entree_continue_citee(extrait: str, attendu: bool) -> None:
    assert entree_continue_citee(extrait) is attendu


def test_port_dc_faux_avec_son_marqueur() -> None:
    motifs = _motifs({"ports.dc": False}, {"ports.dc": "36 VDC, 2.23 A ± 25% HI-PoE"})
    assert motifs == {"ports.dc": "port_faux_marqueur"}


def test_port_poe_faux_avec_son_marqueur() -> None:
    motifs = _motifs({"ports.poe": False}, {"ports.poe": "PoE IEEE 802.3af Class 2"})
    assert motifs == {"ports.poe": "port_faux_marqueur"}


def test_port_dc_faux_cite_sur_l_extrait_poe() -> None:
    # GUIDE : « PoE seul » se cite par l'extrait PoE, sans tension continue.
    extrait = "Power over Ethernet (PoE) IEEE 802.3af/802.3at Type 1"
    assert _motifs({"ports.dc": False}, {"ports.dc": extrait}) == {}


@pytest.mark.parametrize(("citee", "admis"), [("802.3bt", True), ("", False)])
def test_classe_du_pire_cas_avec_norme_basse(citee: str, admis: bool) -> None:
    # Q1806-LE : démarre en at, classe 6 du mode bt (GUIDE, 2026-10-20).
    valeurs: dict[str, Valeur] = {
        "ports.poe.class": "6",
        "ports.poe.min_standard": "802.3at",
    }
    motifs = _motifs(valeurs, texte=f"IEEE 802.3at Class 4 ; {citee} Class 6")
    assert ("ports.poe.class" not in motifs) is admis


@pytest.mark.parametrize(
    ("valeur", "extrait", "attendu"),
    [
        (11.4, "PoE max 24.7 W / 11.4 W (Heater on/off)", True),
        (11.4, "PoE: Max. 24.7/11.4 W (Heater on/off)", True),
        (24.7, "PoE: Max. 24.7/11.4 W (Heater on/off)", False),  # la bonne
        (12.0, "PoE: Max. 12/12 W", False),  # couple égal
    ],
)
def test_minimum_d_un_couple_max(valeur: float, extrait: str, attendu: bool) -> None:
    assert minimum_d_un_couple_max(valeur, extrait) is attendu


def test_regle_poe_couple() -> None:
    motifs = _motifs(
        {"ports.poe.power_w": 11.4, "power_w_peak": 24.7},
        {"ports.poe.power_w": "PoE max 24.7 W / 11.4 W (Heater on/off)"},
    )
    assert motifs == {"ports.poe.power_w": "minimum_d_un_couple_max"}


@pytest.mark.parametrize("extrait", ["PoE: N/A", "Non-PoE model", "12 VDC, no PoE"])
def test_poe_nie_pas_de_fausse_alerte(extrait: str) -> None:
    assert _motifs({"ports.poe": False}, {"ports.poe": extrait}) == {}
