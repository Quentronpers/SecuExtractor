"""Règles qui lisent l'extrait cité pour un champ (L5, avis ``expert-metier``).

Les règles de ``rules.py`` comparent des valeurs entre elles ; celles-ci
confrontent une valeur à son propre extrait, pour les erreurs qu'un modèle
fait en citant juste : la typique retenue au lieu de la maximale, un port
déclaré absent alors que son extrait le décrit.

Motifs : ``poe_non_maximale``, ``typique_dans_couple_max``,
``minimum_d_un_couple_max``, ``port_faux_marqueur``.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from catalog.plausibility.indices import (
    minimum_d_un_couple_max,
    normaliser,
    typique_au_lieu_du_max,
    typique_dans_couple_max,
)
from catalog.plausibility.rules import TENSIONS_POE, Contexte, Motifs

_NOMBRE = r"(\d+(?:[.,]\d+)?)"
# Tension continue chiffrée : « 36 VDC », « 12 V DC », « DC12V ».
_TENSION_DC = re.compile(
    rf"{_NOMBRE}\s*v\s?dc(?![a-z])|(?<![a-z])dc\s*{_NOMBRE}\s*v(?![a-z])"
)
# Sortie pour accessoires, écrite après (« 12VDC output ») ou avant
# (« Power output: DC12V ») la tension, sur 20 caractères.
_SORTIE_APRES = re.compile(r"\A[^\n]{0,20}(?:output|aux)")
_SORTIE_AVANT = re.compile(r"(?:output|aux|i/o|max\. load)[^\n]{0,20}\Z")
_NEGATION_POE = re.compile(
    r"non-?poe|no poe|without poe|sans poe|poe\s*:?\s*(?:n/a|no\b|-)"
)
_MARQUEUR_POE = re.compile(r"poe|802\.3|power[\s-]*over[\s-]*ethernet")


def regle_poe_typique(ctx: Contexte) -> Motifs:
    """Puissance PoE : la typique retenue alors que la maximale est citée.

    Erreurs de Groq en L5 (hanwha-07 : 30 W pour « Max. 60W, typical : 30W » ;
    bosch-01). Sous-estimer la puissance PoE fait choisir un switch trop petit.
    """
    poe = ctx.nombre("ports.poe.power_w")
    extrait = ctx.extraits.get("ports.poe.power_w")
    if poe is not None and extrait and typique_au_lieu_du_max(poe, extrait):
        return [("ports.poe.power_w", "poe_non_maximale")]
    return []


def regle_typique_couple(ctx: Contexte) -> Motifs:
    """Typique lue dans un couple de maximums « Max. A/B W (X on/off) »."""
    typique, extrait = ctx.nombre("power_w"), ctx.extraits.get("power_w")
    if typique is not None and extrait and typique_dans_couple_max(typique, extrait):
        return [("power_w", "typique_dans_couple_max")]
    return []


def regle_poe_couple(ctx: Contexte) -> Motifs:
    """Puissance PoE : la plus basse d'un couple « Max. A/B W » retenue."""
    poe = ctx.nombre("ports.poe.power_w")
    extrait = ctx.extraits.get("ports.poe.power_w")
    if poe is not None and extrait and minimum_d_un_couple_max(poe, extrait):
        return [("ports.poe.power_w", "minimum_d_un_couple_max")]
    return []


def entree_continue_citee(extrait: str) -> bool:
    """Une tension continue chiffrée qui n'est ni celle du PoE ni une sortie.

    « 48 VDC nominal » sous « Power-over-Ethernet » (Bosch) est la tension du
    PoE (44–57 V) ; « 12VDC output » (Hanwha) alimente des accessoires.
    """
    texte = normaliser(extrait)
    for tension in _TENSION_DC.finditer(texte):
        volts = float((tension[1] or tension[2]).replace(",", "."))
        poe = TENSIONS_POE[0] <= volts <= TENSIONS_POE[1]
        sortie = _SORTIE_APRES.match(texte[tension.end() :]) or _SORTIE_AVANT.search(
            texte[: tension.start()]
        )
        if not poe and not sortie:
            return True
    return False


def regle_port_faux(ctx: Contexte) -> Motifs:
    """Un port déclaré absent alors que son propre extrait le décrit.

    dahua-03 (Groq, test) : « 36 VDC, 2.23 A ± 25% » cité pour un DC absent.
    """
    motifs: Motifs = []
    dc = ctx.extraits.get("ports.dc") or ""
    poe = normaliser(ctx.extraits.get("ports.poe") or "")
    if ctx.valeurs.get("ports.dc") is False and entree_continue_citee(dc):
        motifs.append(("ports.dc", "port_faux_marqueur"))
    nie = _NEGATION_POE.search(poe)
    if ctx.valeurs.get("ports.poe") is False and _MARQUEUR_POE.search(poe) and not nie:
        motifs.append(("ports.poe", "port_faux_marqueur"))
    return motifs


REGLES_EXTRAITS: tuple[Callable[[Contexte], Motifs], ...] = (
    regle_poe_typique,
    regle_typique_couple,
    regle_poe_couple,
    regle_port_faux,
)
