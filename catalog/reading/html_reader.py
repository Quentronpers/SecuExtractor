"""Texte structuré d'une fiche produit HTML archivée, découpé en sections.

Une section s'ouvre à chaque titre (``h1``…``h6``) et à chaque ligne de
groupe d'un tableau de spécifications (une seule cellule sur toute la
largeur : « Power » chez Dahua, « General » chez Uniview). Chaque rangée de
tableau devient une ligne « libellé | valeur » ; une cellule fusionnée sur
plusieurs rangées (``rowspan``, Hanwha) est répétée sur chacune.

Les sections vides et les doublons exacts (Hanwha publie deux fois ses
tableaux) sont retirés. Les sections sont numérotées dans l'ordre du
document à partir de 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

from catalog.reading.page import Page, nettoyer

IGNORES = {"script", "style", "noscript", "template", "svg", "iframe", "head"}
TITRES = {"h1", "h2", "h3", "h4", "h5", "h6"}
BLOCS = {
    "p", "div", "li", "ul", "ol", "dl", "dt", "dd", "br", "section", "article",
    "header", "footer", "main", "aside", "nav", "form", "caption", "blockquote",
}  # fmt: skip


@dataclass
class _Section:
    titre: str | None
    lignes: list[str] = field(default_factory=list)


@dataclass
class _Lecture:
    """État du parcours : sections closes, section en cours, ligne en cours."""

    sections: list[_Section] = field(default_factory=lambda: [_Section(None)])
    tampon: list[str] = field(default_factory=list)

    def ouvrir(self, titre: str) -> None:
        self.couper()
        self.sections.append(_Section(titre))

    def ajouter(self, ligne: str) -> None:
        self.couper()
        if ligne:
            self.sections[-1].lignes.append(ligne)

    def couper(self) -> None:
        texte = _compacter("".join(self.tampon))
        self.tampon.clear()
        if texte:
            self.sections[-1].lignes.append(texte)


def lire(chemin: Path | str) -> list[Page]:
    """Retourne les sections titrées d'une page produit archivée."""
    soupe = BeautifulSoup(Path(chemin).read_bytes(), "html.parser")
    lecture = _Lecture()
    _parcourir(soupe, lecture)
    lecture.couper()
    pages: list[Page] = []
    vues: set[tuple[str | None, str]] = set()
    for section in lecture.sections:
        texte = nettoyer("\n".join(section.lignes))
        if texte and (section.titre, texte) not in vues:
            vues.add((section.titre, texte))
            pages.append(Page(numero=len(pages) + 1, titre=section.titre, texte=texte))
    return pages


def _parcourir(noeud: Tag, lecture: _Lecture) -> None:
    """Parcourt l'arbre dans l'ordre du document."""
    for enfant in noeud.children:
        if type(enfant) is NavigableString:  # ni commentaire ni CDATA
            lecture.tampon.append(str(enfant))
        elif isinstance(enfant, Tag) and enfant.name not in IGNORES:
            _visiter(enfant, lecture)


def _visiter(element: Tag, lecture: _Lecture) -> None:
    """Traite un élément : titre, tableau, bloc ou élément en ligne."""
    if element.name in TITRES:
        lecture.ouvrir(_texte(element))
    elif element.name == "table":
        _lire_tableau(element, lecture)
    elif element.name in BLOCS:
        lecture.couper()
        _parcourir(element, lecture)
        lecture.couper()
    else:
        _parcourir(element, lecture)


def _lire_tableau(tableau: Tag, lecture: _Lecture) -> None:
    """Une ligne par rangée ; une rangée de groupe ouvre une section."""
    rangees = [r for r in tableau.find_all("tr") if r.find_parent("table") is tableau]
    largeur = max((_largeur(r) for r in rangees), default=0)
    reports: dict[int, tuple[str, int]] = {}  # colonne -> (texte, rangées restantes)
    for rangee in rangees:
        cellules = rangee.find_all(["td", "th"], recursive=False)
        if len(cellules) == 1 and largeur > 1 and _largeur(rangee) == largeur:
            lecture.ouvrir(_texte(cellules[0]))
            continue
        lecture.ajouter(" | ".join(t for t in _textes(cellules, reports) if t))


def _textes(cellules: list[Tag], reports: dict[int, tuple[str, int]]) -> list[str]:
    """Textes d'une rangée, cellules fusionnées des rangées précédentes comprises.

    ``reports`` associe à une colonne le texte d'une cellule fusionnée
    verticalement et le nombre de rangées qu'elle couvre encore ; il est mis
    à jour pour la rangée suivante.
    """
    textes: list[str] = []
    colonne = 0
    file = list(cellules)
    while file or colonne in reports:
        if colonne in reports:
            texte, reste = reports.pop(colonne)
            largeur = 1
        else:
            cellule = file.pop(0)
            texte, reste = _texte(cellule), _entier(cellule.get("rowspan"))
            largeur = _entier(cellule.get("colspan"))
        if reste > 1:
            reports[colonne] = (texte, reste - 1)
        textes.append(texte)
        colonne += largeur
    return textes


def _largeur(rangee: Tag) -> int:
    """Nombre de colonnes d'une rangée, fusions horizontales comprises."""
    cellules = rangee.find_all(["td", "th"], recursive=False)
    return sum(_entier(c.get("colspan")) for c in cellules)


def _entier(valeur: object) -> int:
    """Lit un attribut ``colspan`` ou ``rowspan`` ; 1 s'il est absent ou invalide."""
    try:
        return max(1, int(str(valeur))) if valeur is not None else 1
    except ValueError:
        return 1


def _texte(element: Tag) -> str:
    """Texte d'un élément sur une seule ligne."""
    return _compacter(element.get_text(" "))


def _compacter(texte: str) -> str:
    """Réduit tout blanc (sauts de ligne compris) à une espace."""
    return " ".join(texte.split())
