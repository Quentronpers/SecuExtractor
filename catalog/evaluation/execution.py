"""Sous-commande ``extract`` : extraction du bloc alimentation sur le jeu d'évaluation.

Lit ``eval/notices.csv``, retrouve chaque notice archivée par son empreinte,
et lance le runner. Le serveur se règle par l'environnement (``LLM_BASE_URL``,
``LLM_MODEL``, ``LLM_API_KEY`` pour Groq) ; avec Ollama, le contexte réel et
le digest du modèle sont lus dans ``/api/ps`` avant tout appel.

Les réponses brutes vont dans ``data/extractions/brut/`` et les résultats
dans ``data/extractions/resultats/<date>_<modele>_<prompt>_<reflexion>/``,
avec un ``execution.json`` qui garde les réglages. Rien de cela n'est
versionné : les réponses contiennent le texte des notices.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import date
from pathlib import Path

from catalog.evaluation.notices import (
    MANIFESTE_PATH,
    NOTICES_PATH,
    RACINE,
    charger_notices,
    chemin_source,
)
from catalog.extraction.brut import ArchiveBrute, maintenant
from catalog.extraction.cible import Cible, charger_cible
from catalog.extraction.client import ClientCompatibleOpenAI, EchecAppel
from catalog.extraction.ollama import decrire_modele, version_ollama
from catalog.extraction.prompts import (
    VERSION_PROMPT,
    ReponseBloc,
    gabarit,
    schema_sortie,
)
from catalog.extraction.runner import (
    ConfigModele,
    Document,
    Moteur,
    ResultatBloc,
    executer_lot,
)

RESULTATS_DIR = RACINE / "data" / "extractions" / "resultats"
# La réflexion consomme le budget de sortie (``num_predict`` la compte).
# ``none`` coupe la réflexion de qwen3 sur Ollama ; Groq refuse ``none`` pour
# gpt-oss, qui veut ``low``, ``medium`` ou ``high``. Avec réflexion, 8192
# jetons peuvent être courts : une troncature est comptée comme échec.
MAX_JETONS = {"none": 2048, "low": 8192, "medium": 8192}


def ajouter_extract(subparsers: argparse._SubParsersAction) -> None:
    """Déclare la sous-commande ``extract`` et ses options."""
    sous = subparsers.add_parser("extract", help="extraction sur le jeu d'évaluation")
    sous.add_argument("--notices", type=Path, default=NOTICES_PATH)
    sous.add_argument("--jeu", choices=["miseaupoint", "test"], required=True)
    sous.add_argument("--ids", default="", help="identifiants séparés par des virgules")
    sous.add_argument("--executions", type=int, default=1)
    sous.add_argument("--fournisseur", choices=["ollama", "groq"], default="ollama")
    sous.add_argument("--reflexion", choices=sorted(MAX_JETONS), default="none")
    sous.add_argument("--max-jetons", type=int, default=None)
    sous.set_defaults(func=cmd_extract)


def documents(args: argparse.Namespace) -> list[Document]:
    """Les notices du jeu demandé (ou des ids donnés), avec leur fichier archivé."""
    manifeste = json.loads(MANIFESTE_PATH.read_text(encoding="utf-8"))
    ids = {i.strip() for i in args.ids.split(",") if i.strip()}
    retenues = [
        n
        for n in charger_notices(args.notices)
        if n.jeu == args.jeu and (not ids or n.id in ids)
    ]
    inconnus = ids - {n.id for n in retenues}
    if inconnus:
        raise SystemExit(f"hors du jeu {args.jeu} : {', '.join(sorted(inconnus))}")
    trouves = []
    for notice in retenues:
        chemin = chemin_source(notice, manifeste)
        if chemin is None or not chemin.exists():
            raise SystemExit(f"{notice.id} : fichier archivé introuvable")
        trouves.append(
            Document(
                id=notice.id,
                reference=notice.reference,
                chemin=chemin,
                sha256=notice.sha256,
            )
        )
    return trouves


def configurer(
    args: argparse.Namespace, url: str, modele: str
) -> tuple[ConfigModele, dict[str, object]]:
    """Réglages du modèle et ce que dit le serveur (Ollama : ``/api/ps``)."""
    max_jetons = args.max_jetons or MAX_JETONS[args.reflexion]
    if args.fournisseur == "groq":
        return ConfigModele(modele, None, None, args.reflexion, max_jetons), {}
    try:
        charge = decrire_modele(url, modele)
        version = version_ollama(url)
    except EchecAppel as erreur:
        raise SystemExit(f"Ollama injoignable ou incomplet : {erreur}") from erreur
    if charge.part_gpu < 1.0:
        print(f"Attention : {charge.part_gpu:.0%} du modèle seulement en VRAM.")
    config = ConfigModele(
        modele, charge.contexte_jetons, charge.empreinte, args.reflexion, max_jetons
    )
    return config, {"part_gpu": charge.part_gpu, "version_ollama": version}


def _empreinte(texte: str | bytes) -> str:
    """SHA-256 hexadécimal d'un texte ou d'octets."""
    donnees = texte.encode("utf-8") if isinstance(texte, str) else texte
    return hashlib.sha256(donnees).hexdigest()


def commit_courant(racine: Path = RACINE) -> str:
    """Commit de HEAD lu dans ``.git/`` (le conteneur n'a pas git)."""
    git = racine / ".git"
    try:
        tete = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not tete.startswith("ref: "):
            return tete
        ref = tete.removeprefix("ref: ")
        if (git / ref).exists():
            return (git / ref).read_text(encoding="utf-8").strip()
        for ligne in (git / "packed-refs").read_text(encoding="utf-8").splitlines():
            if ligne.endswith(" " + ref):
                return ligne.split()[0]
    except OSError:
        pass
    return ""


def reglages(
    args: argparse.Namespace, config: ConfigModele, cible: Cible
) -> dict[str, object]:
    """Ce qui permet de rejouer et de comparer une exécution (plan, §4)."""
    prompt = gabarit(cible) + json.dumps(schema_sortie(cible), sort_keys=True)
    return {
        **vars(config),
        "fournisseur": args.fournisseur,
        "jeu": args.jeu,
        "ids": args.ids,
        "executions": args.executions,
        "version_prompt": VERSION_PROMPT,
        "empreinte_prompt": _empreinte(prompt),
        "empreinte_notices": _empreinte(Path(args.notices).read_bytes()),
        "commit": commit_courant(),
        "debut": maintenant(),
    }


def controler_fin(url: str, config: ConfigModele) -> dict[str, object]:
    """Relit ``/api/ps`` en fin de lot : un autre client a pu recharger le modèle."""
    try:
        charge = decrire_modele(url, config.modele)
    except EchecAppel as erreur:
        return {"fin_erreur": str(erreur)}
    ecart = (charge.contexte_jetons, charge.empreinte) != (
        config.contexte_jetons,
        config.empreinte_modele,
    )
    if ecart:
        print("Attention : contexte ou digest changé pendant le lot.")
    return {
        "fin_ecart": ecart,
        "fin_contexte_jetons": charge.contexte_jetons,
        "fin_empreinte_modele": charge.empreinte,
        "fin_part_gpu": charge.part_gpu,
    }


def _dossier(config: ConfigModele) -> Path:
    """Dossier des résultats : date, modèle, version du prompt, réflexion."""
    nom = re.sub(r"[^A-Za-z0-9.-]+", "-", config.modele)
    return RESULTATS_DIR / (
        f"{date.today().isoformat()}_{nom}_{VERSION_PROMPT}_{config.reasoning_effort}"
    )


def _resume(resultat: ResultatBloc) -> str:
    """Une ligne de suivi par résultat : états des champs, ou motif d'échec."""
    if resultat.motif_echec:
        return (
            f"{resultat.document} e{resultat.execution} : échec {resultat.motif_echec}"
        )
    etats = Counter(c.etat for c in resultat.champs.values())
    duree = f"{resultat.duree_s:.0f} s" if resultat.duree_s is not None else "?"
    return (
        f"{resultat.document} e{resultat.execution} : {etats['sur']} sur, "
        f"{etats['douteux']} douteux, {etats['absent']} absent ({duree})"
    )


def _ecrire_reglages(sortie: Path, infos: dict[str, object]) -> None:
    """Écrit ``execution.json`` (au départ, puis complété en fin de lot)."""
    (sortie / "execution.json").write_text(
        json.dumps(infos, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def cmd_extract(args: argparse.Namespace) -> None:
    """Extrait le bloc alimentation des notices demandées et écrit les résultats."""
    url = os.environ.get("LLM_BASE_URL", "")
    modele = os.environ.get("LLM_MODEL", "")
    if not url or not modele:
        raise SystemExit("LLM_BASE_URL et LLM_MODEL doivent être définis.")
    a_traiter = documents(args)
    config, serveur = configurer(args, url, modele)
    champ = "max_completion_tokens" if args.fournisseur == "groq" else "max_tokens"
    client = ClientCompatibleOpenAI(url, os.environ.get("LLM_API_KEY"), champ)
    moteur = Moteur(config, ArchiveBrute(), lambda r: client.executer(r, ReponseBloc))
    cible = charger_cible("camera", "alimentation")
    sortie = _dossier(config)
    sortie.mkdir(parents=True, exist_ok=True)
    infos = reglages(args, config, cible) | serveur
    _ecrire_reglages(sortie, infos)
    for resultat in executer_lot(a_traiter, cible, moteur, args.executions, sortie):
        print(_resume(resultat), flush=True)
    if args.fournisseur == "ollama":
        infos |= controler_fin(url, config)
    _ecrire_reglages(sortie, infos | {"fin": maintenant()})
    print(f"Résultats : {sortie}")
