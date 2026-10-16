"""Lecteur PDF : chaque difficulté vue sur les notices, reproduite en petit."""

from __future__ import annotations

from pathlib import Path

from catalog.reading.pdf_reader import lire
from tests.fabrique_pdf import PagePdf, ecrire_pdf


def _grille(page: PagePdf, rangees: list[list[str]], x0: float = 50) -> None:
    """Dessine un tableau réglé de colonnes de 100 pt et rangées de 20 pt."""
    colonnes = len(rangees[0])
    y0 = 100
    for i in range(len(rangees) + 1):
        page.trait(x0, y0 + 20 * i, x0 + 100 * colonnes, y0 + 20 * i)
    for j in range(colonnes + 1):
        page.trait(x0 + 100 * j, y0, x0 + 100 * j, y0 + 20 * len(rangees))
    for i, rangee in enumerate(rangees):
        for j, cellule in enumerate(rangee):
            if cellule:
                page.texte(x0 + 100 * j + 4, y0 + 20 * i + 14, cellule)


def test_une_page_par_page_du_document(tmp_path: Path) -> None:
    premiere, seconde = PagePdf(), PagePdf()
    premiere.texte(50, 100, "Camera features")
    seconde.texte(50, 100, "Power consumption 7.7 W")
    pages = lire(ecrire_pdf(tmp_path / "n.pdf", [premiere, seconde]))
    assert [p.numero for p in pages] == [1, 2]
    assert pages[1].texte == "Power consumption 7.7 W"
    assert pages[0].titre is None


def test_mots_rapproches_restent_separes(tmp_path: Path) -> None:
    # « Typical » mesure 31,67 pt en Helvetica 10 : 2 pt d'écart seulement.
    page = PagePdf()
    page.texte(50, 100, "Typical")
    page.texte(50 + 31.67 + 2, 100, "4.8W")
    assert lire(ecrire_pdf(tmp_path / "n.pdf", [page]))[0].texte == "Typical 4.8W"


def test_deux_colonnes_lues_l_une_apres_l_autre(tmp_path: Path) -> None:
    # Chaque colonne remplit sa moitié de page, comme sur une notice Bosch.
    gauche = [f"gauche ligne {i} avec un texte assez long" for i in range(8)]
    droite = [f"droite ligne {i} avec un texte assez long" for i in range(8)]
    page = PagePdf()
    for i in range(8):
        page.texte(50, 100 + 14 * i, gauche[i])
        page.texte(320, 100 + 14 * i, droite[i])
    lignes = lire(ecrire_pdf(tmp_path / "n.pdf", [page]))[0].texte.splitlines()
    assert lignes[:8] == gauche
    assert lignes[-8:] == droite


def test_tableau_libelle_valeur_non_coupe(tmp_path: Path) -> None:
    # Écart décentré entre libellés et valeurs : ce n'est pas une gouttière.
    page = PagePdf()
    for i in range(10):
        page.texte(50, 100 + 14 * i, f"Libelle {i}")
        page.texte(180, 100 + 14 * i, f"valeur {i} W")
    texte = lire(ecrire_pdf(tmp_path / "n.pdf", [page]))[0].texte
    assert "Libelle 3 valeur 3 W" in texte.splitlines()


def test_texte_superpose_lu_dans_l_ordre_du_flux(tmp_path: Path) -> None:
    page = PagePdf()
    page.texte(50, 100, "Power Input")
    page.texte(120, 100, "95W PoH/PoE")
    page.texte(120, 100, "DC 48V")
    texte = lire(ecrire_pdf(tmp_path / "n.pdf", [page]))[0].texte
    assert "95W PoH/PoE" in texte
    assert "DC 48V" in texte


def test_tableau_large_repris_avec_l_en_tete_des_modeles(tmp_path: Path) -> None:
    premiere, seconde = PagePdf(), PagePdf()
    _grille(
        premiere,
        [["Camera", "Model", "CAM-A", "CAM-B"], ["Video", "Codec", "H.265", "H.264"]],
    )
    _grille(
        seconde,
        [["General", "Weight", "1 kg", ""], ["", "Power", "5 W", "7 W"]],
    )
    pages = lire(ecrire_pdf(tmp_path / "n.pdf", [premiere, seconde]))
    assert "Camera | Model | CAM-A | CAM-B" in pages[0].texte
    lignes = pages[1].texte.splitlines()
    assert "(en-tête repris de la page 1) Camera | Model | CAM-A | CAM-B" in lignes
    assert "Power | 5 W | 7 W" in lignes


def test_tableau_a_deux_colonnes_non_duplique(tmp_path: Path) -> None:
    page = PagePdf()
    _grille(page, [["Power", "12 V DC"], ["Weight", "1 kg"]])
    texte = lire(ecrire_pdf(tmp_path / "n.pdf", [page]))[0].texte
    assert "Tableau" not in texte
    assert texte.count("12 V DC") == 1
