"""Interface Streamlit de relecture — la pièce centrale du projet.

Traite une file priorisée, jamais un lot complet. Voir CLAUDE.md (section
« L'interface de relecture ») pour l'ordre de la file et les actions
attendues : valider, corriger, marquer absent.

Lancement : streamlit run catalog/review/app.py
"""

from __future__ import annotations

import streamlit as st


def main() -> None:
    st.title("Relecture — SecurScope Catalog")
    st.info("File de relecture à brancher sur catalog.storage.repository.")


if __name__ == "__main__":
    main()
