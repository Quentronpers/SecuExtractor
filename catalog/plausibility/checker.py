"""Application des règles de plausibilité aux valeurs extraites d'une notice.

Rend, pour chaque champ en échec, ses motifs (``regle_echouee``) ; un champ
en échec passe en ``douteux``. Les règles sont dans ``rules.py`` ; ce module
leur fournit ce que dit le texte envoyé au modèle (classes, normes, PoE
propriétaire, plus forte consommation citée).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence

from catalog.extraction.cible import Valeur
from catalog.plausibility.indices import (
    INDICE_CALIBRE,
    INDICE_CONSOMMATION,
    WATTS,
)
from catalog.plausibility.rules import REGLES, Contexte
from catalog.reading.page import Page

_CLASSE = re.compile(r"classe?\s*([0-8])(?!\d)")
_NORMES = {
    "802.3af": re.compile(r"802\.3\s*(?:[a-z]{2}\s*/\s*)*af"),
    "802.3at": re.compile(r"802\.3\s*(?:[a-z]{2}\s*/\s*)*at|poe\+(?!\+)"),
    "802.3bt": re.compile(r"802\.3\s*(?:[a-z]{2}\s*/\s*)*bt|poe\+\+"),
}
_POE_PROPRIETAIRE = re.compile(
    r"high[\s-]*(?:poe|power[\s-]*over[\s-]*ethernet)"
    r"|hi-?poe|hpoe|poe\s*inject|inject\w*\s*poe|(?<![a-z])poh(?![a-z])|hdbaset"
)

# Alimentations citées : PoE, courant continu, 24 V AC.
_ALIMENTATIONS = (
    re.compile(r"poe|802\.3|power[\s-]*over[\s-]*ethernet"),
    re.compile(r"(?<![a-z])v?dc(?![a-z])"),
    re.compile(r"(?<![a-z])v?ac(?![a-z])"),
)


def _texte(pages: Sequence[Page]) -> str:
    return unicodedata.normalize("NFKC", "\n".join(p.texte for p in pages)).lower()


def plus_haute_classe(pages: Sequence[Page]) -> int | None:
    """La plus haute classe PoE citée dans le texte envoyé au modèle."""
    return max((int(c) for c in _CLASSE.findall(_texte(pages))), default=None)


def normes_citees(pages: Sequence[Page]) -> frozenset[str]:
    """Les normes PoE citées dans le texte envoyé au modèle."""
    texte = _texte(pages)
    return frozenset(nom for nom, motif in _NORMES.items() if motif.search(texte))


def mentionne_poe_proprietaire(pages: Sequence[Page]) -> bool:
    """Vrai si le texte parle d'un PoE hors norme (High PoE, injecteur…)."""
    return bool(_POE_PROPRIETAIRE.search(_texte(pages)))


def consommations_citees(pages: Sequence[Page]) -> list[float]:
    """Les puissances en watts que le texte présente comme des consommations."""
    trouvees = []
    for ligne in _texte(pages).splitlines():
        debut, retenue = 0, False
        for nombre in WATTS.finditer(ligne):
            avant = ligne[debut : nombre.start()]
            debut = nombre.end()
            if INDICE_CALIBRE.search(avant):
                retenue = False
            elif INDICE_CONSOMMATION.search(avant):
                retenue = True
            if retenue:
                trouvees.append(float(nombre[1].replace(",", ".")))
    return trouvees


def consommation_max_citee(pages: Sequence[Page]) -> float | None:
    """La plus forte consommation citée, si plusieurs alimentations le sont."""
    texte = _texte(pages)
    if sum(bool(motif.search(texte)) for motif in _ALIMENTATIONS) < 2:
        return None
    return max(consommations_citees(pages), default=None)


def verifier_plausibilite(
    valeurs: Mapping[str, Valeur],
    extraits: Mapping[str, str | None],
    pages: Sequence[Page],
) -> dict[str, str]:
    """Motifs d'échec par clé de champ, séparés par « ; ». Vide si tout passe."""
    contexte = Contexte(
        valeurs,
        extraits,
        plus_haute_classe(pages),
        normes_citees(pages),
        mentionne_poe_proprietaire(pages),
        consommation_max_citee(pages),
    )
    motifs: dict[str, list[str]] = {}
    for regle in REGLES:
        for cle, motif in regle(contexte):
            deja = motifs.setdefault(cle, [])
            if motif not in deja:
                deja.append(motif)
    return {cle: "; ".join(liste) for cle, liste in motifs.items()}
