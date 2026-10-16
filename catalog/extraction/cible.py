"""Chargement des fichiers de cibles d'extraction (``cibles/<famille>_<bloc>.json``).

Les cibles disent quels champs extraire, avec la clé SecurScope, l'unité et
la définition (CLAUDE.md, « Le schéma d'extraction »). Elles servent au
prompt, au contrôle des valeurs et au format du corrigé d'évaluation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

CIBLES_DIR = Path(__file__).resolve().parent / "cibles"

TypeChamp = Literal["booleen", "nombre", "enum"]


class ChampCible(BaseModel):
    """Un champ visé : clé SecurScope, type de valeur et ce qu'il alimente."""

    model_config = ConfigDict(frozen=True)

    cle: str
    type: TypeChamp
    unite: str | None
    definition: str
    usage: Literal["calcul", "selection"]
    alimente: str
    valeurs: tuple[str, ...] = ()


class SourceCible(BaseModel):
    """D'où viennent les champs : dépôt, commit et fichiers de SecurScope."""

    depot: str
    commit: str
    date_commit: str
    fichiers: list[str]
    types_equipement: list[str]
    repris_le: str


class Cible(BaseModel):
    """L'ensemble des champs visés pour une famille et un bloc."""

    famille: str
    bloc: str
    description: str
    source: SourceCible
    types_catalogue: list[str]
    champs: list[ChampCible]

    def par_cle(self) -> dict[str, ChampCible]:
        """Index des champs par clé SecurScope."""
        return {champ.cle: champ for champ in self.champs}


def charger_cible(famille: str, bloc: str, dossier: Path = CIBLES_DIR) -> Cible:
    """Lit et valide le fichier de cibles d'une famille et d'un bloc."""
    chemin = dossier / f"{famille}_{bloc}.json"
    return Cible.model_validate(json.loads(chemin.read_text(encoding="utf-8")))
