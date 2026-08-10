#!/usr/bin/env bash
#
# deploy.sh — Déploiement du module SILINA-EDU dans une instance Odoo dockerisée.
#
#   ./deploy.sh                      # déploie + installe/met à jour sur la base par défaut
#   ./deploy.sh -d ma_base           # cible une autre base
#   ./deploy.sh --mode mount         # dev : bind-mount du code source (rechargement à chaud)
#   ./deploy.sh --no-restart -n      # simulation, sans redémarrage
#   ./deploy.sh --help
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration (surchargeable par variables d'environnement)
# ---------------------------------------------------------------------------
MODULE_NAME="${MODULE_NAME:-silina_edu}"
MODULE_SRC="${MODULE_SRC:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
INSTANCE_DIR="${INSTANCE_DIR:-/home/doctorpy/Projects/perso/odoo_apps/odoo1}"
ODOO_SERVICE="${ODOO_SERVICE:-odoo}"
ODOO_CONTAINER="${ODOO_CONTAINER:-odoo1_app}"
DB_CONTAINER="${DB_CONTAINER:-odoo1_db}"
DB_USER="${DB_USER:-odoo}"
DB_NAME="${DB_NAME:-csbonscitoyens}"
ODOO_CONF="${ODOO_CONF:-/etc/odoo/odoo.conf}"
ADDONS_DIR="${ADDONS_DIR:-$INSTANCE_DIR/addons}"
BACKUP_DIR="${BACKUP_DIR:-$INSTANCE_DIR/backups}"

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
MODE="copy"          # copy | mount
DO_BACKUP=1
DO_RESTART=1
DRY_RUN=0
FORCE_VERSION=0
WITH_DEMO=0
ACTION="auto"        # auto | install | upgrade | sync

usage() {
    sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    cat <<'EOF'

Options :
  -d, --database NOM    Base de données cible          (défaut: csbonscitoyens)
  -m, --mode MODE       copy (rsync dans addons/) | mount (bind-mount dev)
  -i, --install         Force l'installation (-i)
  -u, --upgrade         Force la mise à jour (-u)
  -s, --sync-only       Copie les fichiers, sans toucher à la base
      --with-demo       Charge les données de démo (création de base uniquement)
      --no-backup       Ne pas sauvegarder la base avant mise à jour
      --no-restart      Ne pas redémarrer le conteneur Odoo à la fin
      --force-version   Ignore l'incompatibilité de version module/serveur
  -n, --dry-run         Affiche les actions sans les exécuter
  -h, --help            Cette aide
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -d|--database)   DB_NAME="$2"; shift 2 ;;
        -m|--mode)       MODE="$2"; shift 2 ;;
        -i|--install)    ACTION="install"; shift ;;
        -u|--upgrade)    ACTION="upgrade"; shift ;;
        -s|--sync-only)  ACTION="sync"; shift ;;
        --with-demo)     WITH_DEMO=1; shift ;;
        --no-backup)     DO_BACKUP=0; shift ;;
        --no-restart)    DO_RESTART=0; shift ;;
        --force-version) FORCE_VERSION=1; shift ;;
        -n|--dry-run)    DRY_RUN=1; shift ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "Option inconnue : $1" >&2; usage; exit 2 ;;
    esac
done

[[ "$MODE" =~ ^(copy|mount)$ ]] || { echo "--mode doit valoir 'copy' ou 'mount'" >&2; exit 2; }

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
    C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
    C_OK=''; C_WARN=''; C_ERR=''; C_DIM=''; C_OFF=''
