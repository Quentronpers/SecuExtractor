"""Journal des fichiers archivés : url, date de capture, empreinte, outil.

Voir CLAUDE.md (section « Le manifeste ») pour le format d'une entrée.
"""

from __future__ import annotations


def enregistrer(fichier: str, url: str, type_document: str, outil: str) -> None:
    """Ajoute une entrée au manifeste après archivage d'un document."""
    raise NotImplementedError
