"""Réponses brutes du modèle : enregistrement, relecture et interprétation.

Chaque appel est rangé sous une clé d'empreinte (modèle, version du prompt,
texte envoyé, schéma, paramètres, n° d'exécution) dans
``data/extractions/brut/<cle>.json``. Une clé déjà présente est rejouée sans
appel : ``evaluate`` refait citations, plausibilité et métriques depuis ces
fichiers, sans GPU (plan eval-alimentation, §2).

L'URL du serveur n'entre pas dans la clé : la même requête, lancée sur le PC
puis relue sur le NAS, doit retomber sur le même fichier. Ces fichiers
contiennent le texte des notices : ils ne sont pas versionnés.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

BRUT_DIR = Path(__file__).resolve().parents[2] / "data" / "extractions" / "brut"

# Sur /v1, Ollama coupe sans prévenir (``truncate`` et ``shift`` actifs,
# non réglables par requête) : un prompt coupé remonte un ``prompt_tokens``
# proche du contexte ; une génération qui atteint le contexte décale la
# fenêtre et efface le début de la notice, avec ``finish_reason=stop``.
MARGE_TRONCATURE_JETONS = 64

MotifEchec = Literal[
    "aucune_reponse",
    "troncature",
    "troncature_entree",
    "decalage_contexte",
    "json_malforme",
    "schema_invalide",
]


class Message(BaseModel):
    """Un message de la conversation envoyée au modèle."""

    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class RequeteModele(BaseModel):
    """Tout ce qui détermine une réponse, donc tout ce qui entre dans la clé."""

    model_config = ConfigDict(frozen=True)

    modele: str
    version_prompt: str
    messages: tuple[Message, ...]
    nom_schema: str
    schema_sortie: dict[str, Any]  # schéma JSON, libre par nature
    temperature: float = 0.0
    max_jetons: int = 4096
    reasoning_effort: str | None = None
    graine: int | None = None
    execution: int = 0
    # Contexte réel du serveur et digest du modèle (``/api/ps`` d'Ollama) :
    # dans la clé, pour qu'un contexte relevé ou un modèle retiré sous le
    # même nom ne rejoue pas une ancienne réponse.
    contexte_jetons: int | None = None
    empreinte_modele: str | None = None

    def cle(self) -> str:
        """Empreinte SHA-256 de la requête, sur un JSON canonique."""
        canonique = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
        )
        return hashlib.sha256(canonique.encode("utf-8")).hexdigest()


class EssaiBrut(BaseModel):
    """Une réponse du serveur, gardée telle qu'il l'a rendue.

    Le plus souvent un 200 ; aussi le 400 de Groq « JSON hors schéma », qui
    est une réponse du modèle et non une panne.
    """

    corps: dict[str, Any]  # JSON du serveur, non typé
    duree_s: float
    horodatage: str
    graine: int | None = None  # graine envoyée, changée à chaque nouvel essai


class EnregistrementBrut(BaseModel):
    """Une requête et toutes les réponses obtenues pour elle, dans l'ordre."""

    cle: str
    requete: RequeteModele
    essais: list[EssaiBrut]


class EchecReponse(Exception):
    """Aucune réponse exploitable : compte comme échec, jamais comme ``absent``."""

    def __init__(self, motif: MotifEchec, detail: str = "") -> None:
        """Garde le motif, repris tel quel dans les résultats."""
        super().__init__(f"{motif}: {detail}" if detail else motif)
        self.motif: MotifEchec = motif
        self.detail = detail


class ReponseInterpretee[T: BaseModel](BaseModel):
    """Sortie validée d'un essai, avec ce qu'il faut pour la mesure."""

    valeur: T
    essai: int
    finish_reason: str | None
    usage: dict[str, Any]  # JSON du serveur, non typé
    reflexion: str | None
    duree_s: float


