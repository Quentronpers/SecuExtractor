"""Appel du modèle d'extraction, abstraction du fournisseur.

API Anthropic, traitement par lots (Message Batches, moitié prix) — voir
CLAUDE.md (section « Stack »).
"""

from __future__ import annotations


class ClientExtraction:
    """Point d'entrée unique vers le modèle, indépendant du fournisseur."""

    def extraire_bloc(self, texte: str, schema_bloc: dict) -> dict:
        """Remplit un schéma étroit (un bloc) à partir d'un texte source."""
        raise NotImplementedError
