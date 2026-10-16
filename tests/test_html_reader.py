"""Lecteur HTML : sections titrées et tableaux de spécifications."""

from __future__ import annotations

from pathlib import Path

from catalog.reading.html_reader import lire
from catalog.reading.page import Page

FICHE = Path(__file__).parent / "fixtures" / "fiche_produit.html"


def _par_titre(pages: list[Page]) -> dict[str | None, str]:
    return {p.titre: p.texte for p in pages}


def test_sections_dans_l_ordre_du_document() -> None:
    pages = lire(FICHE)
    # « Products » (menu) et « Specifications » n'ont pas de texte propre.
    assert [p.titre for p in pages] == [
        "CAM-100",
        "Camera",
        "Power",
        "Environmental & Electrical",
    ]
    assert [p.numero for p in pages] == list(range(1, len(pages) + 1))


def test_ligne_de_groupe_ouvre_une_section() -> None:
    assert _par_titre(lire(FICHE))["Power"] == (
        "Power Supply | 12 VDC ±25%/PoE (802.3af)\nPower Consumption | Max. 6.5 W"
    )


def test_cellule_fusionnee_repetee_sur_chaque_rangee() -> None:
    texte = _par_titre(lire(FICHE))["Environmental & Electrical"]
    assert texte.splitlines() == [
        "Input Voltage | PoE+(IEEE802.3at, Class4), 12VDC",
        "Power Consumption | PoE | Max. 22.5W",
        "Power Consumption | 12VDC | Max. 20W",
    ]


def test_texte_en_ligne_garde_ses_espaces() -> None:
    assert _par_titre(lire(FICHE))["CAM-100"] == "Fixed dome network camera."


def test_scripts_styles_doublons_et_sections_vides_ecartes() -> None:
    pages = lire(FICHE)
    tout = "\n".join(p.texte for p in pages)
    assert "ne doit pas" not in tout
    assert "color" not in tout
    assert [p.titre for p in pages].count("Environmental & Electrical") == 1
    assert "Empty" not in [p.titre for p in pages]


def test_encodage_declare_respecte(tmp_path: Path) -> None:
    chemin = tmp_path / "latin1.html"
    chemin.write_bytes(
        '<html><head><meta charset="iso-8859-1"></head><body>'
        "<h2>Power</h2><p>12 V ± 10 %, 6 W maximum</p></body></html>".encode("latin-1")
    )
    assert lire(chemin)[0].texte == "12 V ± 10 %, 6 W maximum"
