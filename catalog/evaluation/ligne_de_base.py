"""Ligne de base sans LLM : expressions régulières sur les pages sélectionnées.

C'est le point de comparaison qui justifie le modèle (plan eval-alimentation,
L4). Elle lit ligne par ligne les pages retenues par le découpage et rend un
``ReponseBloc`` comme le ferait le modèle, avec la ligne pour extrait : la
réponse passe ensuite par les mêmes contrôles (citation, plausibilité) et les
mêmes métriques. Les nombres sont lus par ``citations.candidats``.

Règles volontairement simples :

- PoE présent si une ligne parle de PoE ou de 802.3af/at/bt ; DC présent si
  une ligne donne une tension continue hors PoE. Un port non trouvé est
  ``faux`` si l'autre l'est, sinon absent ;
- ``power_w_peak`` : la plus haute puissance des lignes de consommation ;
  ``power_w`` : la puissance qui suit « typ » ;
- classe et norme PoE (la plus basse citée) sur les lignes PoE ;
  ``ports.poe.power_w`` : la plus haute puissance d'une ligne PoE ;
- tensions mini et maxi, courant maxi : sur les lignes de tension continue.
  Le courant au repos n'est jamais lu.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from catalog.extraction.citations import candidats
from catalog.extraction.prompts import CONSIGNES, ChampRendu, ReponseBloc
from catalog.reading.page import Page

Ligne = tuple[int, str]

_POE = re.compile(r"\bpoe\b|power[\s-]*over[\s-]*ethernet|802\.3\s*(af|at|bt)", re.I)
_DC = re.compile(r"\d\s*v\s*dc|\bv?dc\s*\d|\d\s*vdc", re.I)
_CONSO = re.compile(r"consum|power|\btyp|\bmax", re.I)
_TYPIQUE = re.compile(r"typ", re.I)
_CLASSE = re.compile(r"\bclass\s*([0-8])\b", re.I)
_NORME = re.compile(r"802\.3\s*(af|at|bt)", re.I)
VIDE = ChampRendu(extrait=None, page=None, valeur=None, doute=False)


def lignes(pages: Sequence[Page]) -> list[Ligne]:
    """Les lignes non vides des pages, avec leur numéro de page."""
    return [
        (p.numero, texte.strip())
        for p in pages
        for texte in p.texte.split("\n")
        if texte.strip()
    ]


def _rendu(valeur: bool | float | str, ligne: Ligne) -> ChampRendu:
    return ChampRendu(extrait=ligne[1], page=ligne[0], valeur=valeur, doute=False)


def _extreme(choix: Sequence[Ligne], unite: str, haut: bool = True) -> ChampRendu:
    """La plus haute (ou basse) valeur de l'unité dans ces lignes."""
    trouves = [(v, ligne) for ligne in choix for v in candidats(ligne[1], unite)]
    if not trouves:
        return VIDE
    valeur, ligne = (max if haut else min)(trouves, key=lambda t: t[0])
    return _rendu(valeur, ligne)


def _ports(poe: Sequence[Ligne], dc: Sequence[Ligne]) -> dict[str, ChampRendu]:
    """Présence des ports ; « faux » seulement si l'autre port est trouvé."""
    rendus = {}
    for cle, trouvees, autres in (("ports.poe", poe, dc), ("ports.dc", dc, poe)):
        if trouvees:
            rendus[cle] = _rendu(True, trouvees[0])
        elif autres:
            rendus[cle] = _rendu(False, autres[0])
    return rendus


def _typique(conso: Sequence[Ligne]) -> ChampRendu:
    """La première puissance écrite après « typ »."""
    for ligne in conso:
        debut = _TYPIQUE.search(ligne[1])
        valeurs = candidats(ligne[1][debut.end() :], "W") if debut else []
        if valeurs:
            return _rendu(valeurs[0], ligne)
    return VIDE


def _classe_et_norme(poe: Sequence[Ligne]) -> dict[str, ChampRendu]:
    """Première classe citée et norme la plus basse des lignes PoE."""
    rendus = {}
    for ligne in poe:
        if classe := _CLASSE.search(ligne[1]):
            rendus["ports.poe.class"] = _rendu(classe[1], ligne)
            break
    normes = sorted(
        (m[1].lower(), ligne) for ligne in poe for m in _NORME.finditer(ligne[1])
    )
    if normes:
        rendus["ports.poe.min_standard"] = _rendu(f"802.3{normes[0][0]}", normes[0][1])
    return rendus


def extraire(pages: Sequence[Page]) -> ReponseBloc:
    """La réponse de la ligne de base pour les pages d'un document."""
    toutes = lignes(pages)
    poe = [ligne for ligne in toutes if _POE.search(ligne[1])]
    dc = [ligne for ligne in toutes if _DC.search(ligne[1]) and ligne not in poe]
    conso = [ligne for ligne in toutes if _CONSO.search(ligne[1])]
    rendus = {
        "power_w_peak": _extreme(conso, "W"),
        "power_w": _typique(conso),
        "ports.poe.power_w": _extreme(poe, "W"),
        "ports.dc.voltage_min_v": _extreme(dc, "V", haut=False),
        "ports.dc.voltage_max_v": _extreme(dc, "V"),
        "ports.dc.current_peak_ma": _extreme(dc, "mA"),
    }
    rendus |= _ports(poe, dc) | _classe_et_norme(poe)
    return ReponseBloc({cle: rendus.get(cle, VIDE) for cle in CONSIGNES})
