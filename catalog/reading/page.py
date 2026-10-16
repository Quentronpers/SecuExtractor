"""Unité de lecture commune aux lecteurs PDF et HTML : la page.

Pour un PDF, une page est une page du document (numérotée à partir de 1).
Pour une fiche web, c'est une section titrée, numérotée dans l'ordre du
document : le titre tient lieu d'emplacement dans la citation (plan
eval-alimentation, §3).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

# Caractères de contrôle hors saut de ligne : certains PDF (Hanwha) mettent
# ``\x01`` à la place des espaces.
_CONTROLE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
_ESPACES = re.compile(r" {2,}")


class Page(BaseModel):
    """Le texte d'une page de PDF ou d'une section de fiche web."""

    model_config = ConfigDict(frozen=True)

    numero: int = Field(ge=1)
    texte: str
    titre: str | None = None


def nettoyer(texte: str) -> str:
    """Remplace les caractères de contrôle par des espaces et réduit les espaces.

    Seules les espaces ordinaires en suite sont réduites ; une espace
    insécable est gardée telle quelle.

    Le texte reste celui de la source : pas de normalisation Unicode ni de
    changement de casse, que le contrôle de citation fait de son côté.
    """
    texte = _ESPACES.sub(" ", _CONTROLE.sub(" ", texte))
    lignes = (ligne.strip() for ligne in texte.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lignes)).strip()
