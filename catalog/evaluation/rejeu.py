"""Rejeu d'une exécution depuis les réponses brutes, sans modèle ni notice.

Pour chaque résultat d'un dossier ``data/extractions/resultats/<run>/``, la
réponse brute est relue par sa clé et repasse par les contrôles du code
courant (citations, plausibilité, état final). Les pages sont reconstruites
depuis le message envoyé au modèle : les contrôles portent sur le texte
exact qu'il a lu, et le rejeu n'a besoin ni de ``data/sources/`` ni du GPU.
"""

from __future__ import annotations

import re
from pathlib import Path

from catalog.extraction.brut import (
    ArchiveBrute,
    EchecReponse,
    RequeteModele,
    interpreter,
)
from catalog.extraction.cible import Cible
from catalog.extraction.etats import etats_champs, incoherences
from catalog.extraction.prompts import ReponseBloc, message_utilisateur
from catalog.extraction.runner import ResultatBloc
from catalog.reading.page import Page

_REFERENCE = re.compile(r"\ATarget reference: (.*)\n")
_ENTETE = re.compile(r"^=== Page (\d+)(?: - (.*))? ===$", re.MULTILINE)
_DEBUT_PAGES = "\n\nDocument excerpts:\n\n"


class RejeuImpossible(ValueError):
    """Le message envoyé ne se relit pas en pages à l'identique."""


def pages_envoyees(requete: RequeteModele) -> list[Page]:
    """Les pages du message utilisateur, telles qu'envoyées au modèle.

    Le découpage est vérifié en reconstruisant le message : s'il diffère
    d'un caractère, le rejeu est refusé plutôt que faussé.
    """
    message = next(m.content for m in requete.messages if m.role == "user")
    reference = _REFERENCE.match(message)
    if reference is None or _DEBUT_PAGES not in message:
        raise RejeuImpossible("message utilisateur sans référence ni pages")
    corps = message.split(_DEBUT_PAGES, 1)[1].removesuffix("\n")
    entetes = list(_ENTETE.finditer(corps))
    pages = [
        Page(
            numero=int(entete[1]),
            titre=entete[2],
            texte=corps[entete.end() + 1 : suivant.start() - 2 if suivant else None],
        )
        for entete, suivant in zip(entetes, [*entetes[1:], None], strict=True)
    ]
    if message_utilisateur(reference[1], pages) != message:
        raise RejeuImpossible("pages mal reconstruites depuis le message")
    return pages


def rejouer(
    resultat: ResultatBloc, archive: ArchiveBrute, cible: Cible
) -> ResultatBloc:
    """Le résultat recalculé avec les contrôles actuels.

    Sans réponse archivée (appel en échec, jamais archivé), le résultat est
    rendu tel quel.
    """
    enregistrement = archive.lire(resultat.cle_brute) if resultat.cle_brute else None
    if enregistrement is None:
        return resultat
    pages = pages_envoyees(enregistrement.requete)
    vide = resultat.model_copy(
        update={"champs": {}, "incoherents": [], "motif_echec": None}
    )
    try:
        reponse = interpreter(enregistrement, ReponseBloc)
    except EchecReponse as erreur:
        return vide.model_copy(
            update={"motif_echec": erreur.motif, "detail_echec": erreur.detail}
        )
    return vide.model_copy(
        update={
            "detail_echec": None,
            "champs": etats_champs(reponse.valeur, cible, pages),
            "incoherents": incoherences(reponse.valeur),
            "essai": reponse.essai,
            "duree_s": reponse.duree_s,
            "usage": reponse.usage,
        }
    )


def charger_resultats(dossier: Path) -> list[ResultatBloc]:
    """Les résultats ``<id>_e<n>.json`` d'un dossier d'exécution, triés."""
    return [
        ResultatBloc.model_validate_json(chemin.read_text(encoding="utf-8"))
        for chemin in sorted(dossier.glob("*_e*.json"))
    ]
