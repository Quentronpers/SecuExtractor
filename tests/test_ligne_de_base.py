"""Ligne de base par expressions régulières et rappel du découpage."""

from __future__ import annotations

from catalog.evaluation import decoupage, ligne_de_base
from catalog.extraction.etats import etats_champs
from catalog.reading.page import Page
from tests.test_rejeu import corrige
from tests.test_runner import CIBLE, PAGES

PTZ = [
    Page(
        numero=3,
        texte="Power\nPower supply 24 VAC / 12 VDC ± 25%, max 2.5 A\n"
        "Hi-PoE, IEEE 802.3bt Class 6\nPower consumption: typ. 18 W, max 60 W",
    )
]


def test_notice_poe_simple() -> None:
    reponse = ligne_de_base.extraire(PAGES).root
    assert reponse["ports.poe"].valeur is True
    assert reponse["ports.dc"].valeur is False
    assert reponse["ports.poe.class"].valeur == "3"
    assert reponse["ports.poe.min_standard"].valeur == "802.3af"
    assert reponse["power_w"].valeur == 4.8
    assert reponse["power_w_peak"].valeur == 10.7
    assert reponse["ports.dc.current_standby_ma"].valeur is None


def test_notice_dc_et_poe() -> None:
    reponse = ligne_de_base.extraire(PTZ).root
    assert reponse["ports.dc"].valeur is True
    assert reponse["ports.dc.voltage_min_v"].valeur == 9.0
    assert reponse["ports.dc.voltage_max_v"].valeur == 15.0
    assert reponse["ports.dc.current_peak_ma"].valeur == 2500.0
    assert reponse["ports.poe.min_standard"].valeur == "802.3bt"
    assert reponse["power_w"].valeur == 18.0
    assert reponse["power_w_peak"].valeur == 60.0
    assert reponse["ports.poe.power_w"].extrait is None


def test_reponse_passe_les_controles_de_citation() -> None:
    champs = etats_champs(ligne_de_base.extraire(PAGES), CIBLE, PAGES)
    produits = [c for c in champs.values() if c.etat != "absent"]
    assert produits and all(c.etat == "sur" for c in produits)


def test_page_sans_alimentation() -> None:
    reponse = ligne_de_base.extraire([Page(numero=1, texte="Lens 2.8 mm")]).root
    assert all(r.valeur is None for r in reponse.values())


def test_places_retenue_ecartee_introuvable() -> None:
    longue = Page(numero=1, texte="Optics and lens. " * 400)
    pages = [longue, *PAGES]
    assert decoupage.placer("Typical 4.8 W", pages, PAGES) == "retenue"
    assert decoupage.placer("Optics and lens.", pages, PAGES) == "ecartee"
    assert decoupage.placer("Typical 9.9 W", pages, PAGES) == "introuvable"


def test_places_et_resume() -> None:
    places = decoupage.places(corrige(), PAGES, "alimentation")
    assert set(places.values()) == {"retenue"} and len(places) == 7
    resume = decoupage.resumer({"axis-01": places, "x": {"power_w": "ecartee"}})
    assert resume["rappel"] == 7 / 8
    assert resume["non_retenues"] == {"x": {"power_w": "ecartee"}}
