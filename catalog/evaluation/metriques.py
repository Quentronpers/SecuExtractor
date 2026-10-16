"""Métriques d'évaluation : comparaison au corrigé, agrégats, bootstrap.

L'unité de comparaison est la cellule (notice, exécution, champ). Chaque
cellule donne un ``Compte`` additif ; les taux se calculent sur la somme
(plan eval-alimentation, §4) :

- une valeur est juste si elle est égale au corrigé après normalisation
  (nombres à 0,005 près, classe et norme en chaîne) ; un écart à 1 % près
  est compté à part (``proches``), jamais juste ;
- toute valeur non ``absent`` compte comme produite, quel que soit son état ;
  une valeur fausse sur un champ présent au corrigé est à la fois un faux
  positif et un faux négatif ;
- absent des deux côtés : juste, hors précision et hors rappel ;
- une notice en échec technique (troncature, JSON invalide…) ne produit
  rien : ses cellules comptent dans le rappel et l'exactitude, pas dans la
  précision.

Les intervalles de confiance rééchantillonnent les notices, pas les
cellules : les champs d'une même notice ne sont pas indépendants.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields

from catalog.extraction.cible import Valeur
from catalog.extraction.citations import CITATION_INTROUVABLE, CITATION_RECOMPOSEE
from catalog.extraction.etats import DOUTE_MODELE, Etat

# Champs dont la sous-estimation fait choisir un switch trop petit.
CHAMPS_SOUS_ESTIMATION = ("power_w_peak", "ports.poe.power_w")
TOLERANCE_EGALITE = 0.005
TOLERANCE_PROCHE = 0.01
TIRAGES = 2000
GRAINE = 20261016
_CITATIONS_SUSPECTES = (CITATION_INTROUVABLE, CITATION_RECOMPOSEE)


@dataclass(frozen=True)
class Cellule:
    """Un champ d'une notice pour une exécution : attendu, produit, état.

    ``etat`` vaut ``None`` quand la notice est en échec technique.
    """

    document: str
    execution: int
    cle: str
    attendu: Valeur
    produit: Valeur
    etat: Etat | None
    regle: str | None = None


@dataclass(frozen=True)
class Compte:
    """Effectifs additifs d'un ensemble de cellules."""

    cellules: int = 0
    justes: int = 0
    echecs: int = 0
    presents: int = 0
    absents: int = 0
    produits: int = 0
    vp: int = 0
    produits_sur: int = 0
    vp_sur: int = 0
    inventions: int = 0
    proches: int = 0
    erreurs: int = 0
    erreurs_douteux: int = 0
    erreurs_douteux_controles: int = 0
    citations_suspectes: int = 0
    puissances: int = 0
    sous_estimations: int = 0

    def __add__(self, autre: Compte) -> Compte:
        """Somme champ à champ."""
        return Compte(
            *(getattr(self, f.name) + getattr(autre, f.name) for f in fields(self))
        )


def _nombre(valeur: Valeur) -> float | None:
    """La valeur si c'est un nombre (pas un booléen), sinon ``None``."""
    if isinstance(valeur, bool) or not isinstance(valeur, int | float):
        return None
    return float(valeur)


def egales(attendu: Valeur, produit: Valeur) -> bool:
    """Égalité après normalisation : type identique, nombres à 0,005 près."""
    a, p = _nombre(attendu), _nombre(produit)
    if a is not None and p is not None:
        return math.isclose(a, p, abs_tol=TOLERANCE_EGALITE)
    return type(attendu) is type(produit) and attendu == produit


def proches(attendu: Valeur, produit: Valeur) -> bool:
    """Deux nombres différents mais à 1 % l'un de l'autre."""
    a, p = _nombre(attendu), _nombre(produit)
    if a is None or p is None or egales(a, p):
        return False
    return math.isclose(a, p, rel_tol=TOLERANCE_PROCHE)


def _sous_estimation(c: Cellule) -> dict[str, int]:
    """Valeur de puissance produite plus basse que le corrigé."""
    a, p = _nombre(c.attendu), _nombre(c.produit)
    if c.cle not in CHAMPS_SOUS_ESTIMATION or a is None or p is None:
        return {}
    return {"puissances": 1, "sous_estimations": int(p < a - TOLERANCE_EGALITE)}


