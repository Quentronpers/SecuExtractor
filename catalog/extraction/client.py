"""Appel du modèle d'extraction par l'API compatible OpenAI (``/v1/chat/completions``).

Ollama en local, Groq en comparaison : même API, le modèle n'est qu'un
paramètre (plan eval-alimentation, §2). La sortie est contrainte par un
schéma JSON au format strict et validée par Pydantic.

Pièges couverts (plan, §3) : réponse tronquée → échec, jamais ``absent`` ;
contexte trop court pour la requête → refus avant envoi ; 429 → attente
croissante (``Retry-After`` d'abord), arrêt net si le quota du jour est
épuisé ; réponse illisible → un nouvel essai avec une autre graine, puis
échec. Configuration par l'environnement (``LLM_BASE_URL``, ``LLM_MODEL``,
``LLM_API_KEY``) dans le point d'entrée, pas ici.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests
from pydantic import BaseModel

from catalog.extraction.brut import (
    MARGE_TRONCATURE_JETONS,
    EchecReponse,
    EnregistrementBrut,
    EssaiBrut,
    RequeteModele,
    interpreter_essai,
    maintenant,
)

DELAI_S = 600.0  # un 14b en local, réflexion comprise, peut être lent
TENTATIVES_HTTP = 5  # 429, 5xx et erreurs réseau
ATTENTE_BASE_S = 2.0
ATTENTE_MAX_S = 120.0  # au-delà, ``Retry-After`` annonce un quota épuisé
ESSAIS_REPONSE = 2  # réponse illisible : un nouvel essai, puis échec
STATUTS_REPRISE = {429, 500, 502, 503, 504}
CARACTERES_PAR_JETON = 3  # estimation prudente (surestime les jetons)
CODE_SCHEMA_GROQ = "json_validate_failed"  # 400 de Groq : JSON hors schéma

# JSON du serveur : non typé par nature, d'où ``dict[str, Any]`` aux frontières.
JSON = dict[str, Any]


@dataclass
class ReponseHTTP:
    """Ce que le client lit d'une réponse HTTP."""

    statut: int
    corps: JSON | None
    entetes: dict[str, str] = field(default_factory=dict)
    texte: str = ""


class Transport(Protocol):
    """Envoi d'un POST JSON ; remplacé par un faux dans les tests."""

    def __call__(
        self, url: str, entetes: dict[str, str], corps: JSON, delai_s: float
    ) -> ReponseHTTP:
        """Envoie la requête et rend la réponse, ou lève ``OSError``."""
        ...


class EchecAppel(Exception):
    """Le serveur n'a pas répondu utilement : rien n'est archivé."""


class ContexteInsuffisant(EchecAppel):
    """Le contexte du serveur ne tient pas la requête : Ollama la couperait."""


def transport_requests(
    url: str, entetes: dict[str, str], corps: JSON, delai_s: float
) -> ReponseHTTP:
    """Transport réel, par ``requests`` ; erreurs réseau rendues en ``OSError``."""
    try:
        reponse = requests.post(url, headers=entetes, json=corps, timeout=delai_s)
    except requests.RequestException as erreur:
        raise OSError(str(erreur)) from erreur
    try:
        lu: object = reponse.json()
    except ValueError:
        lu = None
    return ReponseHTTP(
        statut=reponse.status_code,
        corps=lu if isinstance(lu, dict) else None,
        entetes=dict(reponse.headers),
        texte=reponse.text[:2000],
    )


def corps_requete(
    requete: RequeteModele, champ_max_jetons: str, graine: int | None
) -> JSON:
    """Corps ``chat/completions`` ; les réglages non fixés ne sont pas envoyés."""
    corps: JSON = {
        "model": requete.modele,
        "messages": [m.model_dump() for m in requete.messages],
        "temperature": requete.temperature,
        champ_max_jetons: requete.max_jetons,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": requete.nom_schema,
                "strict": True,
                "schema": requete.schema_sortie,
            },
        },
    }
    if requete.reasoning_effort is not None:
        corps["reasoning_effort"] = requete.reasoning_effort
    if graine is not None:
        corps["seed"] = graine
    return corps


def verifier_contexte(requete: RequeteModele) -> None:
    """Refuse une requête que le contexte du serveur ne tiendrait pas."""
    if requete.contexte_jetons is None:
        return
    caracteres = sum(len(m.content) for m in requete.messages)
    caracteres += len(str(requete.schema_sortie))
    besoin = caracteres // CARACTERES_PAR_JETON + requete.max_jetons
    if besoin + MARGE_TRONCATURE_JETONS > requete.contexte_jetons:
        raise ContexteInsuffisant(
            f"environ {besoin} jetons pour un contexte de {requete.contexte_jetons}"
        )


