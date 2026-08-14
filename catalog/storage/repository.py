"""Lecture et écriture des références, champs et historique en base."""

from __future__ import annotations

import sqlite3


class Repository:
    """Accès à la base SQLite pour les commandes du CLI et l'interface de relecture."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def file_de_relecture(self) -> list[dict]:
        """Retourne les champs à relire, dans l'ordre de priorité documenté."""
        raise NotImplementedError
