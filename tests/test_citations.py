"""Contrôle de citation : extrait dans la page citée, valeur dans l'extrait."""

from __future__ import annotations

import pytest

from catalog.extraction.cible import ChampCible, charger_cible
from catalog.extraction.citations import (
    CITATION_ABSENTE,
    CITATION_AUTRE_PAGE,
    CITATION_INTROUVABLE,
    CITATION_RECOMPOSEE,
    VALEUR_HORS_EXTRAIT,
    VALEUR_NON_MAXIMALE,
    candidats,
    canonique,
    valeur_dans_extrait,
    verifier_citation,
)
from catalog.reading.page import Page

CHAMPS = charger_cible("camera", "alimentation").par_cle()


def _champ(cle: str) -> ChampCible:
    return CHAMPS[cle]


def _valide(cle: str, valeur: bool | float | str, extrait: str) -> bool:
    return valeur_dans_extrait(_champ(cle), valeur, extrait)


# --- 1. L'extrait dans la page ---------------------------------------------


def test_extrait_present_dans_la_page_citee() -> None:
    pages = [Page(numero=3, texte="Power\nPoE: max. 6.5 W\nWeight 1 kg")]
    motif = verifier_citation(_champ("power_w_peak"), 6.5, 3, "PoE: max. 6.5 W", pages)
    assert motif is None


def test_mots_colles_par_pdfplumber() -> None:
    # Axis : « Typical4.8W,max10.7W » dans le texte lu.
    pages = [Page(numero=5, texte="Power consumption Typical4.8W,max10.7W")]
    extrait = "Typical 4.8 W, max 10.7 W"
    assert verifier_citation(_champ("power_w_peak"), 10.7, 5, extrait, pages) is None


def test_casse_tirets_insecables_et_coupure_de_mot() -> None:
    page = Page(numero=1, texte="Power Consumption (typ-\nical) 10–28 V DC")
    extrait = "power consumption (typical) 10-28 V DC"
    assert (
        verifier_citation(_champ("ports.dc.voltage_min_v"), 10, 1, extrait, [page])
        is None
    )


def test_caracteres_de_controle_et_separateurs_de_cellules() -> None:
    page = Page(numero=1, texte="Power\x01Source | 12VDC\x01±\x0125%")
    extrait = "Power Source 12VDC ± 25%"
    assert (
        verifier_citation(_champ("ports.dc.voltage_max_v"), 15, 1, extrait, [page])
        is None
    )


def test_extrait_absent_de_la_notice() -> None:
    pages = [Page(numero=1, texte="Power consumption max. 6.5 W")]
    motif = verifier_citation(_champ("power_w_peak"), 7.5, 1, "max. 7.5 W", pages)
    assert motif == CITATION_INTROUVABLE


def test_extrait_sur_une_autre_page_envoyee() -> None:
    pages = [Page(numero=1, texte="Lens 2.8 mm"), Page(numero=2, texte="max. 6.5 W")]
    motif = verifier_citation(_champ("power_w_peak"), 6.5, 1, "max. 6.5 W", pages)
    assert motif == CITATION_AUTRE_PAGE


def test_page_citee_non_envoyee() -> None:
    pages = [Page(numero=1, texte="max. 6.5 W")]
    motif = verifier_citation(_champ("power_w_peak"), 6.5, 9, "max. 9.5 W", pages)
    assert motif == CITATION_INTROUVABLE


def test_extrait_recolle_depuis_un_tableau() -> None:
    page = Page(
        numero=2,
        texte="Tableau :\nPower consumption | Model A | Model B\nMax | 6.5 W | 9.1 W",
    )
    motif = verifier_citation(
        _champ("power_w_peak"), 9.1, 2, "Power consumption Model B 9.1 W", [page]
    )
    assert motif == CITATION_RECOMPOSEE


@pytest.mark.parametrize(
    ("page", "extrait"), [(None, "max. 6.5 W"), (1, None), (1, ""), (1, "  | ")]
)
def test_sans_citation(page: int | None, extrait: str | None) -> None:
    pages = [Page(numero=1, texte="max. 6.5 W")]
    motif = verifier_citation(_champ("power_w_peak"), 6.5, page, extrait, pages)
    assert motif == CITATION_ABSENTE


