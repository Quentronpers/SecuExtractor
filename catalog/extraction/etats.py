"""État final des champs d'un bloc, calculé sans modèle.

- ``absent`` : pas de valeur rendue (ou champ non rendu) ;
- ``douteux`` : valeur rendue avec au moins un motif dans ``regle_echouee``
  (doute du modèle, type invalide, contrôle de citation, plausibilité) ;
- ``sur`` : valeur rendue, citation contrôlée, règles passées, aucun doute.

Le runner l'applique après l'appel ; l'évaluation le rejoue depuis les
réponses brutes, sans GPU (plan eval-alimentation, §2).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from catalog.extraction.cible import ChampCible, Cible, Valeur, verifier_type
from catalog.extraction.citations import verifier_citation
from catalog.extraction.prompts import ChampRendu, ReponseBloc
from catalog.plausibility.checker import verifier_plausibilite
from catalog.reading.page import Page

Etat = Literal["sur", "douteux", "absent"]

DOUTE_MODELE = "doute_modele"
TYPE_INVALIDE = "type_invalide"


class ChampExtrait(BaseModel):
    """Un champ après contrôles : valeur, citation, état et motifs."""

    cle: str
    valeur: Valeur
    etat: Etat
    page: int | None = None
    extrait: str | None = None
    doute: bool = False
    regle_echouee: str | None = None


def _motifs(
    champ: ChampCible,
    rendu: ChampRendu,
    plausibilite: str | None,
    pages: Sequence[Page],
) -> list[str]:
    """Tout ce qui empêche une valeur rendue d'être ``sur``."""
    motifs = []
    if verifier_type(champ, rendu.valeur):
        motifs.append(TYPE_INVALIDE)
    else:
        citation = verifier_citation(
            champ, rendu.valeur, rendu.page, rendu.extrait, pages
        )
        if citation:
            motifs.append(citation)
    if plausibilite:
        motifs.append(plausibilite)
    if rendu.doute:
        motifs.append(DOUTE_MODELE)
    return motifs


def _champ_extrait(
    champ: ChampCible,
    rendu: ChampRendu | None,
    plausibilite: str | None,
    pages: Sequence[Page],
) -> ChampExtrait:
    """L'état final d'un champ à partir de ce que le modèle a rendu."""
    if rendu is None or rendu.valeur is None:
        return ChampExtrait(cle=champ.cle, valeur=None, etat="absent")
    motifs = _motifs(champ, rendu, plausibilite, pages)
    return ChampExtrait(
        cle=champ.cle,
        valeur=rendu.valeur,
        etat="douteux" if motifs else "sur",
        page=rendu.page,
        extrait=rendu.extrait,
        doute=rendu.doute,
        regle_echouee="; ".join(motifs) or None,
    )


def etats_champs(
    reponse: ReponseBloc, cible: Cible, pages: Sequence[Page]
) -> dict[str, ChampExtrait]:
    """Contrôle chaque champ de la cible : citation, plausibilité, doute.

    Les règles de plausibilité ne voient que les valeurs du bon type : une
    chaîne dans un champ numérique est déjà ``douteux`` par son type.
    """
    rendus = reponse.root
    valeurs: dict[str, Valeur] = {}
    extraits: dict[str, str | None] = {}
    for champ in cible.champs:
        rendu = rendus.get(champ.cle)
        if (
            rendu
            and rendu.valeur is not None
            and not verifier_type(champ, rendu.valeur)
        ):
            valeurs[champ.cle] = rendu.valeur
            extraits[champ.cle] = rendu.extrait
    plausibilite = verifier_plausibilite(valeurs, extraits, pages)
    return {
        champ.cle: _champ_extrait(
            champ, rendus.get(champ.cle), plausibilite.get(champ.cle), pages
        )
        for champ in cible.champs
    }
