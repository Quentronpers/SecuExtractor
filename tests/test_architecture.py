"""Garde-fous d'architecture, vérifiés à chaque exécution des tests.

Ce que CLAUDE.md énonce et qu'une machine peut contrôler est contrôlé ici :

- **frontière de l'acquisition** : le pipeline lit ``data/sources/`` sans
  jamais savoir d'où viennent les documents. Seul ``catalog.cli`` importe
  ``catalog.acquisition`` ; l'acquisition, elle, n'importe rien de l'aval ;
- **frontière de la démo** : ``demo`` fait tourner le code mesuré sans
  importer ``catalog.acquisition`` ni ``catalog.evaluation``, ni dans son
  texte, ni à l'exécution ;
- **tailles** : fichier ≤ 300 lignes, fonction ≤ 30 lignes hors docstring,
  ≤ 5 paramètres.

Les écarts existants sont gelés dans ``tests/architecture_debt.txt`` : la
liste ne peut que rétrécir (une entrée qui n'est plus en infraction fait
échouer le test, pour qu'on la retire).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "catalog"
DEMO = ROOT / "demo"
DEBT_FILE = Path(__file__).with_name("architecture_debt.txt")

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 30
MAX_PARAMETERS = 5

ACQUISITION = "catalog.acquisition"
# Modules autorisés à importer l'acquisition : le point d'entrée seul.
ACQUISITION_CLIENTS = {"catalog.cli"}
DOWNSTREAM = (
    "catalog.reading",
    "catalog.extraction",
    "catalog.plausibility",
    "catalog.storage",
    "catalog.review",
    "catalog.export",
    "catalog.evaluation",
)
# Ce que la démo ne charge jamais : elle fait tourner le code mesuré, sans
# l'acquisition ni l'évaluation.
DEMO_FORBIDDEN = (ACQUISITION, "catalog.evaluation")


def _python_files() -> Iterator[Path]:
    """Énumère les fichiers Python du paquet, de la démo et des tests."""
    for base in (PACKAGE, DEMO, ROOT / "tests"):
        yield from sorted(base.rglob("*.py"))


def _module_name(path: Path) -> str:
    """Convertit un chemin de fichier en nom de module pointé."""
    parts = path.relative_to(ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    """Retourne les modules importés par un fichier."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _is_under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _function_length(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Compte les lignes d'une fonction, docstring exclue."""
    body = node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    if not body:
        return 0
    end = node.end_lineno or node.lineno
    return end - body[0].lineno + 1


def _parameter_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Compte les paramètres, hors ``self`` et ``cls``."""
    args = node.args
    names = [a.arg for a in args.posonlyargs + args.args + args.kwonlyargs]
    return len([n for n in names if n not in ("self", "cls")])


def _violations() -> set[str]:
    """Calcule toutes les infractions de taille, au format du fichier de dette."""
    found: set[str] = set()
    for path in _python_files():
        rel = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        if len(source.splitlines()) > MAX_FILE_LINES:
            found.add(f"file {rel}")
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if _function_length(node) > MAX_FUNCTION_LINES:
                found.add(f"function {rel}::{node.name}")
            if _parameter_count(node) > MAX_PARAMETERS:
                found.add(f"params {rel}::{node.name}")
    return found


def _frozen_debt() -> set[str]:
    """Lit la dette gelée, commentaires et lignes vides ignorés."""
    lines = DEBT_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and line[0] != "#"}


@pytest.mark.parametrize(
    "path", [p for p in PACKAGE.rglob("*.py")], ids=lambda p: p.name
)
def test_only_the_cli_imports_acquisition(path: Path) -> None:
    module = _module_name(path)
    if _is_under(module, ACQUISITION) or module in ACQUISITION_CLIENTS:
        return
    offending = {m for m in _imports(path) if _is_under(m, ACQUISITION)}
    assert not offending, (
        f"{module} importe {offending} : le pipeline ne doit pas savoir d'où "
        "viennent les documents (CLAUDE.md, « Ce que l'acquisition produit »)."
    )


@pytest.mark.parametrize(
    "path", sorted((PACKAGE / "acquisition").rglob("*.py")), ids=lambda p: p.name
)
def test_acquisition_does_not_import_downstream(path: Path) -> None:
    offending = {m for m in _imports(path) if any(_is_under(m, d) for d in DOWNSTREAM)}
    assert not offending, (
        f"{_module_name(path)} importe {offending} : l'acquisition doit pouvoir "
        "casser sans emporter le reste du pipeline."
    )


@pytest.mark.parametrize("path", sorted(DEMO.rglob("*.py")), ids=lambda p: p.name)
def test_demo_does_not_import_acquisition_nor_evaluation(path: Path) -> None:
    offending = {
        m for m in _imports(path) if any(_is_under(m, f) for f in DEMO_FORBIDDEN)
    }
    assert not offending, (
        f"{_module_name(path)} importe {offending} : la démo fait tourner "
        "l'extraction, ni l'acquisition ni l'évaluation."
    )


@pytest.mark.parametrize("path", sorted(DEMO.rglob("*.py")), ids=lambda p: p.name)
def test_demo_does_not_load_acquisition_nor_evaluation(path: Path) -> None:
    """Même règle à l'exécution : un import indirect passerait l'AST."""
    script = (
        "import importlib, sys\n"
        f"importlib.import_module({_module_name(path)!r})\n"
        "print('\\n'.join(sys.modules))\n"
    )
    sortie = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    charges = {m for m in sortie if any(_is_under(m, f) for f in DEMO_FORBIDDEN)}
    assert not charges, f"importer {_module_name(path)} charge {charges}"


def test_no_new_size_violation() -> None:
    new = _violations() - _frozen_debt()
    assert not new, (
        "Nouvelles infractions de taille (fichier ≤ 300 lignes, fonction ≤ 30 "
        "lignes, ≤ 5 paramètres) : scinder plutôt que d'ajouter à la dette.\n"
        + "\n".join(sorted(new))
    )


def test_debt_only_shrinks() -> None:
    resolved = _frozen_debt() - _violations()
    assert not resolved, (
        "Entrées résolues à retirer de tests/architecture_debt.txt :\n"
        + "\n".join(sorted(resolved))
    )
