"""Sous-commande ``evaluate`` : métriques contre le corrigé, sans modèle.

Trois usages, au choix :

- ``--run <dossier>`` : une exécution de ``extract``, rejouée depuis les
  réponses brutes avec les contrôles du code courant (``rejeu.py``) ;
- ``--comparer A B`` : deux rapports, par bootstrap apparié ;
- ``--ligne-de-base`` : la ligne de base par expressions régulières sur les
  notices du jeu, avec le rappel du découpage (lit ``data/sources/``).

Le rapport va dans ``eval/resultats/<nom>.json`` et ``.md`` (``rapport.py``).
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from catalog.evaluation import comparaison, decoupage, ligne_de_base, rapport
from catalog.evaluation.execution import commit_courant, documents, suffixe_ids
from catalog.evaluation.notices import NOTICES_PATH
from catalog.evaluation.reference import REFERENCE_DIR, Corrige, charger_corriges
from catalog.evaluation.rejeu import charger_resultats, rejouer
from catalog.extraction.brut import ArchiveBrute, maintenant
from catalog.extraction.cible import Cible, charger_cible
from catalog.extraction.etats import etats_champs
from catalog.extraction.runner import Document, ResultatBloc, lire_document
from catalog.reading.chunker import selectionner

VERSION_LIGNE_DE_BASE = "ligne-de-base-v1"


def ajouter_evaluate(subparsers: argparse._SubParsersAction) -> None:
    """Déclare la sous-commande ``evaluate`` et ses options."""
    sous = subparsers.add_parser("evaluate", help="métriques contre le corrigé")
    source = sous.add_mutually_exclusive_group(required=True)
    source.add_argument("--run", type=Path, help="dossier de résultats d'extract")
    source.add_argument("--ligne-de-base", action="store_true")
    source.add_argument(
        "--comparer", nargs=2, type=Path, metavar=("A", "B"), help="deux rapports"
    )
    sous.add_argument("--notices", type=Path, default=NOTICES_PATH)
    sous.add_argument("--jeu", choices=["miseaupoint", "test"], default="miseaupoint")
    sous.add_argument("--ids", default="", help="identifiants séparés par des virgules")
    sous.add_argument("--sortie", type=Path, default=rapport.RAPPORTS_DIR)
    sous.set_defaults(func=cmd_evaluate)


def evaluer_run(
    dossier: Path, cible: Cible, archive: ArchiveBrute
) -> tuple[list[ResultatBloc], dict[str, Any]]:
    """Résultats rejoués d'une exécution et ses réglages (``execution.json``)."""
    reglages = dossier / "execution.json"
    meta = json.loads(reglages.read_text(encoding="utf-8")) if reglages.exists() else {}
    resultats = [rejouer(r, archive, cible) for r in charger_resultats(dossier)]
    return resultats, meta | {"nom": dossier.name, "source": "rejeu"}


def evaluer_ligne_de_base(
    docs: Sequence[Document], cible: Cible, corriges: dict[str, Corrige]
) -> tuple[list[ResultatBloc], dict[str, dict[str, decoupage.Place]]]:
    """Résultats de la ligne de base et place des valeurs du corrigé, par notice."""
    resultats, places = [], {}
    for doc in docs:
        pages = lire_document(doc.chemin)
        retenues = selectionner(pages, cible.bloc)
        reponse = ligne_de_base.extraire(retenues)
        resultats.append(
            ResultatBloc(
                document=doc.id,
                reference=doc.reference,
                sha256=doc.sha256,
                execution=0,
                modele="regex",
                version_prompt=VERSION_LIGNE_DE_BASE,
                pages=[p.numero for p in retenues],
                champs=etats_champs(reponse, cible, retenues),
            )
        )
        if doc.id in corriges:
            places[doc.id] = decoupage.places(corriges[doc.id], pages, cible.bloc)
    return resultats, places


def _rapport_ligne_de_base(
    args: argparse.Namespace, cible: Cible, corriges: dict[str, Corrige]
) -> tuple[dict[str, Any], str]:
    """Rapport de la ligne de base, avec le rappel du découpage."""
    resultats, places = evaluer_ligne_de_base(documents(args), cible, corriges)
    nom = (
        f"{date.today().isoformat()}_{VERSION_LIGNE_DE_BASE}_{args.jeu}"
        f"{suffixe_ids(args.ids)}"
    )
    meta = {
        "nom": nom,
        "source": VERSION_LIGNE_DE_BASE,
        "jeu": args.jeu,
        "ids": args.ids,
        "commit": commit_courant(),
        "date": maintenant(),
    }
    construit = rapport.construire(resultats, corriges, meta)
    return construit | {"decoupage": decoupage.resumer(places)}, nom


def _comparer(chemins: list[Path], sortie: Path) -> None:
    """Compare deux rapports, affiche le tableau et l'écrit à côté."""
    a, b = (comparaison.charger_comptes(c) for c in chemins)
    resultat = comparaison.comparer(a, b)
    texte = comparaison.markdown(chemins[0].stem, chemins[1].stem, resultat)
    nom = f"comparaison_{chemins[0].stem}__{chemins[1].stem}"
    sortie.mkdir(parents=True, exist_ok=True)
    (sortie / f"{nom}.json").write_text(
        json.dumps(resultat, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (sortie / f"{nom}.md").write_text(texte, encoding="utf-8")
    print(texte)


def cmd_evaluate(args: argparse.Namespace) -> None:
    """Calcule et écrit le rapport, puis affiche les métriques globales."""
    if args.comparer:
        _comparer(args.comparer, args.sortie)
        return
    cible = charger_cible("camera", "alimentation")
    corriges = charger_corriges(REFERENCE_DIR, cible)
    if args.run:
        resultats, meta = evaluer_run(args.run, cible, ArchiveBrute())
        construit, nom = rapport.construire(resultats, corriges, meta), args.run.name
    else:
        construit, nom = _rapport_ligne_de_base(args, cible, corriges)
    chemin = rapport.ecrire(construit, nom, args.sortie)
    print(rapport.markdown(construit))
    if "decoupage" in construit:
        print(f"Découpage : {json.dumps(construit['decoupage'], ensure_ascii=False)}")
    print(f"Rapport : {chemin}")
