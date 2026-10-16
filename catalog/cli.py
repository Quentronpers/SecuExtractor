"""Point d'entrée en ligne de commande du pipeline.

Sous-commandes : discover, acquire, extract, evaluate, recuperer, status, export.
Voir CLAUDE.md (section « Commandes ») pour l'usage détaillé.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from catalog.acquisition import discovery, recuperation
from catalog.evaluation.evaluate import ajouter_evaluate
from catalog.evaluation.execution import ajouter_extract
from catalog.evaluation.notices import NOTICES_PATH, charger_notices


def cmd_discover(args: argparse.Namespace) -> None:
    """Découverte des fabricants, catalogues et pages produit."""
    lignes = Path(args.fabricants).read_text(encoding="utf-8").splitlines()
    fabricants = [ligne.strip() for ligne in lignes if ligne.strip()]
    discovery.decouvrir(fabricants)


def cmd_acquire(args: argparse.Namespace) -> None:
    """Téléchargement et archivage des documents découverts, pour un fabricant."""
    discovery.decouvrir_fabricant(args.fabricant)


def cmd_recuperer(args: argparse.Namespace) -> None:
    """Retrouve les notices du jeu d'évaluation et vérifie leur empreinte."""
    ids = {i.strip() for i in args.ids.split(",") if i.strip()}
    statuts: Counter[str] = Counter()
    for notice in charger_notices(args.notices):
        if ids and notice.id not in ids:
            continue
        demande = recuperation.Demande(
            notice.id, notice.fabricant, notice.url, notice.format, notice.sha256
        )
        statut = recuperation.recuperer(demande, args.archiver)
        statuts[statut] += 1
        print(f"{notice.id} : {statut}", flush=True)
    print(dict(statuts))
    if statuts["modifie"]:
        print("Notices modifiées : le corrigé ne vaut plus pour elles.")


def ajouter_recuperer(subparsers: argparse._SubParsersAction) -> None:
    """Déclare la sous-commande ``recuperer`` (notices du jeu d'évaluation)."""
    sous = subparsers.add_parser(
        "recuperer", help="retélécharger les notices du jeu et vérifier l'empreinte"
    )
    sous.add_argument("--notices", type=Path, default=NOTICES_PATH)
    sous.add_argument("--ids", default="", help="identifiants séparés par des virgules")
    sous.add_argument(
        "--archiver",
        action="store_true",
        help="écrire dans data/sources/ (sinon : vérification seule)",
    )
    sous.set_defaults(func=cmd_recuperer)


def cmd_export(args: argparse.Namespace) -> None:
    """Export du catalogue avec les niveaux de fiabilité."""
    raise NotImplementedError


def cmd_status(args: argparse.Namespace) -> None:
    """État global : découvert, extrait, vérifié, échecs par étape."""
    raise NotImplementedError


_FABRICANT = ("--fabricant", "nom du fabricant à traiter")

# Sous-commande → (fonction, aide, options obligatoires (nom, aide)).
SOUS_COMMANDES: dict[
    str, tuple[Callable[[argparse.Namespace], None], str, list[tuple[str, str]]]
] = {
    "discover": (
        cmd_discover,
        "découverte à partir d'une liste de fabricants",
        [("--fabricants", "chemin vers data/fabricants.txt")],
    ),
    "acquire": (cmd_acquire, "téléchargement et archivage", [_FABRICANT]),
    "export": (
        cmd_export,
        "export du catalogue",
        [("--out", "chemin du fichier de sortie")],
    ),
    "status": (cmd_status, "état du pipeline", []),
}


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur des sous-commandes."""
    parser = argparse.ArgumentParser(prog="catalog", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for nom, (fonction, aide, options) in SOUS_COMMANDES.items():
        sous = subparsers.add_parser(nom, help=aide)
        for option, aide_option in options:
            sous.add_argument(option, required=True, help=aide_option)
        sous.set_defaults(func=fonction)
    ajouter_extract(subparsers)
    ajouter_evaluate(subparsers)
    ajouter_recuperer(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Exécute la sous-commande demandée et retourne le code de sortie."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
