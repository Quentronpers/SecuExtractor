"""Rapport d'évaluation : métriques, intervalles, détail par champ, erreurs.

Écrit ``eval/resultats/<nom>.json`` (versionné) et un résumé Markdown à
côté. Le rapport ne contient que des valeurs, des motifs et des
identifiants : aucun texte de notice (plan eval-alimentation, §2).
"""

from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from catalog.evaluation.metriques import (
    Cellule,
    bootstrap,
    compter,
    regrouper,
    taux,
    total,
)
from catalog.evaluation.notices import RACINE
from catalog.evaluation.reference import Corrige
from catalog.extraction.runner import ResultatBloc

RAPPORTS_DIR = RACINE / "eval" / "resultats"


def cellules(
    resultats: Sequence[ResultatBloc], corriges: Mapping[str, Corrige]
) -> list[Cellule]:
    """Une cellule par champ du corrigé et par résultat ; sans corrigé, ignoré."""
    trouvees = []
    for r in resultats:
        corrige = corriges.get(r.document)
        if corrige is None:
            continue
        for cle, annotee in corrige.champs.items():
            champ = r.champs.get(cle)
            trouvees.append(
                Cellule(
                    document=r.document,
                    execution=r.execution,
                    cle=cle,
                    attendu=annotee.valeur,
                    produit=champ.valeur if champ else None,
                    etat=None if r.motif_echec else (champ.etat if champ else "absent"),
                    regle=champ.regle_echouee if champ else None,
                )
            )
    return trouvees


def empreinte_corriges(corriges: Mapping[str, Corrige]) -> str:
    """SHA-256 des corrigés utilisés, sérialisés dans l'ordre des identifiants."""
    contenu = json.dumps(
        [corriges[i].model_dump(mode="json") for i in sorted(corriges)],
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def _par_execution(liste: Sequence[Cellule]) -> dict[str, dict[str, float | None]]:
    """Moyenne, minimum et maximum de chaque métrique sur les exécutions."""
    par_exec = [taux(c) for c in regrouper(liste, "execution").values()]
    resume: dict[str, dict[str, float | None]] = {}
    for nom in taux(total([])):
        valeurs = [v for t in par_exec if (v := t[nom]) is not None]
        resume[nom] = {
            "moyenne": statistics.fmean(valeurs) if valeurs else None,
            "min": min(valeurs, default=None),
            "max": max(valeurs, default=None),
        }
    return resume


def _erreurs(liste: Sequence[Cellule]) -> list[dict[str, Any]]:
    """Les cellules fausses (valeur produite ou manquée), pour l'analyse."""
    return [asdict(c) for c in liste if c.etat is not None and not compter(c).justes]


def _technique(resultats: Sequence[ResultatBloc]) -> dict[str, Any]:
    """Échecs techniques, incohérences, latence et jetons."""
    durees = [r.duree_s for r in resultats if r.duree_s is not None]
    jetons = Counter[str]()
    for r in resultats:
        jetons.update(
            {k: int(v) for k, v in r.usage.items() if isinstance(v, int | float)}
        )
    return {
        "resultats": len(resultats),
        "echecs": dict(Counter(r.motif_echec for r in resultats if r.motif_echec)),
        "incoherents": sum(len(r.incoherents) for r in resultats),
        "duree_moyenne_s": statistics.fmean(durees) if durees else None,
        "jetons": dict(jetons),
    }


def construire(
    resultats: Sequence[ResultatBloc],
    corriges: Mapping[str, Corrige],
    meta: Mapping[str, Any],
) -> dict[str, Any]:
    """Le rapport complet d'une exécution, prêt à sérialiser."""
    liste = cellules(resultats, corriges)
    utilises = {i: corriges[i] for i in {c.document for c in liste}}
    par_champ = regrouper(liste, "cle")
    par_document = regrouper(liste, "document")
    return {
        "meta": dict(meta) | {"empreinte_corriges": empreinte_corriges(utilises)},
        "notices": sorted(utilises),
        "global": taux(total(liste)),
        "intervalles": bootstrap(par_document),
        # Effectifs par notice : ce que le bootstrap apparié rééchantillonne
        # pour comparer deux rapports (``comparaison.py``).
        "par_document": {d: asdict(c) for d, c in sorted(par_document.items())},
        "effectifs": asdict(total(liste)),
        "par_execution": _par_execution(liste),
        "par_champ": {
            cle: {"taux": taux(c), "effectifs": asdict(c)}
            for cle, c in sorted(par_champ.items())
        },
        "technique": _technique(resultats),
        "erreurs": _erreurs(liste),
    }


def _pourcent(valeur: float | None) -> str:
    return "—" if valeur is None else f"{100 * valeur:.1f} %"


def _intervalle(ic: Sequence[float] | None) -> str:
    return "—" if not ic else f"[{100 * ic[0]:.1f} ; {100 * ic[1]:.1f}]"


def markdown(rapport: Mapping[str, Any]) -> str:
    """Résumé lisible : métriques globales avec IC, puis tableau par champ."""
    lignes = [
        f"# Évaluation — {rapport['meta'].get('nom', '')}",
        "",
        f"{len(rapport['notices'])} notices, "
        f"{rapport['effectifs']['cellules']} cellules.",
        "",
        "| Métrique | Valeur | IC 95 % |",
        "|---|---|---|",
    ]
    for nom, valeur in rapport["global"].items():
        ic = _intervalle(rapport["intervalles"].get(nom))
        lignes.append(f"| {nom} | {_pourcent(valeur)} | {ic} |")
    lignes += [
        "",
        "| Champ | Présents | Produits | Précision | Rappel | Invention |",
        "|---|---|---|---|---|---|",
    ]
    for cle, champ in rapport["par_champ"].items():
        n, t = champ["effectifs"], champ["taux"]
        lignes.append(
            f"| `{cle}` | {n['presents']} | {n['produits']} | "
            f"{_pourcent(t['precision'])} | {_pourcent(t['rappel'])} | "
            f"{_pourcent(t['invention'])} |"
        )
    return "\n".join(lignes) + "\n"


def ecrire(rapport: Mapping[str, Any], nom: str, dossier: Path = RAPPORTS_DIR) -> Path:
    """Écrit ``<nom>.json`` et ``<nom>.md`` ; retourne le chemin du JSON."""
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{nom}.json"
    chemin.write_text(
        json.dumps(rapport, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    chemin.with_suffix(".md").write_text(markdown(rapport), encoding="utf-8")
    return chemin
