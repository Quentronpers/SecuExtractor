"""Contrôle de citation, déterministe et sans modèle (plan eval-alimentation, §3).

Pour chaque champ rendu par le modèle (valeur, page, extrait), le code
vérifie, sur le texte exact envoyé au modèle :

1. que l'extrait se trouve dans la page citée. Sinon : ``citation_autre_page``
   s'il est sur une autre page envoyée, ``citation_recomposee`` si ses
   fragments sont dans la page mais séparés (tableau mal linéarisé recollé
   par le modèle), ``citation_introuvable`` dans les autres cas ;
2. que la valeur figure dans l'extrait (``valeur_hors_extrait``) : nombre
   délimité suivi de son unité (« 7.7 » ne valide pas « 17.7 W »), ou règle
   propre au champ pour les ports, la classe et la norme ;
3. pour ``power_w_peak``, qu'aucune valeur plus haute ne figure dans
   l'extrait (``valeur_non_maximale`` : la typique ou la borne basse retenue
   à la place de la maximale, la sous-estimation que vise la règle 3).

L'extrait est comparé sans tenir compte de la casse, des espaces (pdfplumber
colle les mots), des séparateurs de cellules ni des coupures de mot en fin de
ligne. La plausibilité est vérifiée à part (``catalog.plausibility``).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence

from catalog.extraction.cible import ChampCible, Valeur
from catalog.reading.page import Page

CITATION_ABSENTE = "citation_absente"
CITATION_INTROUVABLE = "citation_introuvable"
CITATION_AUTRE_PAGE = "citation_autre_page"
CITATION_RECOMPOSEE = "citation_recomposee"
VALEUR_HORS_EXTRAIT = "valeur_hors_extrait"
VALEUR_NON_MAXIMALE = "valeur_non_maximale"

# Champs qui retiennent la plus haute valeur citée (eval/GUIDE.md) : une
# valeur plus haute dans le même extrait trahit la typique ou la borne basse.
_MAXIMALES = ("power_w_peak",)

_TRADUCTION = str.maketrans(
    {**dict.fromkeys("‐‑‒–—―−", "-"), "­": None, "’": "'", "‘": "'"}
)
_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
_COUPURE = re.compile(r"(?<=[a-z])-\s+(?=[a-z])")
_BLANCS = re.compile(r"[\s|│]+")

# Un nombre ni précédé d'un chiffre, ni de « chiffre + séparateur » : « 7.7 »
# n'est pas lu dans « 17.7 », mais « max.5 W » donne 5.
_NOMBRE = r"(?<!\d)(?<!\d[.,])(\d+(?:[.,]\d+)?)"
# Les nombres qui précèdent une unité partagée : « 10–28 V », « 24.7/11.4 W ».
_SUITE = r"(?:\s*(?:-|~|to|à|/)\s*(?:dc\s*)?\d+(?:[.,]\d+)?)+"
_UNITES = {
    "W": r"\s*w(?:atts?)?(?![a-z])",
    "V": r"\s*v(?:\s?dc)?(?![a-z])(?!\s*ac(?![a-z]))",  # ni VA, ni VAC, ni V AC
    "mA": r"\s*ma(?![a-z])",
    "A": r"\s*a(?![a-z])",
}
# Ni « AC 24V » : une tension alternative n'est pas une entrée continue.
_PAS_AC = r"(?<!ac)(?<!ac )"
_POURCENT = r"(\d+(?:[.,]\d+)?)\s*%"
_TOLERANCE = re.compile(rf"(?:±|\+/-|\+-)\s*{_POURCENT}")
_ASYMETRIQUE = re.compile(rf"-\s*{_POURCENT}\s*(?:to|à|~|/|,)?\s*\+\s*{_POURCENT}")

_PREUVES_PORT = {
    "ports.poe": re.compile(r"poe|power[\s-]*over[\s-]*ethernet|802\.3\s*(?:af|at|bt)"),
    "ports.dc": re.compile(r"(?<![a-z])(?:v\s?)?dc(?![a-z])|d\.c\.|courant continu"),
}
_LISTE_NORMES = r"802\.3\s*(?:[a-z]{2}\s*/\s*)*"
_NORMES = {
    "802.3af": re.compile(_LISTE_NORMES + "af"),
    "802.3at": re.compile(_LISTE_NORMES + r"at|poe\+(?!\+)"),
    "802.3bt": re.compile(_LISTE_NORMES + "bt"),
}


def _texte(texte: str) -> str:
    """NFKC, minuscules, tirets unifiés, caractères de contrôle en espaces."""
    texte = unicodedata.normalize("NFKC", texte).lower().translate(_TRADUCTION)
    return _CONTROLE.sub(" ", texte)


def canonique(texte: str) -> str:
    """Forme de comparaison des extraits : sans espaces, séparateurs ni coupures."""
    return _BLANCS.sub("", _COUPURE.sub("", _texte(texte)))


def _contenu(page: Page) -> str:
    return canonique(f"{page.titre or ''}\n{page.texte}")


def _fragments(extrait: str, contenu: str) -> int | None:
    """Nombre de fragments contigus, pris au plus long, dont l'extrait est fait.

    ``None`` si un mot de l'extrait ne se trouve pas dans la page.
    """
    mots = extrait.split()
    debut, fragments = 0, 0
    while debut < len(mots):
        fin = next(
            (
                f
                for f in range(len(mots), debut, -1)
                if canonique(" ".join(mots[debut:f])) in contenu
            ),
            None,
        )
        if fin is None:
            return None
        debut, fragments = fin, fragments + 1
    return fragments


def controler_extrait(page: int, extrait: str, pages: Sequence[Page]) -> str | None:
    """Retourne le motif d'échec si l'extrait n'est pas tel quel dans la page citée."""
    cherche = canonique(extrait)
    contenus = {p.numero: _contenu(p) for p in pages}
    contenu = contenus.get(page)
    if contenu is not None and cherche in contenu:
        return None
    if any(cherche in autre for autre in contenus.values()):
        return CITATION_AUTRE_PAGE
    if contenu is not None and _fragments(extrait, contenu) is not None:
        return CITATION_RECOMPOSEE
    return CITATION_INTROUVABLE


