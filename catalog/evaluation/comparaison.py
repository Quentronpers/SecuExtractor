"""Comparaison de deux rapports par bootstrap apparié (plan eval-alimentation, §4).

Les deux systèmes sont rééchantillonnés sur les mêmes notices à chaque
tirage : l'écart ne paie pas la variance due au choix des notices. Un écart
dont l'intervalle exclut zéro est réel à 95 % ; sinon les notices ne
suffisent pas à départager. Seules les notices communes aux deux rapports
comptent, et les rapports doivent porter les effectifs par notice
(``par_document``, écrits depuis le 2026-10-20).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from catalog.evaluation.metriques import (
    GRAINE,
    TIRAGES,
    Compte,
    bootstrap_apparie,
    taux,
)

METRIQUES = (
    "exactitude",
    "precision",
    "precision_sur",
    "rappel",
    "invention",
    "sous_estimation",
    "tri_douteux",
)


class RapportIncomplet(ValueError):
    """Un rapport sans effectifs par notice : à régénérer avec ``evaluate``."""


def charger_comptes(chemin: Path) -> dict[str, Compte]:
    """Les effectifs par notice d'un rapport ``eval/resultats/*.json``."""
    rapport = json.loads(chemin.read_text(encoding="utf-8"))
    if "par_document" not in rapport:
        raise RapportIncomplet(f"{chemin.name} : pas d'effectifs par notice")
    return {doc: Compte(**c) for doc, c in rapport["par_document"].items()}


def provenance(chemins: list[Path]) -> dict[str, Any]:
    """Rapports comparés, corrigé commun et réglages du bootstrap.

    Deux rapports faits sur des corrigés différents ne se comparent pas :
    l'écart mêlerait le modèle et le changement de corrigé.
    """
    rapports = [json.loads(c.read_text(encoding="utf-8")) for c in chemins]
    empreintes = {r["meta"].get("empreinte_corriges") for r in rapports}
    if len(empreintes) != 1:
        raise CorrigesDifferents(
            "corrigés différents : régénérer les rapports avec `evaluate`"
        )
    return {
        "a": chemins[0].name,
        "b": chemins[1].name,
        "empreinte_corriges": empreintes.pop(),
        "commits": [r["meta"].get("commit_evaluation") for r in rapports],
        "tirages": TIRAGES,
        "graine": GRAINE,
    }


class CorrigesDifferents(ValueError):
    """Les deux rapports ne reposent pas sur le même corrigé."""


def comparer(
    a: Mapping[str, Compte], b: Mapping[str, Compte]
) -> dict[str, dict[str, Any]]:
    """Par métrique : valeur de chaque système, écart a − b et son intervalle."""
    communs = sorted(set(a) & set(b))
    total_a = sum((a[d] for d in communs), Compte())
    total_b = sum((b[d] for d in communs), Compte())
    resultat = {}
    for nom in METRIQUES:
        va, vb = taux(total_a)[nom], taux(total_b)[nom]
        resultat[nom] = {
            "a": va,
            "b": vb,
            "ecart": None if va is None or vb is None else va - vb,
            "ic": bootstrap_apparie(a, b, nom),
        }
    return resultat | {"notices": {"communes": len(communs)}}


def _pts(valeur: float | None) -> str:
    return "—" if valeur is None else f"{100 * valeur:+.1f}"


def markdown(nom_a: str, nom_b: str, comparaison: Mapping[str, Any]) -> str:
    """Tableau : valeurs, écart en points, intervalle, verdict."""
    lignes = [
        f"# Comparaison — A : {nom_a} / B : {nom_b}",
        "",
        f"{comparaison['notices']['communes']} notices communes, "
        "bootstrap apparié à 95 %.",
        "",
        "| Métrique | A | B | A − B (points) | IC 95 % | Départagés |",
        "|---|---|---|---|---|---|",
    ]
    for nom in METRIQUES:
        m = comparaison[nom]
        ic = m["ic"]
        intervalle = "—" if not ic else f"[{_pts(ic[0])} ; {_pts(ic[1])}]"
        tranche = "—" if not ic else ("oui" if ic[0] > 0 or ic[1] < 0 else "non")
        a, b = ("—" if v is None else f"{100 * v:.1f} %" for v in (m["a"], m["b"]))
        lignes.append(
            f"| {nom} | {a} | {b} | {_pts(m['ecart'])} | {intervalle} | {tranche} |"
        )
    return "\n".join(lignes) + "\n"
