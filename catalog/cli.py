"""Point d'entrée en ligne de commande du pipeline.

Sous-commandes : discover, acquire, extract, status, export.
Voir CLAUDE.md (section « Commandes ») pour l'usage détaillé.
"""

from __future__ import annotations

import argparse
import sys


def cmd_discover(args: argparse.Namespace) -> None:
    """Découverte des fabricants, catalogues et pages produit."""
    raise NotImplementedError


def cmd_acquire(args: argparse.Namespace) -> None:
    """Téléchargement et archivage des documents découverts."""
    raise NotImplementedError


def cmd_extract(args: argparse.Namespace) -> None:
    """Extraction des champs sur les documents archivés."""
    raise NotImplementedError


def cmd_export(args: argparse.Namespace) -> None:
    """Export du catalogue avec les niveaux de fiabilité."""
    raise NotImplementedError


def cmd_status(args: argparse.Namespace) -> None:
    """État global : découvert, extrait, vérifié, échecs par étape."""
    raise NotImplementedError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="catalog", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="découverte à partir d'une liste de fabricants")
    discover.add_argument("--fabricants", required=True, help="chemin vers data/fabricants.txt")
    discover.set_defaults(func=cmd_discover)

    acquire = subparsers.add_parser("acquire", help="téléchargement et archivage")
    acquire.add_argument("--fabricant", required=True, help="nom du fabricant à traiter")
    acquire.set_defaults(func=cmd_acquire)

    extract = subparsers.add_parser("extract", help="extraction sur ce qui est archivé")
    extract.add_argument("--fabricant", required=True, help="nom du fabricant à traiter")
    extract.set_defaults(func=cmd_extract)

    export = subparsers.add_parser("export", help="export du catalogue")
    export.add_argument("--out", required=True, help="chemin du fichier de sortie")
    export.set_defaults(func=cmd_export)

    status = subparsers.add_parser("status", help="état du pipeline")
    status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
