"""Connexion et schéma SQLite : references, champs, historique.

Prévu, pas encore construit. Voir docs/pipeline.md (§ 5, « Le stockage »)
pour le détail des trois tables.
Un seul fichier, aucun serveur — data/catalog.db, non versionné.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS references_ (
    id INTEGER PRIMARY KEY,
    fabricant TEXT NOT NULL,
    reference TEXT NOT NULL,
    type_equipement TEXT NOT NULL,
    fichier_source TEXT,
    date_extraction TEXT,
    statut TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS champs (
    id INTEGER PRIMARY KEY,
    reference_id INTEGER NOT NULL REFERENCES references_(id),
    nom_champ TEXT NOT NULL,
    valeur TEXT,
    unite TEXT,
    etat TEXT NOT NULL,
    niveau TEXT NOT NULL,
    source_page INTEGER,
    source_extrait TEXT,
    regle_echouee TEXT,
    usage TEXT
);

CREATE TABLE IF NOT EXISTS historique (
    id INTEGER PRIMARY KEY,
    champ_id INTEGER NOT NULL REFERENCES champs(id),
    ancienne_valeur TEXT,
    nouvelle_valeur TEXT,
    action TEXT NOT NULL,
    date TEXT NOT NULL
);
"""


def connexion(chemin_db: Path) -> sqlite3.Connection:
    """Ouvre la connexion SQLite et crée le schéma s'il n'existe pas encore."""
    conn = sqlite3.connect(chemin_db)
    conn.executescript(SCHEMA)
    return conn
