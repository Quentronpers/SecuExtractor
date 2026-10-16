"""Découpage : pages du bloc alimentation, et nettoyage commun aux lecteurs."""

from __future__ import annotations

import pytest

from catalog.reading.chunker import DOCUMENT_COURT, MAX_PAGES, selectionner
from catalog.reading.page import Page, nettoyer

REMPLISSAGE = "Lens and image sensor characteristics. " * 60


def _page(numero: int, texte: str) -> Page:
    return Page(numero=numero, texte=texte + "\n" + REMPLISSAGE)


def test_document_court_envoye_en_entier() -> None:
    pages = [Page(numero=1, texte="Lens"), Page(numero=2, texte="Weight 1 kg")]
    assert sum(len(p.texte) for p in pages) <= DOCUMENT_COURT
    assert selectionner(pages, "alimentation") == pages


def test_seules_les_pages_d_alimentation_sont_gardees() -> None:
    pages = [
        _page(1, "Video compression H.265"),
        _page(2, "Power consumption Max. 6.5 W, PoE (802.3af)"),
        _page(3, "Operating temperature -30 °C"),
        _page(4, "Input voltage 12 V DC ± 25 %"),
    ]
    assert [p.numero for p in selectionner(pages, "alimentation")] == [2, 4]


def test_une_seule_mention_ne_suffit_pas() -> None:
    pages = [_page(i, "Supports PoE switches") for i in range(1, 4)]
    assert selectionner(pages, "alimentation") == []


def test_plafond_les_mieux_notees_dans_l_ordre_du_document() -> None:
    forte = "Power consumption 6 W, PoE 802.3af Class 2, 12 V DC, 500 mA"
    faible = "Power supply 12 V DC"
    pages = [_page(1, faible)] + [_page(i, forte) for i in range(2, MAX_PAGES + 2)]
    retenues = selectionner(pages, "alimentation")
    assert [p.numero for p in retenues] == list(range(2, MAX_PAGES + 2))


def test_bloc_inconnu_refuse() -> None:
    with pytest.raises(ValueError, match="bloc inconnu"):
        selectionner([Page(numero=1, texte="x")], "physique")


def test_nettoyer_remplace_les_caracteres_de_controle() -> None:
    # Hanwha : « \x01 » à la place des espaces.
    assert nettoyer("Metal\x01shielded\x01RJ-45") == "Metal shielded RJ-45"


def test_nettoyer_garde_les_lignes_et_retire_l_excedent() -> None:
    assert nettoyer("  a  b \n\n\n\n c\t") == "a b\n\nc"


def test_nettoyer_garde_les_espaces_insecables() -> None:
    assert nettoyer("12 V  DC") == "12 V  DC"