def attente_reprise(tentative: int, entetes: dict[str, str]) -> float:
    """Délai avant la tentative suivante : ``Retry-After`` s'il est donné.

    Un ``Retry-After`` au-delà de ``ATTENTE_MAX_S`` lève ``EchecAppel`` :
    le quota du jour est épuisé, attendre ne sert à rien.
    """
    for nom, valeur in entetes.items():
        if nom.lower() != "retry-after":
            continue
        try:
            secondes = max(float(valeur), 0.0)
        except ValueError:
            break
        if secondes > ATTENTE_MAX_S:
            raise EchecAppel(f"quota épuisé : Retry-After {valeur} s")
        return secondes
    return min(ATTENTE_BASE_S * 2**tentative, ATTENTE_MAX_S)


def _erreur_de_schema(reponse: ReponseHTTP) -> bool:
    """400 de Groq quand le JSON généré sort du schéma : une réponse du modèle."""
    erreur = (reponse.corps or {}).get("error")
    return (
        reponse.statut == 400
        and isinstance(erreur, dict)
        and erreur.get("code") == CODE_SCHEMA_GROQ
    )


class ClientCompatibleOpenAI:
    """Client d'un serveur ``/v1/chat/completions`` (Ollama, Groq…)."""

    def __init__(
        self,
        url_base: str,
        cle_api: str | None = None,
        champ_max_jetons: str = "max_tokens",
        transport: Transport = transport_requests,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        """``champ_max_jetons`` : Ollama ne lit que ``max_tokens``.

        Groq le tient pour obsolète et préfère ``max_completion_tokens``.
        """
        self.url = url_base.rstrip("/") + "/chat/completions"
        self.cle_api = cle_api
        self.champ_max_jetons = champ_max_jetons
        self.transport = transport
        self.dormir = dormir

    def _entetes(self) -> dict[str, str]:
        entetes = {"Content-Type": "application/json"}
        if self.cle_api:
            entetes["Authorization"] = f"Bearer {self.cle_api}"
        return entetes

    def _tenter(self, corps: JSON) -> tuple[ReponseHTTP | None, str]:
        """Une tentative : la réponse et la raison de l'échec.

        Réponse ``None`` si le réseau a coupé ; raison vide si la réponse
        vient du modèle.
        """
        try:
            reponse = self.transport(self.url, self._entetes(), corps, DELAI_S)
        except OSError as erreur:
            return None, f"réseau : {erreur}"
        if (reponse.statut == 200 and reponse.corps) or _erreur_de_schema(reponse):
            return reponse, ""
        if reponse.statut == 200:
            return reponse, "HTTP 200 sans corps JSON"
        return reponse, f"HTTP {reponse.statut} : {reponse.texte[:200]}"

    def _poster(self, corps: JSON) -> EssaiBrut:
        """Un POST qui rend une réponse du modèle, après reprises ; sinon lève."""
        raison = ""
        for tentative in range(TENTATIVES_HTTP):
            debut = time.monotonic()
            reponse, raison = self._tenter(corps)
            if reponse is not None and reponse.corps is not None and not raison:
                return EssaiBrut(
                    corps=reponse.corps,
                    duree_s=time.monotonic() - debut,
                    horodatage=maintenant(),
                    graine=corps.get("seed"),
                )
            statut = reponse.statut if reponse is not None else 0
            if statut not in STATUTS_REPRISE | {0, 200}:
                break
            if tentative + 1 < TENTATIVES_HTTP:
                entetes = reponse.entetes if reponse is not None else {}
                self.dormir(attente_reprise(tentative, entetes))
        raise EchecAppel(raison)

    def executer(
        self, requete: RequeteModele, modele: type[BaseModel]
    ) -> EnregistrementBrut:
        """Interroge le modèle et rend tous les essais, exploitables ou non.

        Une réponse illisible (JSON malformé, hors schéma) est redemandée une
        fois avec une autre graine, sans quoi Ollama rendrait la même ; une
        réponse tronquée ne l'est pas, elle le serait encore. Si le nouvel
        essai échoue au transport, le premier est rendu quand même.
        """
        verifier_contexte(requete)
        essais: list[EssaiBrut] = []
        for rang in range(ESSAIS_REPONSE):
            graine = requete.graine if rang == 0 else (requete.graine or 0) + rang
            try:
                essai = self._poster(
                    corps_requete(requete, self.champ_max_jetons, graine)
                )
            except EchecAppel:
                if not essais:
                    raise
                break
            essais.append(essai)
            if not _a_redemander(essai, modele, requete.contexte_jetons):
                break
        return EnregistrementBrut(cle=requete.cle(), requete=requete, essais=essais)


def _a_redemander(
    essai: EssaiBrut, modele: type[BaseModel], contexte_jetons: int | None
) -> bool:
    """Vrai si l'essai est illisible au point qu'un nouvel essai a un sens."""
    try:
        interpreter_essai(essai, modele, contexte_jetons)
    except EchecReponse as echec:
        return echec.motif in ("json_malforme", "schema_invalide")
    return False