def test_valeur_absente_rien_a_citer() -> None:
    assert verifier_citation(_champ("power_w"), None, None, None, []) is None


def test_canonique() -> None:
    assert canonique("Typ-\nical  12 V | DC") == "typical12vdc"


# --- 2. La valeur dans l'extrait : nombres -----------------------------------


def test_un_nombre_contenu_dans_un_autre_ne_valide_pas() -> None:
    assert not _valide("power_w_peak", 7.7, "max. 17.7 W")
    assert not _valide("power_w_peak", 7.7, "max. 7.75 W")
    assert _valide("power_w_peak", 17.7, "max. 17.7 W")


def test_virgule_decimale_et_erreur_de_virgule() -> None:
    assert _valide("power_w_peak", 6.5, "Consommation max. 6,5 W")
    # 6,5 W lu 65 W : refusé.
    pages = [Page(numero=1, texte="Consommation max. 6,5 W")]
    motif = verifier_citation(
        _champ("power_w_peak"), 65, 1, "Consommation max. 6,5 W", pages
    )
    assert motif == VALEUR_HORS_EXTRAIT


def test_l_unite_doit_etre_accolee() -> None:
    assert not _valide("power_w_peak", 12, "PoE Class 3, 12 V")
    assert not _valide("power_w_peak", 6.5, "Power consumption (W) 6.5")
    assert _valide("power_w_peak", 59.05, "max 59.05 watt, max 87.12 VA")
    assert not _valide("power_w_peak", 87.12, "max 59.05 watt, max 87.12 VA")


def test_tension_alternative_refusee_pour_l_entree_continue() -> None:
    assert not _valide("ports.dc.voltage_min_v", 24, "24 VAC, 50/60 Hz")
    assert _valide("ports.dc.voltage_min_v", 36, "24 VAC/36 VDC power source")
    assert _valide("ports.dc.voltage_min_v", 10, "Power Supply DC10V~DC28V")


def test_plage_de_tension() -> None:
    assert _valide("ports.dc.voltage_min_v", 10, "10–28 V DC, typical 13 W")
    assert _valide("ports.dc.voltage_max_v", 28, "10–28 V DC, typical 13 W")
    assert not _valide("ports.dc.voltage_min_v", 13, "10–28 V DC, typical 13 W")


@pytest.mark.parametrize(
    ("extrait", "bas", "haut"),
    [
        ("12 VDC ± 25%", 9, 15),
        ("12 VDC ± 20%, 1.19 A, max. 14.28 W", 9.6, 14.4),
        ("12 VDC, 4 A (–10% to +25%)", 10.8, 15),
        ("12 V DC +/- 10 %", 10.8, 13.2),
    ],
)
def test_tolerance_de_tension(extrait: str, bas: float, haut: float) -> None:
    assert _valide("ports.dc.voltage_min_v", bas, extrait)
    assert _valide("ports.dc.voltage_max_v", haut, extrait)
    assert _valide("ports.dc.voltage_max_v", 12, extrait)


def test_amperes_en_milliamperes_mais_jamais_des_watts() -> None:
    extrait = "12 VDC ± 25%, 0.4 A, max. 5 W"
    assert _valide("ports.dc.current_peak_ma", 400, extrait)
    assert not _valide("ports.dc.current_peak_ma", 417, extrait)  # 5 W / 12 V
    assert _valide("ports.dc.current_peak_ma", 720, "12 V DC: 720 mA, Approx. 8.6 W")
    assert _valide("ports.dc.current_peak_ma", 1190, "1.19 A, max. 14.28 W")


def test_milliers_a_la_virgule() -> None:
    assert _valide("ports.dc.current_peak_ma", 1500, "max. 1,500 mA")


def test_candidats_sans_unite_connue() -> None:
    assert candidats("Weight 1.2 kg", "W") == []


# --- 2 bis. La valeur dans l'extrait : ports, classe, norme ------------------


@pytest.mark.parametrize(
    "extrait",
    ["PoE (802.3af)", "Hi-PoE", "Power over Ethernet Plus", "IEEE 802.3bt Type 3"],
)
def test_port_poe_justifie(extrait: str) -> None:
    assert _valide("ports.poe", True, extrait)