fi
step() { printf '\n%s==>%s %s\n' "$C_OK" "$C_OFF" "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
die()  { printf '%s[x]%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; exit 1; }
run()  {
    if (( DRY_RUN )); then printf '%s    [dry-run] %s%s\n' "$C_DIM" "$*" "$C_OFF"
    else "$@"; fi
}

# sudo uniquement si nécessaire
SUDO=""
docker info >/dev/null 2>&1 || SUDO="sudo"
DOCKER="${SUDO:+$SUDO }docker"
dk() { $SUDO docker "$@"; }
dc() { $SUDO docker compose -f "$INSTANCE_DIR/docker-compose.yml" "$@"; }

# ---------------------------------------------------------------------------
# 1. Préflight
# ---------------------------------------------------------------------------
step "Préflight"

[[ -f "$MODULE_SRC/__manifest__.py" ]] || die "Manifeste introuvable dans $MODULE_SRC"
[[ -f "$INSTANCE_DIR/docker-compose.yml" ]] || die "Instance introuvable : $INSTANCE_DIR"
command -v docker >/dev/null || die "docker n'est pas installé"
command -v rsync  >/dev/null || die "rsync est requis (apt install rsync)"

dk inspect -f '{{.State.Running}}' "$ODOO_CONTAINER" 2>/dev/null | grep -q true \
    || die "Conteneur '$ODOO_CONTAINER' arrêté. Démarre-le : (cd $INSTANCE_DIR && docker compose up -d)"
dk inspect -f '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null | grep -q true \
    || die "Conteneur '$DB_CONTAINER' arrêté."
info "Conteneurs $ODOO_CONTAINER / $DB_CONTAINER actifs."

# --- Compilation Python + XML bien formé + fichiers du manifeste présents ---
python3 - "$MODULE_SRC" <<'PY' || die "Le module ne passe pas les contrôles statiques."
import ast, pathlib, sys, xml.etree.ElementTree as ET
src, errors = pathlib.Path(sys.argv[1]), []

for py in src.rglob("*.py"):
    if "__pycache__" in py.parts:
        continue
    try:
        compile(py.read_text(encoding="utf-8"), str(py), "exec")
    except SyntaxError as exc:
        errors.append(f"Python  : {py.relative_to(src)}:{exc.lineno} — {exc.msg}")

manifest = ast.literal_eval((src / "__manifest__.py").read_text(encoding="utf-8"))
declared = manifest.get("data", []) + manifest.get("demo", [])
for rel in declared:
    path = src / rel
    if not path.exists():
        errors.append(f"Manquant: {rel} (déclaré dans __manifest__.py)")
    elif path.suffix == ".xml":
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            errors.append(f"XML     : {rel} — {exc}")

for asset in sum(manifest.get("assets", {}).values(), []):
    rel = asset.split("/", 1)[1] if asset.startswith(src.name + "/") else asset
    if not (src / rel).exists():
        errors.append(f"Manquant: asset {asset}")

print(f"    Version du module : {manifest.get('version')}")
print(f"    Dépendances       : {', '.join(manifest.get('depends', []))}")
print(f"    {len(declared)} fichier(s) de données déclaré(s), "
      f"{sum(1 for _ in src.rglob('*.py'))} fichier(s) Python.")
for e in errors:
    print(f"    \033[31m{e}\033[0m")
sys.exit(1 if errors else 0)
PY

# --- Compatibilité de version module <-> serveur ---
MODULE_SERIES="$(python3 -c "import ast,sys; print(ast.literal_eval(open(sys.argv[1]).read())['version'].split('.')[0])" "$MODULE_SRC/__manifest__.py")"
SERVER_SERIES="$(dk exec "$ODOO_CONTAINER" odoo --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1 | cut -d. -f1)"
info "Série module : $MODULE_SERIES — Série serveur : ${SERVER_SERIES:-inconnue}"

if [[ -n "$SERVER_SERIES" && "$MODULE_SERIES" != "$SERVER_SERIES" ]]; then
    warn "Le module cible Odoo $MODULE_SERIES mais le serveur exécute Odoo $SERVER_SERIES."
    warn "Odoo <18 ne reconnaît pas les vues <list> ; l'installation échouera très probablement."
    warn "Corrige en amont (image odoo:$MODULE_SERIES, ou portage du module) — ou relance avec --force-version."
    (( FORCE_VERSION )) || die "Arrêt sur incompatibilité de version."
    warn "--force-version : on continue malgré tout."
fi

# --- Dépendances disponibles côté serveur ---
MISSING_DEPS="$(python3 -c "
import ast,sys; print(' '.join(ast.literal_eval(open(sys.argv[1]).read()).get('depends',[])))
" "$MODULE_SRC/__manifest__.py")"
for dep in $MISSING_DEPS; do
    dk exec "$ODOO_CONTAINER" test -e "/usr/lib/python3/dist-packages/odoo/addons/$dep" \
        || warn "Dépendance '$dep' absente des addons standards (module tiers ? entreprise ?)."
done

# --- État de la base ---
DB_EXISTS=0
if dk exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -tAc \
        "select 1 from pg_database where datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
    DB_EXISTS=1
    MODULE_STATE="$(dk exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
        "select state from ir_module_module where name='$MODULE_NAME'" 2>/dev/null | tr -d '[:space:]')"
    info "Base '$DB_NAME' présente — module : ${MODULE_STATE:-absent}"
else
    MODULE_STATE=""
    info "Base '$DB_NAME' inexistante : elle sera créée."
fi

if [[ "$ACTION" == "auto" ]]; then
    [[ "$MODULE_STATE" == "installed" || "$MODULE_STATE" == "to upgrade" ]] \
        && ACTION="upgrade" || ACTION="install"
fi
info "Action retenue : $ACTION (mode $MODE)"

# ---------------------------------------------------------------------------
# 2. Sauvegarde (base + filestore) avant toute modification
# ---------------------------------------------------------------------------
if (( DO_BACKUP )) && (( DB_EXISTS )) && [[ "$ACTION" != "sync" ]]; then
    step "Sauvegarde de '$DB_NAME'"
    STAMP="$(date +%Y%m%d-%H%M%S)"
    run mkdir -p "$BACKUP_DIR"
    if (( DRY_RUN )); then
        info "[dry-run] pg_dump + tar du filestore vers $BACKUP_DIR/$DB_NAME-$STAMP.*"
    else
        dk exec "$DB_CONTAINER" pg_dump -U "$DB_USER" -Fc "$DB_NAME" \
            > "$BACKUP_DIR/$DB_NAME-$STAMP.dump"
        dk exec "$ODOO_CONTAINER" tar -cf - -C /var/lib/odoo/filestore "$DB_NAME" 2>/dev/null \
            | gzip > "$BACKUP_DIR/$DB_NAME-$STAMP-filestore.tar.gz" || warn "Filestore vide ou absent."
        info "Base      : $BACKUP_DIR/$DB_NAME-$STAMP.dump ($(du -h "$BACKUP_DIR/$DB_NAME-$STAMP.dump" | cut -f1))"
        info "Filestore : $BACKUP_DIR/$DB_NAME-$STAMP-filestore.tar.gz"
        info "Restauration : docker exec -i $DB_CONTAINER pg_restore -U $DB_USER -d $DB_NAME -c < <dump>"
    fi
fi

# ---------------------------------------------------------------------------
# 3. Mise en place du code
# ---------------------------------------------------------------------------
step "Déploiement du code (mode $MODE)"

if [[ "$MODE" == "copy" ]]; then
    TARGET="$ADDONS_DIR/$MODULE_NAME"
    # addons/ appartient à root (créé par Docker) : sudo si non inscriptible
    RS=""; [[ -w "$ADDONS_DIR" ]] || RS="sudo"
    [[ -n "$RS" ]] && info "addons/ non inscriptible : rsync via sudo."
    run mkdir -p "$ADDONS_DIR"
    run ${RS:+$RS} rsync -a --delete \
        --exclude '.git/' --exclude '.idea/' --exclude '__pycache__/' \
        --exclude '*.pyc' --exclude '*.backup' --exclude 'deploy.sh' \
        --exclude '.dockerignore' --exclude '.gitignore' \
        "$MODULE_SRC/" "$TARGET/"
    (( DRY_RUN )) || info "Copié dans $TARGET ($(du -sh "$TARGET" 2>/dev/null | cut -f1))"
else
    OVERRIDE="$INSTANCE_DIR/docker-compose.override.yml"
    step "Génération de $OVERRIDE (bind-mount)"
    if (( DRY_RUN )); then
        info "[dry-run] écriture de l'override bind-mount"
    else
        cat > "$OVERRIDE" <<YML
# Généré par $MODULE_NAME/deploy.sh --mode mount — développement uniquement.
services:
  $ODOO_SERVICE:
    volumes:
      - $MODULE_SRC:/mnt/extra-addons/$MODULE_NAME:ro
YML
        info "Le code source est monté en lecture seule dans le conteneur."
        dc up -d "$ODOO_SERVICE"
    fi
fi

# Vérifie que le module est bien visible depuis l'intérieur du conteneur
(( DRY_RUN )) || dk exec "$ODOO_CONTAINER" test -f "/mnt/extra-addons/$MODULE_NAME/__manifest__.py" \
    || die "Le module n'est pas visible dans /mnt/extra-addons du conteneur."

if [[ "$ACTION" == "sync" ]]; then
    step "Terminé (copie seule, base non modifiée)."
    exit 0
fi

# ---------------------------------------------------------------------------
# 4. Installation / mise à jour
# ---------------------------------------------------------------------------
step "$([[ $ACTION == install ]] && echo Installation || echo 'Mise à jour') de $MODULE_NAME sur '$DB_NAME'"

ODOO_ARGS=(odoo -c "$ODOO_CONF" -d "$DB_NAME" --stop-after-init --no-http --log-level=info)
[[ "$ACTION" == "install" ]] && ODOO_ARGS+=(-i "$MODULE_NAME") || ODOO_ARGS+=(-u "$MODULE_NAME")
(( DB_EXISTS )) || { (( WITH_DEMO )) || ODOO_ARGS+=(--without-demo=all); }

LOG="${TMPDIR:-/tmp}/${MODULE_NAME}-deploy-$(date +%s).log"
if (( DRY_RUN )); then
    info "[dry-run] docker exec $ODOO_CONTAINER ${ODOO_ARGS[*]}"
else
    info "Journal complet : $LOG"
    set +e
    dk exec "$ODOO_CONTAINER" "${ODOO_ARGS[@]}" 2>&1 | tee "$LOG" \
        | grep -Ei 'ERROR|WARNING|CRITICAL|loading|Modules loaded' | tail -40
    RC=${PIPESTATUS[0]}
    set -e
    if (( RC != 0 )) || grep -qE '(CRITICAL|ERROR) ' "$LOG"; then
        printf '\n%s--- extrait des erreurs ---%s\n' "$C_ERR" "$C_OFF" >&2
        grep -E '(CRITICAL|ERROR) ' -A4 "$LOG" | tail -40 >&2
        die "Échec de l'opération (code $RC). Journal : $LOG"
    fi
fi

# ---------------------------------------------------------------------------
# 5. Redémarrage et contrôle final
# ---------------------------------------------------------------------------
if (( DO_RESTART )); then
    step "Redémarrage du service Odoo"
    run dc restart "$ODOO_SERVICE"
    if ! (( DRY_RUN )); then
        for i in $(seq 1 30); do
            if dk exec "$ODOO_CONTAINER" curl -sf -o /dev/null http://localhost:8069/web/login; then
                info "Odoo répond (après ${i}s)."; break
            fi
            sleep 1
            (( i == 30 )) && warn "Odoo ne répond pas encore — vérifie : docker logs $ODOO_CONTAINER"
        done
    fi
fi

if ! (( DRY_RUN )); then
    step "État final"
    dk exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
        "select name, state, latest_version from ir_module_module where name='$MODULE_NAME';"
fi

step "Déploiement terminé — http://localhost:8069 (base : $DB_NAME)"
