"""Orchestration de l'extraction d'un bloc sur un ou plusieurs documents.

Pour chaque document : lecture, sélection des pages du bloc, un appel au
modèle (rejoué depuis l'archive brute s'il a déjà eu lieu), puis l'état final
de chaque champ (``etats.py``).

Une réponse inexploitable (troncature, JSON invalide) ou un appel en échec
donne un résultat sans champs, avec son motif : c'est un échec, jamais une
série d'``absent`` (plan eval-alimentation, §3).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from catalog.extraction.brut import (
    ArchiveBrute,
    EchecReponse,
    EnregistrementBrut,
    Message,
    MotifEchec,
    ReponseInterpretee,
    RequeteModele,
    interpreter,
    obtenir,
)
from catalog.extraction.cible import Cible
from catalog.extraction.client import EchecAppel
from catalog.extraction.etats import ChampExtrait, etats_champs, incoherences
from catalog.extraction.prompts import (
    VERSION_PROMPT,
    ReponseBloc,
    gabarit,
    message_utilisateur,
    schema_sortie,
)
from catalog.reading import html_reader, pdf_reader
from catalog.reading.chunker import selectionner
from catalog.reading.page import Page

ECHEC_APPEL: MotifEchec = "echec_appel"
GRAINE = 20261015


@dataclass(frozen=True)
class ConfigModele:
    """Réglages d'un modèle, tous enregistrés dans la clé des réponses brutes.

    ``contexte_jetons`` et ``empreinte_modele`` viennent de ``/api/ps`` avec
    Ollama (obligatoires) ; ``None`` seulement pour Groq.
    """

    modele: str
    contexte_jetons: int | None
    empreinte_modele: str | None
    reasoning_effort: str = "none"
    max_jetons: int = 2048
    temperature: float = 0.0
    graine: int | None = GRAINE


@dataclass(frozen=True)
class Moteur:
    """Ce qu'il faut pour interroger le modèle : réglages, archive, appel."""

    config: ConfigModele
    archive: ArchiveBrute
    appeler: Callable[[RequeteModele], EnregistrementBrut]


class Document(BaseModel):
    """Un document archivé et la référence qu'il doit décrire."""

    id: str
    reference: str
    chemin: Path
    sha256: str = ""


class ResultatBloc(BaseModel):
    """Le résultat d'un bloc sur un document, pour une exécution."""

    document: str
    reference: str
    sha256: str
    execution: int
    modele: str
    version_prompt: str
    pages: list[int]
    cle_brute: str | None = None
    motif_echec: str | None = None
    detail_echec: str | None = None
    champs: dict[str, ChampExtrait] = {}
    incoherents: list[str] = []
    essai: int | None = None
    duree_s: float | None = None
    usage: dict[str, Any] = {}  # JSON du serveur, non typé


def lire_document(chemin: Path) -> list[Page]:
    """Pages d'un PDF ou sections d'une fiche HTML, selon l'extension."""
    if chemin.suffix.lower() == ".pdf":
        return pdf_reader.lire(chemin)
    return html_reader.lire(chemin)


def construire_requete(
    cible: Cible,
    reference: str,
    pages: Sequence[Page],
    config: ConfigModele,
    execution: int,
) -> RequeteModele:
    """La requête d'un bloc : prompt système, pages retenues, schéma strict."""
    return RequeteModele(
        modele=config.modele,
        version_prompt=VERSION_PROMPT,
        messages=(
            Message(role="system", content=gabarit(cible)),
            Message(role="user", content=message_utilisateur(reference, pages)),
        ),
        nom_schema=f"{cible.famille}_{cible.bloc}",
        schema_sortie=schema_sortie(cible),
        temperature=config.temperature,
        max_jetons=config.max_jetons,
        reasoning_effort=config.reasoning_effort,
        graine=config.graine,
        execution=execution,
        contexte_jetons=config.contexte_jetons,
        empreinte_modele=config.empreinte_modele,
    )


def _interroger(
    requete: RequeteModele, moteur: Moteur
) -> ReponseInterpretee[ReponseBloc]:
    """Réponse validée du modèle (archivée ou obtenue) ; sinon EchecReponse.

    Un appel en échec (réseau, quota, contexte trop court) devient un échec
    de motif echec_appel ; il n'est pas archivé, le passage suivant
    réessaiera.
    """
    try:
        enregistrement = obtenir(moteur.archive, requete, moteur.appeler)
    except EchecAppel as erreur:
        raise EchecReponse(ECHEC_APPEL, str(erreur)) from erreur
    return interpreter(enregistrement, ReponseBloc)


def extraire_document(
    document: Document,
    pages: Sequence[Page],
    cible: Cible,
    execution: int,
    moteur: Moteur,
) -> ResultatBloc:
    """Extrait le bloc d'un document déjà lu ; les pages sont sélectionnées ici."""
    retenues = selectionner(list(pages), cible.bloc)
    requete = construire_requete(
        cible, document.reference, retenues, moteur.config, execution
    )
    resultat = ResultatBloc(
        document=document.id,
        reference=document.reference,
        sha256=document.sha256,
        execution=execution,
        modele=moteur.config.modele,
        version_prompt=VERSION_PROMPT,
        pages=[p.numero for p in retenues],
        cle_brute=requete.cle(),
    )
    try:
        reponse = _interroger(requete, moteur)
    except EchecReponse as erreur:
        return resultat.model_copy(
            update={"motif_echec": erreur.motif, "detail_echec": erreur.detail}
        )
    return resultat.model_copy(
        update={
            "champs": etats_champs(reponse.valeur, cible, retenues),
            "incoherents": incoherences(reponse.valeur),
            "essai": reponse.essai,
            "duree_s": reponse.duree_s,
            "usage": reponse.usage,
        }
    )


def executer_lot(
    documents: Sequence[Document],
    cible: Cible,
    moteur: Moteur,
    executions: int,
    sortie: Path,
) -> Iterator[ResultatBloc]:
    """Extrait chaque document ``executions`` fois et écrit chaque résultat.

    Un document est lu une seule fois. Les résultats vont dans
    ``sortie/<id>_e<n>.json`` ; ils sont rendus au fur et à mesure.
    """
    sortie.mkdir(parents=True, exist_ok=True)
    for document in documents:
        pages = lire_document(document.chemin)
        for execution in range(executions):
            resultat = extraire_document(document, pages, cible, execution, moteur)
            chemin = sortie / f"{document.id}_e{execution}.json"
            chemin.write_text(resultat.model_dump_json(indent=2), encoding="utf-8")
            yield resultat
