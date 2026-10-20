"""Règles de vraisemblance du bloc alimentation des caméras (plan, §3).

Bornes larges à dessein : elles attrapent les erreurs d'unité et de virgule,
et les incohérences entre champs, pas les erreurs subtiles qui relèvent de la
relecture humaine. Chaque règle rend des couples (clé du champ, motif) ;
``checker.py`` les applique toutes.

Motifs : ``hors_bornes``, ``tension_hors_gamme``, ``tension_poe``,
``min_superieur_max``, ``plage_trop_large``, ``classe_norme_incoherentes``,
``depasse_plafond_classe``, ``norme_insuffisante``,
``typique_superieure_max``, ``poe_superieure_max``, ``port_absent``,
``repos_superieur_max``, ``courant_incoherent``,
``inferieure_consommation_citee``, ``repos_sans_max``. Les règles qui lisent
l'extrait d'un champ sont dans ``regles_extraits.py``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from catalog.extraction.cible import Valeur

Motifs = list[tuple[str, str]]

BORNES: dict[str, tuple[float, float]] = {
    "power_w": (1, 200),
    "power_w_peak": (1, 200),
    "ports.poe.power_w": (1, 90),
    # Moins de 20 mA : des ampères lus comme des milliampères.
    "ports.dc.current_standby_ma": (20, 2000),
    # Sous 100 mA en 12 V : 1,2 W, aucune caméra IP ne consomme si peu.
    "ports.dc.current_peak_ma": (100, 5000),
}
TENSIONS_NOMINALES = (12.0, 24.0, 36.0, 48.0)
TOLERANCE_TENSION = 0.25
TENSION_PLAGE_MIN = 1 / 3  # « 10–28 V DC » (Axis) : min ≥ max / 3
# Tension du PoE côté switch, si l'extrait parle de PoE. Pas sans condition :
# il existe de vraies entrées 48 V DC (Vivotek « DC 48V power input »).
TENSIONS_POE = (44.0, 57.0)
# Puissance maximale côté caméra (PD) par classe, IEEE 802.3af/at/bt.
PLAFONDS_CLASSE = {
    0: 12.95, 1: 3.84, 2: 6.49, 3: 12.95, 4: 25.5,
    5: 40.0, 6: 51.0, 7: 62.0, 8: 71.3,
}  # fmt: skip
PLAFOND_PD = 71.3  # 802.3bt Class 8 ; « max 90 W » est la capacité du PSE
ORDRE_NORMES = ("802.3af", "802.3at", "802.3bt")
CLASSES_PAR_NORME = {
    "802.3af": range(0, 4),
    "802.3at": range(0, 5),
    "802.3bt": range(1, 9),
}
# V × I rapporté à power_w_peak, qui est le maximum toutes alimentations :
# plus serré, il refuse des valeurs justes (hik-01 : PoE au-dessus du DC ;
# dahua-03 : 36 V × 2,23 A pour 45 W, gardé par le corrigé).
RAPPORT_VI = (0.5, 2.0)

_TENSIONS = ("ports.dc.voltage_min_v", "ports.dc.voltage_max_v")
_ATTRIBUTS_PORT = {
    "ports.poe": ("ports.poe.class", "ports.poe.power_w", "ports.poe.min_standard"),
    "ports.dc": (
        *_TENSIONS,
        "ports.dc.current_standby_ma",
        "ports.dc.current_peak_ma",
    ),
}
_MENTION_POE = re.compile(r"poe|power[\s-]*over[\s-]*ethernet|802\.3", re.IGNORECASE)


@dataclass(frozen=True)
class Contexte:
    """Les valeurs extraites d'une notice, leurs extraits, et le texte envoyé.

    Du texte envoyé au modèle : la plus haute classe PoE citée, les normes
    citées, s'il mentionne un PoE propriétaire (High PoE, injecteur, PoH), et
    la plus forte consommation citée quand plusieurs alimentations le sont.
    """

    valeurs: Mapping[str, Valeur]
    extraits: Mapping[str, str | None] = field(default_factory=dict)
    classe_max_citee: int | None = None
    normes_citees: frozenset[str] = field(default_factory=frozenset)
    poe_proprietaire: bool = False
    consommation_max_citee: float | None = None

    def nombre(self, cle: str) -> float | None:
        """La valeur numérique d'un champ, None si absente ou d'un autre type."""
        v = self.valeurs.get(cle)
        if isinstance(v, bool) or not isinstance(v, int | float):
            return None
        return float(v)

    def classe(self) -> int | None:
        """La classe PoE extraite, en entier."""
        v = self.valeurs.get("ports.poe.class")
        return int(v) if isinstance(v, str) and v.isdigit() else None


def _deux(a: str, b: str, motif: str) -> Motifs:
    return [(a, motif), (b, motif)]


def regle_bornes(ctx: Contexte) -> Motifs:
    """Chaque valeur numérique dans sa plage large."""
    motifs: Motifs = []
    for cle, (bas, haut) in BORNES.items():
        v = ctx.nombre(cle)
        if v is not None and not bas <= v <= haut:
            motifs.append((cle, "hors_bornes"))
    return motifs


def _proche_nominale(tension: float) -> bool:
    return any(abs(tension - n) <= n * TOLERANCE_TENSION for n in TENSIONS_NOMINALES)


def regle_tensions(ctx: Contexte) -> Motifs:
    """Tensions autour de 12, 24, 36 ou 48 V ; pas la tension du PoE ; min ≤ max."""
    motifs: Motifs = []
    for cle in _TENSIONS:
        v = ctx.nombre(cle)
        if v is None:
            continue
        if not _proche_nominale(v):
            motifs.append((cle, "tension_hors_gamme"))
        poe = _MENTION_POE.search(ctx.extraits.get(cle) or "")
        if poe and TENSIONS_POE[0] <= v <= TENSIONS_POE[1]:
            motifs.append((cle, "tension_poe"))
    bas, haut = (ctx.nombre(cle) for cle in _TENSIONS)
    if bas is not None and haut is not None:
        if bas > haut:
            motifs += _deux(*_TENSIONS, "min_superieur_max")
        elif bas < haut * TENSION_PLAGE_MIN:
            motifs += _deux(*_TENSIONS, "plage_trop_large")
    return motifs


def regle_classe(ctx: Contexte) -> Motifs:
    """Classe compatible avec la norme ; af exclut plus de 12,95 W.

    La classe est celle du pire cas, ``min_standard`` la norme la plus basse
    (GUIDE, plusieurs modes PoE) : une classe admise par une norme plus haute
    citée dans la notice passe (Q1806-LE : at, classe 6 du mode bt).
    """
    motifs: Motifs = []
    classe = ctx.classe()
    norme = ctx.valeurs.get("ports.poe.min_standard")
    admises: set[int] | None = None
    if isinstance(norme, str) and norme in CLASSES_PAR_NORME:
        rang = ORDRE_NORMES.index(norme)
        normes = {norme} | (ctx.normes_citees & set(ORDRE_NORMES[rang + 1 :]))
        admises = {c for n in normes for c in CLASSES_PAR_NORME.get(n, ())}
        # Une norme plus haute n'admet que des classes citées dans la notice :
        # « Midspan 802.3bt » ne justifie pas une classe 8 jamais écrite.
        admises &= set(CLASSES_PAR_NORME[norme]) | set(
            range((ctx.classe_max_citee or 0) + 1)
        )
    if classe is not None and admises is not None and classe not in admises:
        motifs += _deux(
            "ports.poe.class", "ports.poe.min_standard", "classe_norme_incoherentes"
        )
    puissance = ctx.nombre("ports.poe.power_w")
    superieures = ctx.normes_citees & {"802.3at", "802.3bt"}
    if (
        norme == "802.3af"
        and puissance is not None
        and puissance > PLAFONDS_CLASSE[3]
        and not superieures
        and not ctx.poe_proprietaire
    ):
        motifs += _deux(
            "ports.poe.min_standard", "ports.poe.power_w", "norme_insuffisante"
        )
    return motifs


def regle_plafond(ctx: Contexte) -> Motifs:
    """Puissance PoE sous le plafond de sa classe ; sans classe, 71,3 W.

    Classe et puissance forment une paire du pire cas (eval/GUIDE.md,
    plusieurs modes PoE) : « Class 4 » avec 51 W ferait proposer un port de
    switch trop faible. Sans classe extraite, le plafond est celui de la plus
    haute classe citée. Pas de plafond quand la notice mentionne un PoE
    propriétaire (High PoE, injecteur constructeur) : la classe est alors
    celle du mode normé, pas du pire cas.
    """
    puissance, classe = ctx.nombre("ports.poe.power_w"), ctx.classe()
    if ctx.poe_proprietaire or puissance is None:
        return []
    reference = classe if classe is not None else ctx.classe_max_citee
    plafond = PLAFONDS_CLASSE[reference] if reference is not None else PLAFOND_PD
    if puissance <= plafond:
        return []
    if classe is None:
        return [("ports.poe.power_w", "depasse_plafond_classe")]
    return _deux("ports.poe.power_w", "ports.poe.class", "depasse_plafond_classe")


def regle_puissances(ctx: Contexte) -> Motifs:
    """Typique et puissance PoE au plus égales à la maximale."""
    motifs: Motifs = []
    maxi = ctx.nombre("power_w_peak")
    if maxi is None:
        return motifs
    typique, poe = ctx.nombre("power_w"), ctx.nombre("ports.poe.power_w")
    if typique is not None and typique > maxi:
        motifs += _deux("power_w", "power_w_peak", "typique_superieure_max")
    if poe is not None and poe > maxi:
        motifs += _deux("ports.poe.power_w", "power_w_peak", "poe_superieure_max")
    return motifs


def regle_consommation_citee(ctx: Contexte) -> Motifs:
    """Maximale au moins égale à la plus forte consommation citée.

    Cause principale des erreurs de L4 : le maximum d'une seule alimentation
    (PoE) retenu quand une autre (24 V AC, DC) consomme plus. Sur une notice
    multi-références, la consommation d'une voisine peut déclencher la règle
    à tort : le champ passe en ``douteux``, une relecture tranche.
    """
    maxi, citee = ctx.nombre("power_w_peak"), ctx.consommation_max_citee
    if maxi is not None and citee is not None and maxi < citee:
        return [("power_w_peak", "inferieure_consommation_citee")]
    return []


def regle_ports(ctx: Contexte) -> Motifs:
    """Un attribut de port renseigné alors que le port n'est pas déclaré présent."""
    motifs: Motifs = []
    for port, attributs in _ATTRIBUTS_PORT.items():
        if ctx.valeurs.get(port) is True:
            continue
        orphelins = [a for a in attributs if ctx.valeurs.get(a) is not None]
        motifs += [(a, "port_absent") for a in orphelins]
        if orphelins and ctx.valeurs.get(port) is False:
            motifs.append((port, "port_absent"))
    return motifs


