"""Texte et tableaux de chaque page d'un PDF, via pdfplumber.

Les réglages viennent des notices du jeu d'évaluation (L2, 2026-10-16) :

- tolérance horizontale resserrée (1,5 pt au lieu de 3) : avec la valeur par
  défaut, les mots des fiches Axis se collent (« Typical4.8W,max10.7W ») ;
- deux colonnes de texte (Axis, Bosch, Vivotek) : quand une gouttière vide
  passe au centre de la page, chaque moitié est lue à part. Une gouttière
  décentrée sépare plutôt les libellés des valeurs d'un tableau (Hanwha,
  Milesight, Hikvision) et ne coupe pas la page ;
- texte superposé (Vivotek SD9364 : deux chaînes imprimées au même endroit) :
  la page est lue dans l'ordre du flux PDF, qui garde chaque chaîne entière ;
- tableaux à plusieurs colonnes de valeurs (une colonne par modèle, Milesight) :
  ajoutés sous le texte, une ligne par rangée, avec l'en-tête des modèles
  repris de la page précédente quand le tableau y commence.
"""

from __future__ import annotations

import logging
from pathlib import Path

# pdfplumber n'est pas typé (ignoré par mypy) : ses pages circulent en Any.
from typing import Any

import pdfplumber

from catalog.reading.page import Page, nettoyer

TOLERANCE_X = 1.5
# Bande où doit tomber le milieu d'une gouttière de mise en page à deux colonnes.
CENTRE_MIN, CENTRE_MAX = 0.42, 0.58
LARGEUR_GOUTTIERE_MIN = 6
SEUIL_SUPERPOSITIONS = 5

Rangee = list[str | None]

# pdfminer signale bruyamment des polices mal décrites, sans effet sur le texte.
logging.getLogger("pdfminer").setLevel(logging.ERROR)


def lire(chemin: Path | str) -> list[Page]:
    """Retourne le texte de chaque page d'un PDF, tableaux larges compris."""
    pages: list[Page] = []
    # Dernier en-tête de modèles vu, par nombre de colonnes : (page, rangée).
    entetes: dict[int, tuple[int, Rangee]] = {}
    with pdfplumber.open(chemin) as pdf:
        for numero, page in enumerate(pdf.pages, start=1):
            blocs = [_texte(page)]
            for objet in page.find_tables():
                tableau = objet.extract(x_tolerance=TOLERANCE_X)
                if not tableau:
                    continue
                if _est_entete(tableau[0]):
                    blocs.append(_rendre_tableau(tableau, None))
                    entetes[len(tableau[0])] = (numero, tableau[0])
                elif _est_large(tableau):
                    blocs.append(_rendre_tableau(tableau, entetes.get(len(tableau[0]))))
            pages.append(Page(numero=numero, texte=nettoyer("\n\n".join(blocs))))
    return pages


def _texte(page: Any) -> str:
    """Lit le texte d'une page selon sa mise en page."""
    if _superpositions(page) >= SEUIL_SUPERPOSITIONS:
        return page.extract_text(x_tolerance=TOLERANCE_X, use_text_flow=True) or ""
    milieu = _gouttiere(page)
    if milieu is None:
        return page.extract_text(x_tolerance=TOLERANCE_X) or ""
    x0, haut, x1, bas = page.bbox
    gauche = page.crop((x0, haut, milieu, bas)).extract_text(x_tolerance=TOLERANCE_X)
    droite = page.crop((milieu, haut, x1, bas)).extract_text(x_tolerance=TOLERANCE_X)
    return f"{gauche or ''}\n\n{droite or ''}"


def _gouttiere(page: Any) -> float | None:
    """Abscisse du milieu de la gouttière centrale, ou None s'il n'y en a pas.

    Une gouttière est une bande verticale qu'aucun mot ne traverse (un titre
    ou un pied de page pleine largeur sur cent mots est toléré).
    """
    mots = page.extract_words(x_tolerance=TOLERANCE_X)
    if len(mots) < 20:
        return None
    x0, x1 = int(page.bbox[0]), int(page.bbox[2])
    couverture = [0] * (x1 - x0 + 1)
    for mot in mots:
        for x in range(max(int(mot["x0"]), x0), min(int(mot["x1"]), x1) + 1):
            couverture[x - x0] += 1
    seuil = len(mots) // 100
    largeur = x1 - x0
    for debut, fin in _bandes_vides(couverture, seuil):
        milieu = (debut + fin) / 2
        centree = CENTRE_MIN * largeur <= milieu <= CENTRE_MAX * largeur
        if centree and fin - debut + 1 >= LARGEUR_GOUTTIERE_MIN:
            return x0 + milieu
    return None


def _bandes_vides(couverture: list[int], seuil: int) -> list[tuple[int, int]]:
    """Intervalles d'indices consécutifs dont la couverture ne dépasse pas le seuil."""
    bandes: list[tuple[int, int]] = []
    debut: int | None = None
    for i, valeur in enumerate([*couverture, seuil + 1]):
        if valeur <= seuil and debut is None:
            debut = i
        elif valeur > seuil and debut is not None:
            bandes.append((debut, i - 1))
            debut = None
    return bandes


def _superpositions(page: Any) -> int:
    """Compte les caractères différents imprimés l'un sur l'autre.

    Un caractère répété au même endroit (faux gras) n'en est pas un.
    """
    caracteres = sorted(page.chars, key=lambda c: (round(c["top"]), c["x0"]))
    total = 0
    for avant, apres in zip(caracteres, caracteres[1:], strict=False):
        meme_ligne = abs(avant["top"] - apres["top"]) < 1
        chevauche = apres["x0"] < avant["x0"] + (avant["x1"] - avant["x0"]) / 2
        if meme_ligne and chevauche and avant["text"] != apres["text"]:
            total += 1
    return total


def _est_entete(rangee: Rangee) -> bool:
    """Une première rangée pleine sur trois colonnes ou plus : un en-tête de modèles."""
    return len(rangee) >= 3 and all(cellule for cellule in rangee)


def _est_large(tableau: list[Rangee]) -> bool:
    """Un tableau dont une rangée porte au moins trois cellules remplies."""
    return any(sum(1 for c in rangee if c) >= 3 for rangee in tableau)


def _rendre_tableau(tableau: list[Rangee], entete: tuple[int, Rangee] | None) -> str:
    """Une ligne par rangée, cellules séparées par « | »."""
    lignes = ["Tableau :"]
    if entete:
        lignes.append(f"(en-tête repris de la page {entete[0]}) {_ligne(entete[1])}")
    lignes += [_ligne(rangee) for rangee in tableau]
    return "\n".join(lignes)


def _ligne(rangee: Rangee) -> str:
    """Cellules non vides d'une rangée, sauts de ligne internes aplatis."""
    return " | ".join(" ".join(c.split()) for c in rangee if c)
