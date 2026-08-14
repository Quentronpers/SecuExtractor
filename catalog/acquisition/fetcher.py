"""Récupération de pages et documents : requests d'abord, repli playwright.

Cadence, robots.txt, User-Agent identifiable et reprise sur erreur — voir
CLAUDE.md (section « Cadre à respecter »).
"""

from __future__ import annotations


def fetch(url: str) -> str:
    """Récupère le contenu d'une URL via requests, avec repli playwright.

    Bascule sur playwright quand la réponse revient vide ou manifestement
    incomplète, signe d'un contenu injecté en JavaScript.
    """
    raise NotImplementedError
