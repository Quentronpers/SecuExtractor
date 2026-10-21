"""Lecture et écriture des références, champs et historique en base.

Prévu, pas encore construit (docs/pipeline.md, § 5).
"""

from __future__ import annotations

import sqlite3


class Repository:
    """Accès à la base SQLite pour les commandes du CLI et l'interface de relecture."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        """Lie le dépôt à une connexion SQLite ouverte."""
        self._conn = conn

    def file_de_relecture(self) -> list[dict]:
        """Retourne les champs à relire, dans l'ordre de priorité documenté."""
        raise NotImplementedError