def _lire(nombre: str) -> list[float]:
    """Virgule décimale ; « 1,500 » est lu aussi comme 1500."""
    lus = [float(nombre.replace(",", "."))]
    if re.fullmatch(r"\d+,\d{3}", nombre):
        lus.append(float(nombre.replace(",", "")))
    return lus


def _nombres(texte: str, motif: str) -> list[float]:
    return [n for m in re.finditer(motif, texte) for n in _lire(m.group(1))]


def _tolerances(texte: str) -> list[float]:
    """Bornes d'une tension nominale suivie d'une tolérance (« 12 VDC ± 25 % »).

    La tolérance doit être collée à la tension (éventuellement entre
    parenthèses) : écrite après le courant, « 36 VDC, 2.23 A ± 25% », on ne
    sait pas si elle porte sur la tension, et eval/GUIDE.md l'ignore.
    """
    bornes: list[float] = []
    for nominale in re.finditer(_PAS_AC + _NOMBRE + _UNITES["V"], texte):
        suite = texte[nominale.end() :].lstrip(" (")
        ecarts: list[tuple[float, float]] = []
        if symetrique := _TOLERANCE.match(suite):
            ecarts.append((-_lire(symetrique[1])[0], _lire(symetrique[1])[0]))
        if asymetrique := _ASYMETRIQUE.match(suite):
            ecarts.append((-_lire(asymetrique[1])[0], _lire(asymetrique[2])[0]))
        v = _lire(nominale[1])[0]
        bornes += [v * (1 + e / 100) for ecart in ecarts for e in ecart]
    return bornes


def candidats(extrait: str, unite: str) -> list[float]:
    """Les valeurs qu'un extrait permet de citer dans une unité (W, V ou mA).

    Nombre suivi de l'unité ; nombres d'une plage ou d'une liste qui partagent
    l'unité (« 10–28 V DC », « 24.7/11.4 W ») ;
    bornes d'une tension avec tolérance ; ampères convertis en milliampères.
    Jamais de conversion entre grandeurs (W → mA).
    """
    texte = _texte(extrait)
    unites = {"mA": [("mA", 1.0), ("A", 1000.0)]}.get(unite, [(unite, 1.0)])
    valeurs: list[float] = []
    for nom, facteur in unites:
        motif = _UNITES[nom]
        debut = _PAS_AC + _NOMBRE if nom == "V" else _NOMBRE
        trouves = _nombres(texte, debut + motif) + _nombres(
            texte, rf"{debut}(?={_SUITE}{motif})"
        )
        valeurs += [n * facteur for n in trouves]
    if unite == "V":
        valeurs += _tolerances(texte)
    return valeurs


def valeur_dans_extrait(champ: ChampCible, valeur: Valeur, extrait: str) -> bool:
    """Vrai si l'extrait justifie la valeur, selon le type et la clé du champ.

    Un port déclaré absent (faux) ne se prouve pas par un extrait : la section
    alimentation citée est réputée complète (eval/GUIDE.md).
    """
    texte = _texte(extrait)
    if champ.type == "booleen" and isinstance(valeur, bool):
        preuve = _PREUVES_PORT.get(champ.cle)
        return not valeur or (preuve is not None and bool(preuve.search(texte)))
    if champ.cle == "ports.poe.class" and isinstance(valeur, str):
        return bool(re.search(rf"classe?\s*{re.escape(valeur)}(?!\d)", texte))
    if champ.cle == "ports.poe.min_standard" and isinstance(valeur, str):
        norme = _NORMES.get(valeur)
        return norme is not None and bool(norme.search(texte))
    if champ.type == "nombre" and champ.unite in _UNITES:
        if isinstance(valeur, bool) or not isinstance(valeur, int | float):
            return False
        return any(
            math.isclose(valeur, c, abs_tol=0.005)
            for c in candidats(extrait, champ.unite)
        )
    return False


def verifier_citation(
    champ: ChampCible,
    valeur: Valeur,
    page: int | None,
    extrait: str | None,
    pages: Sequence[Page],
) -> str | None:
    """Motif d'échec du contrôle de citation d'un champ, ``None`` s'il passe.

    Une valeur absente (``None``) n'a rien à citer. Sans extrait ou sans page,
    la valeur est ``citation_absente`` (CLAUDE.md, règle 1).
    """
    if valeur is None:
        return None
    if page is None or not extrait or not canonique(extrait):
        return CITATION_ABSENTE
    motif = controler_extrait(page, extrait, pages)
    if motif:
        return motif
    if not valeur_dans_extrait(champ, valeur, extrait):
        return VALEUR_HORS_EXTRAIT
    if (
        champ.cle in _MAXIMALES
        and champ.unite
        and isinstance(valeur, int | float)
        and any(c > valeur + 0.005 for c in candidats(extrait, champ.unite))
    ):
        return VALEUR_NON_MAXIMALE
    return None
