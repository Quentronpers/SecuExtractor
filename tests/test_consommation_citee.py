"""Règle de la plus forte consommation citée (cause n° 1 des erreurs de L4)."""

from __future__ import annotations

import pytest

from catalog.extraction.cible import Valeur
from catalog.plausibility.checker import (
    consommation_max_citee,
    consommations_citees,
    verifier_plausibilite,
)
from catalog.reading.page import Page

# hanwha-07 : le maximum PoE (60 W) n'est pas le maximum toutes alimentations.
HANWHA_07 = """Input Voltage PoE++(IEEE802.3bt type4,Class7),24VAC
Power Consumption PoE Max. 60W, typical : 30W
24VAC Max. 92W, typical : 30W"""


def _pages(texte: str) -> list[Page]:
    return [Page(numero=1, texte=texte)]


def _motif_maxi(maxi: float, texte: str) -> str:
    valeurs: dict[str, Valeur] = {"ports.poe": True, "power_w_peak": maxi}
    return verifier_plausibilite(valeurs, {}, _pages(texte)).get("power_w_peak", "")


@pytest.mark.parametrize(("maxi", "douteux"), [(60.0, True), (92.0, False)])
def test_maximale_sous_la_plus_forte_consommation(maxi: float, douteux: bool) -> None:
    assert ("inferieure_consommation_citee" in _motif_maxi(maxi, HANWHA_07)) is douteux


def test_une_seule_alimentation_citee_pas_de_regle() -> None:
    texte = "Power over Ethernet (PoE) IEEE 802.3af\nTypical 4 W, max 6 W\nmax 9 W"
    assert consommation_max_citee(_pages(texte)) is None
    assert _motif_maxi(6.0, texte) == ""


def test_calibre_d_injecteur_exclu_consommation_mesuree_gardee() -> None:
    texte = (
        "Power Source and Power Consumption AC24 V 3.4 A, Approx. 55 W\n"
        "PoE+ (IEEE802.3at compliant): DC 54V 470 mA, Approx. 25 W(Class4 device)\n"
        "Tested POE Injector (60 W) : DC 54V 1.0 A, Approx. 50 W"
    )
    # 25 W est écarté (la ligne cite une norme) : la règle se tait plus
    # souvent, elle ne se déclenche jamais à tort pour autant.
    assert consommations_citees(_pages(texte)) == [55.0, 50.0]


@pytest.mark.parametrize(
    "ligne",
    [
        "NPD-6001B Midspan, 60W, single port, AC in",
        "High Power over Ethernet, max 90 W",
        "maximum global, PoH/PoE 95 W",
        "IEEE 802.3bt max 90 W",
        "PoE Class 4, max 25.5 W",
        "12 VDC output, max 6 W",
        "40 W",
    ],
)
def test_calibres_et_valeurs_sans_indice_exclus(ligne: str) -> None:
    assert consommations_citees(_pages(ligne)) == []


@pytest.mark.parametrize(
    ("ligne", "attendu"),
    [
        ("Max.: 7W (DC 12V), 8.5W(PoE)", [7.0, 8.5]),
        ("Max (Note): 7.4 W (12 VDC); 8.9 W (PoE)", [7.4, 8.9]),
        ("Power consumption: max 59.05 watt", [59.05]),
        ("max 6 W; recommended 30 W PSU", [6.0]),
        ("PoE Type 3 (60 W)", []),
    ],
)
def test_valeur_suivante_heritee_et_indices(ligne: str, attendu: list[float]) -> None:
    assert consommations_citees(_pages(ligne)) == attendu


def test_virgule_decimale_et_plage_typique() -> None:
    texte = "Power consumption VAC (W) (typical 6,31 W – 10,76 W"
    assert consommations_citees(_pages(texte)) == [6.31, 10.76]