def maintenant() -> str:
    """Horodatage UTC ISO 8601, à la seconde."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def _contenu(corps: dict[str, Any]) -> tuple[str, str | None, str | None]:
    """Texte, raison d'arrêt et réflexion du premier choix d'une réponse."""
    choix = corps.get("choices") or [{}]
    message = choix[0].get("message") or {}
    # Ollama rend la réflexion dans ``reasoning``, d'autres dans
    # ``reasoning_content`` ; on garde ce qui existe.
    reflexion = message.get("reasoning") or message.get("reasoning_content")
    return message.get("content") or "", choix[0].get("finish_reason"), reflexion


def _verifier_contexte(usage: dict[str, Any], contexte_jetons: int | None) -> None:
    """Lève un échec si l'usage trahit une coupe silencieuse d'Ollama.

    Sans contexte connu (Groq), rien n'est contrôlé : avec Ollama, le point
    d'entrée doit le fournir.
    """
    if contexte_jetons is None:
        return
    entree = int(usage.get("prompt_tokens") or 0)
    sortie = int(usage.get("completion_tokens") or 0)
    if entree >= contexte_jetons - MARGE_TRONCATURE_JETONS:
        detail = f"{entree} jetons d'entrée pour un contexte de {contexte_jetons}"
        raise EchecReponse("troncature_entree", detail)
    if entree + sortie >= contexte_jetons:
        detail = f"{entree} + {sortie} jetons pour un contexte de {contexte_jetons}"
        raise EchecReponse("decalage_contexte", detail)


def interpreter_essai[T: BaseModel](
    essai: EssaiBrut, modele: type[T], contexte_jetons: int | None = None
) -> tuple[T, str | None, str | None]:
    """Valide un essai ; lève ``EchecReponse`` s'il est inexploitable.

    Une réponse coupée (``finish_reason == "length"``) est un échec même si
    son JSON se lit : un champ manquant y passerait pour ``absent``.
    """
    if "error" in essai.corps:
        raise EchecReponse("schema_invalide", str(essai.corps["error"])[:500])
    texte, finish_reason, reflexion = _contenu(essai.corps)
    if finish_reason == "length":
        raise EchecReponse("troncature", "finish_reason=length")
    _verifier_contexte(essai.corps.get("usage") or {}, contexte_jetons)
    try:
        donnees = json.loads(texte)
    except json.JSONDecodeError as erreur:
        raise EchecReponse("json_malforme", str(erreur)) from erreur
    try:
        return modele.model_validate(donnees), finish_reason, reflexion
    except ValidationError as erreur:
        raise EchecReponse("schema_invalide", str(erreur)) from erreur


def interpreter[T: BaseModel](
    enregistrement: EnregistrementBrut, modele: type[T]
) -> ReponseInterpretee[T]:
    """Premier essai exploitable d'un enregistrement ; sinon l'échec du dernier."""
    echec = EchecReponse("aucune_reponse")
    for rang, essai in enumerate(enregistrement.essais):
        try:
            valeur, finish_reason, reflexion = interpreter_essai(
                essai, modele, enregistrement.requete.contexte_jetons
            )
        except EchecReponse as erreur:
            echec = erreur
            continue
        return ReponseInterpretee[T](
            valeur=valeur,
            essai=rang,
            finish_reason=finish_reason,
            usage=essai.corps.get("usage") or {},
            reflexion=reflexion,
            duree_s=essai.duree_s,
        )
    raise echec


class ArchiveBrute:
    """Dossier des réponses brutes, une par clé."""

    def __init__(self, dossier: Path = BRUT_DIR) -> None:
        """Le dossier est créé à la première écriture."""
        self.dossier = dossier

    def _chemin(self, cle: str) -> Path:
        return self.dossier / f"{cle}.json"

    def lire(self, cle: str) -> EnregistrementBrut | None:
        """Enregistrement rangé sous cette clé, ou ``None``."""
        chemin = self._chemin(cle)
        if not chemin.exists():
            return None
        enregistrement = EnregistrementBrut.model_validate_json(
            chemin.read_text(encoding="utf-8")
        )
        if enregistrement.requete.cle() != cle:
            raise ValueError(f"{chemin.name} : la requête ne correspond pas à sa clé")
        return enregistrement

    def ecrire(self, enregistrement: EnregistrementBrut) -> Path:
        """Écrit l'enregistrement d'un bloc (fichier temporaire puis renommage)."""
        self.dossier.mkdir(parents=True, exist_ok=True)
        chemin = self._chemin(enregistrement.cle)
        temporaire = chemin.with_suffix(".tmp")
        temporaire.write_text(
            enregistrement.model_dump_json(indent=2), encoding="utf-8"
        )
        temporaire.replace(chemin)
        return chemin


def obtenir(
    archive: ArchiveBrute,
    requete: RequeteModele,
    appeler: Callable[[RequeteModele], EnregistrementBrut],
) -> EnregistrementBrut:
    """Rejoue la réponse archivée, ou appelle le modèle et archive sa réponse.

    Une réponse inexploitable (troncature, JSON malformé) est archivée comme
    les autres : c'est un résultat de l'expérience. Une erreur de transport
    ne l'est pas (``appeler`` lève) : le prochain passage réessaiera.
    """
    deja = archive.lire(requete.cle())
    if deja is not None:
        return deja
    enregistrement = appeler(requete)
    archive.ecrire(enregistrement)
    return enregistrement
