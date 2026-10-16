"""Rappel du découpage : part des valeurs du corrigé dans les pages envoyées.

Une valeur dont la page n'est pas sélectionnée ne peut pas être extraite :
ce rappel borne tout le reste (plan eval-alimentation, L4). Chaque valeur
présente au corrigé est classée selon l'endroit où son extrait se trouve :

- ``retenue`` : dans une page sélectionnée ;
- ``ecartee`` : seulement dans des pages écartées par le découpage ;
- ``introuvable`` : dans aucune page lue. C'est un écart entre le corrigé et
  le lecteur (texte mal linéarisé, extrait recopié de l'écran), compté à part
  et hors rappel.

L'extrait est cherché comme le contrôle de citation le fait : tel quel ou
recomposé de fragments d'une même page. La « section » d'un corrigé HTML
est un libellé de ligne, pas un titre de section du lecteur : on ne s'y fie
pas, seul l'extrait compte.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Literal

from catalog.evaluation.reference import Corrige
from catalog.extraction.citations import CITATION_RECOMPOSEE, controler_extrait
from catalog.reading.chunker import selectionner
from catalog.reading.page import Page

Place = Literal["retenue", "ecartee", "introuvable"]


def _dans(extrait: str, page: Page) -> bool:
    """L'extrait est dans la page, tel quel ou recomposé."""
    return controler_extrait(page.numero, extrait, [page]) in (
        None,
        CITATION_RECOMPOSEE,
    )


def placer(extrait: str, pages: Sequence[Page], retenues: Sequence[Page]) -> Place:
    """Où se trouve l'extrait : page retenue, page écartée, ou nulle part."""
    if any(_dans(extrait, p) for p in retenues):
        return "retenue"
    if any(_dans(extrait, p) for p in pages):
        return "ecartee"
    return "introuvable"


def places(corrige: Corrige, pages: Sequence[Page], bloc: str) -> dict[str, Place]:
    """La place de chaque valeur présente au corrigé, par clé."""
    retenues = selectionner(list(pages), bloc)
    return {
        cle: placer(annotee.extrait, pages, retenues)
        for cle, annotee in corrige.champs.items()
        if annotee.valeur is not None and annotee.extrait
    }


def resumer(par_document: dict[str, dict[str, Place]]) -> dict[str, object]:
    """Effectifs, rappel (retenues / trouvées) et valeurs non retenues."""
    effectifs = Counter(p for d in par_document.values() for p in d.values())
    trouvees = effectifs["retenue"] + effectifs["ecartee"]
    return {
        "effectifs": dict(effectifs),
        "rappel": effectifs["retenue"] / trouvees if trouvees else None,
        "non_retenues": {
            doc: {cle: p for cle, p in d.items() if p != "retenue"}
            for doc, d in sorted(par_document.items())
            if any(p != "retenue" for p in d.values())
        },
    }