def _compte_produit(c: Cellule) -> dict[str, int]:
    """Effectifs d'une cellule où une valeur a été produite."""
    present = c.attendu is not None
    juste = present and egales(c.attendu, c.produit)
    erreur = not juste
    motifs = c.regle.split("; ") if c.regle else []
    return {
        "produits": 1,
        "justes": int(juste),
        "vp": int(juste),
        "produits_sur": int(c.etat == "sur"),
        "vp_sur": int(juste and c.etat == "sur"),
        "inventions": int(not present),
        "proches": int(present and proches(c.attendu, c.produit)),
        "erreurs": int(erreur),
        "erreurs_douteux": int(erreur and c.etat == "douteux"),
        "erreurs_douteux_controles": int(
            erreur and any(m != DOUTE_MODELE for m in motifs)
        ),
        "citations_suspectes": int(any(m in _CITATIONS_SUSPECTES for m in motifs)),
    } | _sous_estimation(c)


def compter(c: Cellule) -> Compte:
    """Le compte d'une seule cellule."""
    present = c.attendu is not None
    base = {"cellules": 1, "presents": int(present), "absents": int(not present)}
    if c.etat is None:
        return Compte(**base, echecs=1)
    if c.produit is None:
        return Compte(**base, justes=int(not present))
    return Compte(**(base | _compte_produit(c)))


def _ratio(numerateur: int, denominateur: int) -> float | None:
    return numerateur / denominateur if denominateur else None


def taux(c: Compte) -> dict[str, float | None]:
    """Les métriques du plan (§4) ; ``None`` quand le dénominateur est nul."""
    return {
        "precision": _ratio(c.vp, c.produits),
        "precision_sur": _ratio(c.vp_sur, c.produits_sur),
        "rappel": _ratio(c.vp, c.presents),
        "exactitude": _ratio(c.justes, c.cellules),
        "invention": _ratio(c.inventions, c.absents),
        "sous_estimation": _ratio(c.sous_estimations, c.puissances),
        "citations_suspectes": _ratio(c.citations_suspectes, c.produits),
        "tri_douteux": _ratio(c.erreurs_douteux, c.erreurs),
        "tri_douteux_controles": _ratio(c.erreurs_douteux_controles, c.erreurs),
        "proches": _ratio(c.proches, c.produits),
        "echecs": _ratio(c.echecs, c.cellules),
    }


def total(cellules: Iterable[Cellule]) -> Compte:
    """Somme des comptes de toutes les cellules."""
    return sum((compter(c) for c in cellules), Compte())


def regrouper(cellules: Iterable[Cellule], par: str) -> dict[str, Compte]:
    """Comptes par valeur d'un attribut de cellule (``document``, ``cle``…)."""
    groupes: dict[str, Compte] = defaultdict(Compte)
    for c in cellules:
        cle = str(getattr(c, par))
        groupes[cle] = groupes[cle] + compter(c)
    return dict(groupes)


def _intervalle(valeurs: list[float]) -> tuple[float, float] | None:
    """Percentiles 2,5 et 97,5 d'un échantillon trié ou non."""
    if not valeurs:
        return None
    tries = sorted(valeurs)
    bas = tries[int(0.025 * (len(tries) - 1))]
    haut = tries[math.ceil(0.975 * (len(tries) - 1))]
    return bas, haut


def bootstrap(
    par_document: Mapping[str, Compte], tirages: int = TIRAGES, graine: int = GRAINE
) -> dict[str, tuple[float, float] | None]:
    """Intervalle à 95 % de chaque métrique, en rééchantillonnant les notices."""
    rng = random.Random(graine)
    documents = sorted(par_document)
    echantillons: dict[str, list[float]] = defaultdict(list)
    for _ in range(tirages if documents else 0):
        somme = sum((par_document[rng.choice(documents)] for _ in documents), Compte())
        for nom, valeur in taux(somme).items():
            if valeur is not None:
                echantillons[nom].append(valeur)
    return {nom: _intervalle(echantillons[nom]) for nom in taux(Compte())}


def bootstrap_apparie(
    a: Mapping[str, Compte],
    b: Mapping[str, Compte],
    metrique: str,
    tirages: int = TIRAGES,
) -> tuple[float, float] | None:
    """Intervalle à 95 % de l'écart ``a - b`` sur les notices communes.

    Les deux systèmes sont tirés sur les mêmes notices à chaque tirage :
    l'écart ne paie pas la variance due au choix des notices.
    """
    rng = random.Random(GRAINE)
    communs = sorted(set(a) & set(b))
    ecarts = []
    for _ in range(tirages if communs else 0):
        tirage = [rng.choice(communs) for _ in communs]
        ta = taux(sum((a[d] for d in tirage), Compte()))[metrique]
        tb = taux(sum((b[d] for d in tirage), Compte()))[metrique]
        if ta is not None and tb is not None:
            ecarts.append(ta - tb)
    return _intervalle(ecarts)
