"""Réglages des fournisseurs de modèle : serveur, budget de sortie, réflexion.

Partagés par la sous-commande ``extract`` et la démo, pour qu'aucune ne
recopie l'autre. Scaleway héberge en France (mode souverain).
"""

from __future__ import annotations

# Serveur par défaut de chaque fournisseur ; les hébergés n'ont pas de modèle
# par défaut.
URLS = {
    "ollama": "http://127.0.0.1:11434/v1",
    "groq": "https://api.groq.com/openai/v1",
    "scaleway": "https://api.scaleway.ai/v1",
}
MODELE_OLLAMA = "qwen3:14b"
# La réflexion consomme le budget de sortie (``num_predict`` la compte).
# ``none`` coupe la réflexion de qwen3 sur Ollama. Avec réflexion, 8192
# jetons peuvent être courts : une troncature est comptée comme échec.
MAX_JETONS = {"none": 2048, "low": 8192, "medium": 8192}


def champ_max_jetons(fournisseur: str) -> str:
    """Champ du budget de sortie : Groq tient ``max_tokens`` pour obsolète."""
    return "max_tokens" if fournisseur == "ollama" else "max_completion_tokens"


def reflexion_admise(fournisseur: str, reflexion: str) -> bool:
    """Faux pour ``none`` chez un hébergé.

    Groq refuse ``none`` pour gpt-oss (erreur 400 à chaque notice), qui veut
    ``low``, ``medium`` ou ``high`` ; Scaleway, même modèle, est réglé pareil.
    """
    return fournisseur == "ollama" or reflexion != "none"
