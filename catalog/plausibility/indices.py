"""Indices lus dans le texte autour d'une puissance : consommation ou calibre.

Partagés par ``checker.py`` (plus forte consommation citée) et ``rules.py``
(puissance PoE typique retenue au lieu de la maximale). Le texte est lu entre
la valeur précédente de la ligne et la valeur examinée.
"""

from __future__ import annotations

import math
import re
import unicodedata

WATTS = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:watts?|w)(?![a-z])")
# « typ » sans « type » : « Type 3 (60 W) ».
INDICE_CONSOMMATION = re.compile(r"consum|max|typ(?!e)|approx")
# Midspan, injecteur, alimentation, classe, norme ou capacité PoE, PoE
# propriétaire, switch, sortie : la valeur est un calibre, pas une consommation.
INDICE_CALIBRE = re.compile(
    r"midspan|inject|supply|psu|adapt|transformer|class|802\.3|ethernet|switch"
    r"|output|budget|rated|recommend"
    r"|(?<![a-z])poh(?![a-z])|hi-?poe|high[\s-]*poe|hpoe|upoe"
)
INDICE_TYPIQUE = re.compile(r"typ(?!e)|basic|nominal|average|avg|moyen")
# Étiquette d'une autre alimentation que le PoE.
AUTRE_ALIMENTATION = re.compile(r"(?<![a-z])v?(?:ac|dc)(?![a-z])")


def normaliser(texte: str) -> str:
    """NFKC et minuscules, comme le reste des contrôles."""
    return unicodedata.normalize("NFKC", texte).lower()


def _lire(nombre: str) -> float:
    return float(nombre.replace(",", "."))


def _plus_haute_sur_ligne(ligne: str, valeur: float) -> bool:
    """Une puissance plus haute sur la ligne, ni calibre ni autre alimentation."""
    debut = 0
    for nombre in WATTS.finditer(ligne):
        avant = ligne[debut : nombre.start()]
        debut = nombre.end()
        if (
            _lire(nombre[1]) > valeur + 0.005
            and not INDICE_CALIBRE.search(avant)
            and not AUTRE_ALIMENTATION.search(avant)
        ):
            return True
    return False


def typique_au_lieu_du_max(valeur: float, extrait: str) -> bool:
    """La typique retenue alors que la maximale est sur la même ligne.

    Trois conditions (``expert-metier``, 2026-10-19) : l'extrait porte un
    indice de typique ; une ligne de l'extrait donne la valeur retenue et
    une puissance plus haute ; le texte qui précède celle-ci ne dit ni un
    calibre (injecteur, classe…) ni une autre alimentation (AC, DC).
    """
    texte = normaliser(extrait)
    if not INDICE_TYPIQUE.search(texte):
        return False
    return any(
        any(
            math.isclose(_lire(n[1]), valeur, abs_tol=0.005)
            for n in WATTS.finditer(ligne)
        )
        and _plus_haute_sur_ligne(ligne, valeur)
        for ligne in texte.splitlines()
    )


_COUPLE_MAX = re.compile(  # « max 24.7 W / 11.4 W » ou « Max. 24.7/11.4 W »
    r"max\.?\s*:?\s*(\d+(?:[.,]\d+)?)\s*w?\s*/\s*(\d+(?:[.,]\d+)?)\s*w(?![a-z])"
)


def typique_dans_couple_max(valeur: float, extrait: str) -> bool:
    """Une typique lue dans un couple de maximums « Max. A/B W (X on/off) ».

    Vivotek donne deux maximums (chauffage ou IR en marche / à l'arrêt), pas
    une typique (``expert-metier``, 2026-10-20). Sans indice de typique dans
    l'extrait seulement : « typ./max. : 4.8/6 W » donne bien une typique.
    """
    texte = normaliser(extrait)
    if INDICE_TYPIQUE.search(texte):
        return False
    return any(
        math.isclose(_lire(n), valeur, abs_tol=0.005)
        for couple in _COUPLE_MAX.finditer(texte)
        for n in couple.groups()
    )


def minimum_d_un_couple_max(valeur: float, extrait: str) -> bool:
    """La plus basse d'un couple de maximums retenue comme pire cas.

    « PoE max 24.7 W / 11.4 W (Heater on/off) » : 11,4 W sous-dimensionne le
    switch (``expert-metier``, 2026-10-20).
    """
    for couple in _COUPLE_MAX.finditer(normaliser(extrait)):
        a, b = (_lire(n) for n in couple.groups())
        if max(a, b) > min(a, b) + 0.005 and math.isclose(
            valeur, min(a, b), abs_tol=0.005
        ):
            return True
    return False
