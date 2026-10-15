"""Modèles Pydantic générés depuis schema/specifications-equipements.json.

Aucun modèle par type d'équipement n'est écrit à la main ici : ils sont
construits dynamiquement à l'import, directement depuis le schéma. C'est ce
qui garantit qu'aucun modèle ne peut diverger silencieusement de sa source de
vérité (CLAUDE.md, section « Le schéma d'extraction »).

Chaque champ métier devient un ``Champ[T]`` : la valeur seule ne suffit pas,
il faut aussi porter son état d'extraction, son niveau de fiabilité et sa
citation — c'est le principe central du projet (CLAUDE.md, « Le principe qui
commande tout »).
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "schema"
    / "specifications-equipements.json"
)


class NiveauFiabilite(StrEnum):
    """Niveau de fiabilité porté par chaque champ, indépendamment des autres."""

    EXTRAIT = "extrait"
    VERIFIE = "verifie"


class EtatExtraction(StrEnum):
    """État produit par le pipeline au sein du niveau ``extrait``."""

    SUR = "sur"
    DOUTEUX = "douteux"
    ABSENT = "absent"


class SourcePDF(BaseModel):
    """Citation depuis un document PDF archivé."""

    type: Literal["pdf"] = "pdf"
    fichier: str
    page: int
    extrait: str


class SourceHTML(BaseModel):
    """Citation depuis une page produit HTML archivée, figée par l'horodatage."""

    type: Literal["html"] = "html"
    fichier: str
    url: str
    date_capture: str
    selecteur: str | None = None
    extrait: str


Source = SourcePDF | SourceHTML


class Champ[T](BaseModel):
    """Une valeur extraite, avec son état, son niveau et sa citation source.

    Sans citation, la valeur est ``douteux`` quelle que soit la confiance du
    modèle (CLAUDE.md, règle d'extraction n°1). La validation s'applique
    aussi aux corrections faites depuis l'interface de relecture, pas
    seulement à la construction initiale.
    """

    model_config = ConfigDict(validate_assignment=True)

    valeur: T | None = None
    etat: EtatExtraction = EtatExtraction.ABSENT
    niveau: NiveauFiabilite = NiveauFiabilite.EXTRAIT
    regle_echouee: str | None = None
    source: Source | None = None


_TYPES_SIMPLES: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


def _type_python(champ_def: dict[str, Any]) -> Any:
    """Traduit le type déclaré dans le schéma en type Python pour Pydantic."""
    type_champ = champ_def["type"]
    if type_champ == "enum":
        return Literal[tuple(champ_def["valeurs"])]
    if type_champ == "array":
        return list[str]
    return _TYPES_SIMPLES[type_champ]


def _pascal_case(nom_type: str) -> str:
    return "".join(partie.capitalize() for partie in nom_type.split("_"))


def _charger_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _construire_modele(nom_type: str, definition: dict[str, Any]) -> type[BaseModel]:
    """Construit le modèle Pydantic d'un type d'équipement.

    Le champ ``source`` déclaré dans le schéma documente l'exigence générale
    de traçabilité plutôt qu'une valeur à extraire : il n'est pas dupliqué
    ici, chaque ``Champ`` portant déjà sa propre citation.
    """
    champs: dict[str, Any] = {}
    for nom_champ, champ_def in definition["champs"].items():
        if nom_champ == "source" and champ_def.get("type") == "object":
            continue
        # Type construit à l'exécution depuis le schéma : invisible pour mypy.
        type_champ: Any = Champ[_type_python(champ_def)]  # type: ignore[misc]
        champs[nom_champ] = (
            type_champ,
            Field(default_factory=type_champ, description=champ_def.get("note")),
        )
    return create_model(
        _pascal_case(nom_type),
        __doc__=definition.get("note") or definition.get("libelle"),
        **champs,
    )


SCHEMA: dict[str, Any] = _charger_schema()

METADONNEES: dict[str, dict[str, dict[str, Any]]] = {
    nom_type: definition["champs"]
    for famille in SCHEMA["familles"].values()
    for nom_type, definition in famille["types"].items()
}

MODELES: dict[str, type[BaseModel]] = {
    nom_type: _construire_modele(nom_type, definition)
    for famille in SCHEMA["familles"].values()
    for nom_type, definition in famille["types"].items()
}

globals().update({modele.__name__: modele for modele in MODELES.values()})