def regle_courants(ctx: Contexte) -> Motifs:
    """Repos ≤ maximal ; V × I cohérent avec la puissance maximale.

    Attrape la confusion A / mA. Trop large pour attraper le courant typique
    pris pour le maximal, ou le calibre de l'alimentation (voir RAPPORT_VI).
    """
    motifs: Motifs = []
    repos = ctx.nombre("ports.dc.current_standby_ma")
    pointe = ctx.nombre("ports.dc.current_peak_ma")
    if repos is not None and pointe is None:
        # Un courant unique va dans current_peak_ma (eval/GUIDE.md, Courants).
        motifs.append(("ports.dc.current_standby_ma", "repos_sans_max"))
    if repos is not None and pointe is not None and repos > pointe:
        motifs += _deux(
            "ports.dc.current_standby_ma",
            "ports.dc.current_peak_ma",
            "repos_superieur_max",
        )
    tensions = [t for t in (ctx.nombre(c) for c in _TENSIONS) if t is not None]
    maxi = ctx.nombre("power_w_peak")
    if pointe and tensions and maxi:
        rapport = sum(tensions) / len(tensions) * pointe / 1000 / maxi
        if not RAPPORT_VI[0] <= rapport <= RAPPORT_VI[1]:
            motifs.append(("ports.dc.current_peak_ma", "courant_incoherent"))
    return motifs


REGLES: tuple[Callable[[Contexte], Motifs], ...] = (
    regle_bornes,
    regle_tensions,
    regle_classe,
    regle_plafond,
    regle_puissances,
    regle_consommation_citee,
    regle_ports,
    regle_courants,
)
