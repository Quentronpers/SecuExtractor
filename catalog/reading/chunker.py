"""Sélection des pages (ou sections) utiles à un bloc d'extraction.

On n'envoie au modèle que ce qui parle du bloc, pour tenir dans le contexte
d'un modèle local et ne pas noyer la réponse. Chaque page reçoit un score :
le nombre de motifs du bloc qu'elle contient (un motif compte une fois). Les
pages qui atteignent le seuil sont gardées dans l'ordre du document, au plus
``MAX_PAGES``, les mieux notées d'abord. Un document court est envoyé en
entier : rien à gagner à le couper, et rien ne risque d'être écarté.

Ce découpage borne tout le reste : une valeur dont la page n'est pas
sélectionnée ne peut pas être extraite. Son rappel est mesuré à
l'évaluation (plan eval-alimentation, L4).
"""

from __future__ import annotations

import re

from catalog.reading.page import Page

DOCUMENT_COURT = 6000  # caractères, tout compris
MAX_PAGES = 4
SEUIL = 2

_MOTIFS: dict[str, tuple[str, ...]] = {
    "alimentation": (
        r"power\s*(consumption|supply|input|source)|input\s*voltage",
        r"consommation|alimentation",
        r"\bpoe\b|power\s*over\s*ethernet|\bpoh\b",
        r"802\.3\s*(af|at|bt)",
        r"\bclass\s*[0-8]\b|\bclasse\s*[0-8]\b",
        r"\d\s*v\s*(dc|ac)\b|\bv?dc\s*\d|\bv?ac\s*\d|\d\s*vdc|\d\s*vac",
        r"\d\s*w\b",
        r"\d\s*m?a\b",
    ),
}


def selectionner(pages: list[Page], bloc: str) -> list[Page]:
    """Retourne les pages qui traitent du bloc, ou toutes si le document est court."""
    if bloc not in _MOTIFS:
        raise ValueError(f"bloc inconnu : {bloc} (connus : {sorted(_MOTIFS)})")
    if sum(len(p.texte) for p in pages) <= DOCUMENT_COURT:
        return list(pages)
    motifs = [re.compile(m, re.IGNORECASE) for m in _MOTIFS[bloc]]
    scores = {p.numero: sum(1 for m in motifs if m.search(p.texte)) for p in pages}
    retenues = sorted(
        (p for p in pages if scores[p.numero] >= SEUIL),
        key=lambda p: (-scores[p.numero], p.numero),
    )[:MAX_PAGES]
    return sorted(retenues, key=lambda p: p.numero)
