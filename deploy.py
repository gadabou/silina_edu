#!/usr/bin/env python3
"""Déploiement du module SILINA-EDU dans une instance Odoo dockerisée.

Une seule commande fait tout : contrôles → copie dans les addons →
installation ou mise à jour automatique → redémarrage → vérification.

    python3 deploy.py                    # déploie sur la base par défaut (silina_edu)
    python3 deploy.py -d autre_base      # cible une autre base
    python3 deploy.py -u                 # force la mise à jour
    python3 deploy.py -i                 # force l'installation
    python3 deploy.py -n                 # simulation (n'exécute rien)
    python3 deploy.py --no-backup        # saute la sauvegarde préalable
    python3 deploy.py -h                 # aide
"""
from __future__ import annotations

import argparse
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration (surchargeable par variables d'environnement)
# --------------------------------------------------------------------------- #
MODULE_NAME = os.environ.get("MODULE_NAME", "silina_edu")
MODULE_SRC = Path(os.environ.get("MODULE_SRC", Path(__file__).resolve().parent))
INSTANCE_DIR = Path(os.environ.get(
    "INSTANCE_DIR", "/home/doctorpy/Projects/perso/odoo_apps/odoo1"))
ODOO_SERVICE = os.environ.get("ODOO_SERVICE", "odoo")
ODOO_CONTAINER = os.environ.get("ODOO_CONTAINER", "odoo1_app")
DB_CONTAINER = os.environ.get("DB_CONTAINER", "odoo1_db")
DB_USER = os.environ.get("DB_USER", "odoo")
DEFAULT_DB = os.environ.get("DB_NAME", "silina_edu")
ODOO_CONF = os.environ.get("ODOO_CONF", "/etc/odoo/odoo.conf")

# Exclusions lors de la copie du code source vers /mnt/extra-addons.
EXCLUDE = {
    ".git", ".idea", ".vscode", "__pycache__", "backups", "logs",
    "deploy.sh", "deploy.py", ".dockerignore", ".gitignore",
}
EXCLUDE_SUFFIX = {".pyc", ".pyo", ".backup", ".log", ".swp"}

# --------------------------------------------------------------------------- #
# Affichage
# --------------------------------------------------------------------------- #
_TTY = sys.stdout.isatty()
def _c(code: str) -> str:
    return code if _TTY else ""
OK, WARN, ERR, DIM, OFF = (
    _c("\033[32m"), _c("\033[33m"), _c("\033[31m"), _c("\033[2m"), _c("\033[0m"))

def step(msg: str) -> None:
    print(f"\n{OK}==>{OFF} {msg}")
def info(msg: str) -> None:
    print(f"    {msg}")
def warn(msg: str) -> None:
    print(f"{WARN}[!]{OFF} {msg}", file=sys.stderr)
def die(msg: str) -> "None":
    print(f"{ERR}[x]{OFF} {msg}", file=sys.stderr)
    sys.exit(1)


class Runner:
    """Encapsule l'appel à docker, avec support du mode simulation."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.sudo = not self._docker_ok()

    @staticmethod
    def _docker_ok() -> bool:
        try:
            subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, check=True)
            return True
        except Exception:
            return False

    def _base(self) -> list[str]:
        return (["sudo", "docker"] if self.sudo else ["docker"])

    def docker(self, args: list[str], *, capture=False, check=True,
               show=True) -> subprocess.CompletedProcess:
        cmd = self._base() + args
        if self.dry_run and not capture:
            print(f"{DIM}    [dry-run] {' '.join(cmd)}{OFF}")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.run(
            cmd, check=check,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.STDOUT if capture else None,
            text=True)

    def container_running(self, name: str) -> bool:
        r = self.docker(["inspect", "-f", "{{.State.Running}}", name],
                        capture=True, check=False)
        return r.stdout.strip() == "true"

    def psql(self, db: str, sql: str) -> str:
        r = self.docker(["exec", DB_CONTAINER, "psql", "-U", DB_USER,
                         "-d", db, "-tAc", sql], capture=True, check=False)
        return r.stdout.strip()

    def exec_in(self, args: list[str], *, capture=False, check=True):
        return self.docker(["exec", ODOO_CONTAINER] + args,
                           capture=capture, check=check)


# --------------------------------------------------------------------------- #
# 1. Contrôles statiques du module
# --------------------------------------------------------------------------- #
def read_manifest() -> dict:
    return ast.literal_eval((MODULE_SRC / "__manifest__.py").read_text("utf-8"))


def static_checks(manifest: dict) -> None:
    errors: list[str] = []

    for py in MODULE_SRC.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            compile(py.read_text("utf-8"), str(py), "exec")
        except SyntaxError as exc:
            errors.append(f"Python  : {py.relative_to(MODULE_SRC)}:{exc.lineno} — {exc.msg}")

    declared = list(manifest.get("data", [])) + list(manifest.get("demo", []))
    for rel in declared:
        path = MODULE_SRC / rel
        if not path.exists():
            errors.append(f"Manquant: {rel} (déclaré dans __manifest__.py)")
        elif path.suffix == ".xml":
            try:
                ET.parse(path)
            except ET.ParseError as exc:
                errors.append(f"XML     : {rel} — {exc}")

    for group in manifest.get("assets", {}).values():
        for asset in group:
            rel = asset.split("/", 1)[1] if asset.startswith(MODULE_NAME + "/") else asset
            if not (MODULE_SRC / rel).exists():
                errors.append(f"Manquant: asset {asset}")

    n_py = sum(1 for p in MODULE_SRC.rglob("*.py") if "__pycache__" not in p.parts)
    info(f"Version du module : {manifest.get('version')}")
    info(f"Dépendances       : {', '.join(manifest.get('depends', []))}")
    info(f"{len(declared)} fichier(s) de données déclaré(s), {n_py} fichier(s) Python.")
    for e in errors:
        print(f"    {ERR}{e}{OFF}")
    if errors:
        die("Le module ne passe pas les contrôles statiques.")


def check_version(run: Runner, manifest: dict, force: bool) -> None:
    module_series = str(manifest.get("version", "0")).split(".")[0]
    r = run.exec_in(["odoo", "--version"], capture=True, check=False)
    server_series = ""
    for tok in r.stdout.replace("\n", " ").split():
        if tok[:1].isdigit() and "." in tok:
            server_series = tok.split(".")[0]
            break
    info(f"Série module : {module_series} — Série serveur : {server_series or 'inconnue'}")
    if server_series and module_series != server_series:
        warn(f"Le module cible Odoo {module_series} mais le serveur exécute Odoo {server_series}.")
        warn("Odoo <18 ne reconnaît pas les vues <list> ; l'installation échouera probablement.")
        if not force:
            die("Arrêt sur incompatibilité de version (utilise --force-version pour passer outre).")
        warn("--force-version : on continue malgré tout.")


# --------------------------------------------------------------------------- #
# 2. Sauvegarde
# --------------------------------------------------------------------------- #
def backup(run: Runner, db: str) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = INSTANCE_DIR / "backups"
    dump = backup_dir / f"{db}-{stamp}.dump"
    fs = backup_dir / f"{db}-{stamp}-filestore.tar.gz"
    if run.dry_run:
        info(f"[dry-run] pg_dump + filestore vers {backup_dir}/{db}-{stamp}.*")
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    with dump.open("wb") as fh:
        subprocess.run(run._base() + ["exec", DB_CONTAINER, "pg_dump", "-U",
                       DB_USER, "-Fc", db], stdout=fh, check=True)
    try:
        with fs.open("wb") as fh:
            p1 = subprocess.Popen(
                run._base() + ["exec", ODOO_CONTAINER,
                               "tar", "-cf", "-", "-C", "/var/lib/odoo/filestore", db],
                stdout=subprocess.PIPE)
            subprocess.run(["gzip"], stdin=p1.stdout, stdout=fh, check=True)
            p1.wait()
    except Exception:
        warn("Filestore vide ou absent (base neuve) — ignoré.")
    info(f"Base      : {dump} ({dump.stat().st_size // 1024} Ko)")
    if fs.exists():
        info(f"Filestore : {fs}")


# --------------------------------------------------------------------------- #
# 3. Copie du code dans les addons du conteneur
# --------------------------------------------------------------------------- #
def _copy_tree(run: Runner, dest_parent: Path) -> Path:
    """Copie le source dans dest_parent/MODULE_NAME en filtrant les exclusions."""
    target = dest_parent / MODULE_NAME

    def ignore(dirpath, names):
        skip = set()
        for n in names:
            if n in EXCLUDE or Path(n).suffix in EXCLUDE_SUFFIX:
                skip.add(n)
        return skip

    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(MODULE_SRC, target, ignore=ignore)
    return target


def deploy_code(run: Runner) -> None:
    """Injecte le module dans /mnt/extra-addons du conteneur.

    On copie d'abord vers un dossier temporaire propre, puis on l'envoie
    dans le conteneur avec `docker cp` (indépendant des droits du bind-mount
    hôte, souvent détenu par root)."""
    if run.dry_run:
        info(f"[dry-run] copie filtrée de {MODULE_SRC} vers "
             f"{ODOO_CONTAINER}:/mnt/extra-addons/{MODULE_NAME}")
        return
    with tempfile.TemporaryDirectory() as tmp:
        staged = _copy_tree(run, Path(tmp))
        size_kb = sum(f.stat().st_size for f in staged.rglob("*") if f.is_file()) // 1024
        # Remplacement propre côté conteneur. Le nettoyage se fait en root
        # (-u 0) car les fichiers présents peuvent appartenir à un autre uid
        # qu'Odoo ; docker cp écrit ensuite avec les droits du démon.
        run.docker(["exec", "-u", "0", ODOO_CONTAINER, "rm", "-rf",
                    f"/mnt/extra-addons/{MODULE_NAME}"], check=False)
        run.docker(["cp", str(staged),
                    f"{ODOO_CONTAINER}:/mnt/extra-addons/"])
        info(f"Copié dans {ODOO_CONTAINER}:/mnt/extra-addons/{MODULE_NAME} ({size_kb} Ko)")
    # Contrôle de visibilité.
    r = run.docker(["exec", ODOO_CONTAINER, "test", "-f",
                    f"/mnt/extra-addons/{MODULE_NAME}/__manifest__.py"], check=False)
    if r.returncode != 0:
        die("Le module n'est pas visible dans /mnt/extra-addons du conteneur.")


# --------------------------------------------------------------------------- #
# 4. Installation / mise à jour
# --------------------------------------------------------------------------- #
def install_or_upgrade(run: Runner, db: str, action: str, with_demo: bool,
                       db_exists: bool) -> None:
    flag = "-i" if action == "install" else "-u"
    args = ["odoo", "-c", ODOO_CONF, "-d", db, flag, MODULE_NAME,
            "--stop-after-init", "--no-http", "--log-level=info"]
    if not db_exists and not with_demo:
        args.append("--without-demo=all")

    if run.dry_run:
        info(f"[dry-run] docker exec {ODOO_CONTAINER} {' '.join(args)}")
        return

    log = Path(tempfile.gettempdir()) / f"{MODULE_NAME}-deploy-{int(time.time())}.log"
    info(f"Journal complet : {log}")
    proc = subprocess.Popen(run._base() + ["exec", ODOO_CONTAINER] + args,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)
    lines: list[str] = []
    with log.open("w") as fh:
        for line in proc.stdout:          # type: ignore[union-attr]
            fh.write(line)
            lines.append(line)
            low = line.lower()
            if any(k in low for k in ("error", "critical", "modules loaded",
                                      "loading module")):
                sys.stdout.write("    " + line)
    rc = proc.wait()
    has_fatal = any((" ERROR " in l or " CRITICAL " in l) for l in lines)
    if rc != 0 or has_fatal:
        print(f"\n{ERR}--- extrait des erreurs ---{OFF}", file=sys.stderr)
        for l in lines:
            if " ERROR " in l or " CRITICAL " in l or "Traceback" in l:
                sys.stderr.write(l)
        die(f"Échec de l'opération (code {rc}). Journal : {log}")


# --------------------------------------------------------------------------- #
# 5. Redémarrage + contrôle final
# --------------------------------------------------------------------------- #
def restart_and_verify(run: Runner, db: str) -> None:
    if run.dry_run:
        info(f"[dry-run] restart {ODOO_SERVICE} + contrôle HTTP")
        return
    subprocess.run(run._base() + ["compose", "-f",
                   str(INSTANCE_DIR / "docker-compose.yml"), "restart",
                   ODOO_SERVICE], check=True)
    for i in range(1, 31):
        r = run.docker(["exec", ODOO_CONTAINER, "curl", "-sf", "-o",
                        "/dev/null", "http://localhost:8069/web/login"],
                       check=False)
        if r.returncode == 0:
            info(f"Odoo répond (après {i}s).")
            break
        time.sleep(1)
    else:
        warn(f"Odoo ne répond pas encore — vérifie : docker logs {ODOO_CONTAINER}")

    state = run.psql(db, f"select state from ir_module_module where name='{MODULE_NAME}'")
    ver = run.psql(db, f"select latest_version from ir_module_module where name='{MODULE_NAME}'")
    info(f"Module {MODULE_NAME} : état={state or '?'} version={ver or '?'}")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Déploie SILINA-EDU dans l'instance Odoo dockerisée.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-d", "--database", default=DEFAULT_DB,
                    help=f"Base de données cible (défaut: {DEFAULT_DB})")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("-i", "--install", action="store_true", help="Force l'installation")
    grp.add_argument("-u", "--upgrade", action="store_true", help="Force la mise à jour")
    grp.add_argument("-s", "--sync-only", action="store_true",
                     help="Copie le code, sans toucher à la base")
    ap.add_argument("--with-demo", action="store_true",
                    help="Charge les données de démo (création de base uniquement)")
    ap.add_argument("--no-backup", action="store_true", help="Saute la sauvegarde")
    ap.add_argument("--no-restart", action="store_true", help="Ne redémarre pas Odoo")
    ap.add_argument("--force-version", action="store_true",
                    help="Ignore l'incompatibilité de version module/serveur")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="Affiche les actions sans les exécuter")
    a = ap.parse_args()

    db = a.database
    run = Runner(a.dry_run)

    # 1. Préflight ---------------------------------------------------------- #
    step("Préflight")
    if not (MODULE_SRC / "__manifest__.py").exists():
        die(f"Manifeste introuvable dans {MODULE_SRC}")
    if not (INSTANCE_DIR / "docker-compose.yml").exists():
        die(f"Instance introuvable : {INSTANCE_DIR}")
    if not shutil.which("docker"):
        die("docker n'est pas installé.")
    if not run.container_running(ODOO_CONTAINER):
        die(f"Conteneur '{ODOO_CONTAINER}' arrêté. "
            f"Démarre-le : (cd {INSTANCE_DIR} && docker compose up -d)")
    if not run.container_running(DB_CONTAINER):
        die(f"Conteneur '{DB_CONTAINER}' arrêté.")
    info(f"Conteneurs {ODOO_CONTAINER} / {DB_CONTAINER} actifs.")

    manifest = read_manifest()
    static_checks(manifest)
    check_version(run, manifest, a.force_version)

    db_exists = run.psql("postgres",
                         f"select 1 from pg_database where datname='{db}'") == "1"
    state = ""
    if db_exists:
        state = run.psql(db,
                         f"select state from ir_module_module where name='{MODULE_NAME}'")
        info(f"Base '{db}' présente — module : {state or 'absent'}")
    else:
        info(f"Base '{db}' inexistante : elle sera créée.")

    if a.install:
        action = "install"
    elif a.upgrade:
        action = "upgrade"
    elif a.sync_only:
        action = "sync"
    else:
        action = "upgrade" if state in ("installed", "to upgrade") else "install"
    info(f"Action retenue : {action}")

    # 2. Sauvegarde --------------------------------------------------------- #
    if not a.no_backup and db_exists and action != "sync":
        step(f"Sauvegarde de '{db}'")
        backup(run, db)

    # 3. Copie du code ------------------------------------------------------ #
    step("Déploiement du code")
    deploy_code(run)
    if action == "sync":
        step("Terminé (copie seule, base non modifiée).")
        return

    # 4. Install / upgrade -------------------------------------------------- #
    step(f"{'Installation' if action == 'install' else 'Mise à jour'} de "
         f"{MODULE_NAME} sur '{db}'")
    install_or_upgrade(run, db, action, a.with_demo, db_exists)

    # 5. Redémarrage -------------------------------------------------------- #
    if not a.no_restart:
        step("Redémarrage et contrôle")
        restart_and_verify(run, db)

    step(f"Déploiement terminé — http://localhost:8069 (base : {db})")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        die(f"Commande échouée ({exc.returncode}) : {' '.join(map(str, exc.cmd))}")
    except KeyboardInterrupt:
        die("Interrompu.")