def test_port_poe_non_justifie() -> None:
    assert not _valide("ports.poe", True, "12 VDC ± 25%")


@pytest.mark.parametrize("extrait", ["12 VDC ± 25%", "DC10V~DC28V", "24 VAC/36 V DC"])
def test_port_dc_justifie(extrait: str) -> None:
    assert _valide("ports.dc", True, extrait)


@pytest.mark.parametrize(
    "extrait", ["24 VAC, 50/60 Hz", "PoE: 802.3af, 36 V to 57 V", "Hi-PoE adapter"]
)
def test_port_dc_non_justifie(extrait: str) -> None:
    assert not _valide("ports.dc", True, extrait)


def test_port_declare_absent_sans_preuve_demandee() -> None:
    assert _valide("ports.dc", False, "PoE (802.3af)")


def test_classe() -> None:
    assert _valide("ports.poe.class", "4", "PoE+(IEEE802.3at,Class4)")
    assert _valide("ports.poe.class", "3", "802.3af, Class 3, 36 V to 57 V")
    assert not _valide("ports.poe.class", "4", "802.3bt Type 4")
    assert not _valide("ports.poe.class", "4", "802.3bt Class 40")


@pytest.mark.parametrize(
    ("norme", "extrait"),
    [
        ("802.3af", "IEEE 802.3af/802.3at Type 1 Class 3"),
        ("802.3at", "IEEE 802.3af/at"),
        ("802.3at", "PoE+ (Class 4)"),
        ("802.3bt", "IEEE 802.3 bt Type 3"),
    ],
)
def test_norme_justifiee(norme: str, extrait: str) -> None:
    assert _valide("ports.poe.min_standard", norme, extrait)


@pytest.mark.parametrize(
    ("norme", "extrait"),
    [
        ("802.3bt", "PoE++"),  # hors table
        ("802.3bt", "Hi-PoE 60 W"),  # hors table
        ("802.3at", "PoE++"),
        ("802.3af", "PoE+ (Class 4)"),
        ("802.3af", "PoE"),  # « PoE » seul ne dit pas la norme
    ],
)
def test_norme_non_justifiee(norme: str, extrait: str) -> None:
    assert not _valide("ports.poe.min_standard", norme, extrait)


def test_type_de_valeur_inattendu() -> None:
    assert not _valide("power_w_peak", "6.5", "max. 6.5 W")
    assert not _valide("power_w_peak", True, "max. 1 W")


# --- Tension alternative et valeur non maximale ------------------------------


@pytest.mark.parametrize(
    ("extrait", "admises", "refusees"),
    [
        ("Power 12 V DC / 24 V AC", [12], [24]),
        ("AC 24V±25%", [], [18, 24, 30]),
        ("AC 24V±25% (Default), DC 24V±25%", [18, 24, 30], []),
        ("24 VAC/36 VDC", [36], [24]),
    ],
)
def test_tension_alternative_jamais_citee_en_continu(
    extrait: str, admises: list[float], refusees: list[float]
) -> None:
    for v in admises:
        assert _valide("ports.dc.voltage_min_v", v, extrait)
    for v in refusees:
        assert not _valide("ports.dc.voltage_min_v", v, extrait)


@pytest.mark.parametrize(
    ("extrait", "valeur", "motif"),
    [
        ("Power consumption: 16 ~ 56W", 16.0, VALEUR_NON_MAXIMALE),
        ("Power consumption: 16 ~ 56W", 56.0, None),
        ("Typical4.8W,max10.7W", 4.8, VALEUR_NON_MAXIMALE),
        ("Typical4.8W,max10.7W", 10.7, None),
    ],
)
def test_power_w_peak_est_la_plus_haute_valeur(
    extrait: str, valeur: float, motif: str | None
) -> None:
    pages = [Page(numero=1, texte=extrait)]
    assert verifier_citation(_champ("power_w_peak"), valeur, 1, extrait, pages) == motif
    # La typique, elle, n'est pas tenue d'être la plus haute.
    assert verifier_citation(_champ("power_w"), 4.8, 1, extrait, pages) in (
        None,
        VALEUR_HORS_EXTRAIT,
    )
