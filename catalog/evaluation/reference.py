"""Corrigé d'évaluation : format d'un fichier ``eval/reference/<id>.json``.

Le corrigé est annoté à la main par Quentin (eval/GUIDE.md) ; ce module le
lit et refuse ce qui est malformé, il ne l'écrit jamais. Chaque fichier
porte les champs de la cible, tous : un champ absent de la notice s'écrit
``"valeur": null`` avec ``"etat_attendu": "absent"``, pour qu'un oubli
d'annotation ne passe pas pour un absent.

Lancé en module (``python -m catalog.evaluation.reference``), il valide le
dossier ``eval/reference/`` et signale les fichiers malformés.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from catalog.extraction.cible import ChampCible, Cible, charger_cible

REFERENCE_DIR = Path(__file__).resolve().parents[2] / "eval" / "reference"

EtatAttendu = Literal["sur", "douteux", "absent"]
Valeur = bool | float | str | None


class ValeurAnnotee(BaseModel):
    """La bonne réponse pour un champ, avec l'endroit où la notice la donne.

    ``page`` pour un PDF (numérotée à partir de 1), ``section`` (titre de la
    section) pour une page web : exactement l'un des deux quand une valeur
    est présente. ``note`` garde ce que le modèle SecurScope ne prévoit pas
    (« 24 VAC », « chauffage inclus »).
    """

    model_config = ConfigDict(extra="forbid")

    valeur: Valeur
    etat_attendu: EtatAttendu
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    extrait: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _coherence(self) -> Self:
        if self.valeur is None:
            if self.etat_attendu != "absent":
                raise ValueError("valeur nulle : etat_attendu doit être « absent »")
            return self
        if self.etat_attendu == "absent":
            raise ValueError("valeur présente : etat_attendu ne peut être « absent »")
        if (self.page is None) == (self.section is None):
            raise ValueError("valeur présente : donner page (PDF) ou section (HTML)")
        if not self.extrait:
            raise ValueError("valeur présente : extrait obligatoire")
        return self


class Corrige(BaseModel):
    """Le corrigé d'une notice : identification et une valeur annotée par champ."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*-\d{2}$")
    reference: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotateur: str = Field(min_length=1)
    date_annotation: date
    champs: dict[str, ValeurAnnotee]


def _verifier_type(champ: ChampCible, valeur: Valeur) -> str | None:
    """Retourne le motif de refus si la valeur n'a pas le type du champ."""
    if valeur is None:
        return None
    if champ.type == "booleen" and not isinstance(valeur, bool):
        return "booléen attendu"
    if champ.type == "nombre" and (
        isinstance(valeur, bool) or not isinstance(valeur, float)
    ):
        return f"nombre attendu (en {champ.unite})"
    if champ.type == "enum" and valeur not in champ.valeurs:
        return f"valeur hors énumération {list(champ.valeurs)}"
    return None


def verifier_contre_cible(corrige: Corrige, cible: Cible) -> list[str]:
    """Liste les écarts entre un corrigé et la cible : clés et types de valeur."""
    attendus = cible.par_cle()
    erreurs = [
        f"champ inconnu : {cle}" for cle in corrige.champs if cle not in attendus
    ]
    erreurs += [
        f"champ manquant : {cle}" for cle in attendus if cle not in corrige.champs
    ]
    for cle, annotee in corrige.champs.items():
        if cle in attendus:
            motif = _verifier_type(attendus[cle], annotee.valeur)
            if motif:
                erreurs.append(f"{cle} : {motif}")
    return erreurs


class CorrigeInvalide(ValueError):
    """Un fichier de corrigé ne respecte pas le format ou la cible."""


def charger_corrige(chemin: Path, cible: Cible) -> Corrige:
    """Lit et valide un fichier de corrigé ; lève ``CorrigeInvalide`` sinon."""
    try:
        corrige = Corrige.model_validate_json(chemin.read_text(encoding="utf-8"))
    except ValidationError as exc:
        raise CorrigeInvalide(str(exc)) from exc
    erreurs = verifier_contre_cible(corrige, cible)
    if corrige.id != chemin.stem:
        erreurs.append(f"id « {corrige.id} » différent du nom de fichier")
    if erreurs:
        raise CorrigeInvalide("\n".join(erreurs))
    return corrige


def charger_corriges(dossier: Path, cible: Cible) -> dict[str, Corrige]:
    """Charge tous les corrigés d'un dossier (non récursif), indexés par id."""
    return {
        chemin.stem: charger_corrige(chemin, cible)
        for chemin in sorted(dossier.glob("*.json"))
    }


def valider_dossier(dossier: Path, cible: Cible) -> dict[str, str]:
    """Valide chaque fichier du dossier ; retourne les erreurs par nom de fichier."""
    erreurs: dict[str, str] = {}
    for chemin in sorted(dossier.glob("*.json")):
        try:
            charger_corrige(chemin, cible)
        except (CorrigeInvalide, json.JSONDecodeError, OSError) as exc:
            erreurs[chemin.name] = str(exc)
    return erreurs


def main() -> int:
    """Valide ``eval/reference/`` et affiche les fichiers malformés."""
    erreurs = valider_dossier(REFERENCE_DIR, charger_cible("camera", "alimentation"))
    for nom, message in erreurs.items():
        print(f"✗ {nom}\n  " + message.replace("\n", "\n  "))
    total = len(list(REFERENCE_DIR.glob("*.json")))
    print(f"{total - len(erreurs)}/{total} corrigé(s) valide(s)")
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
