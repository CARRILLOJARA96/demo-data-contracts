#!/usr/bin/env bash
# Compara cada contrato modificado contra la rama base y falla si hay cambios incompatibles.
# Uso: scripts/ci_breaking.sh <ref-base>      (ej. origin/main)
# Escribe un resumen en $GITHUB_STEP_SUMMARY si existe.
set -uo pipefail
cd "$(dirname "$0")/.."

BASE=${1:?"indica la referencia base, ej. origin/main"}
SUMMARY=${GITHUB_STEP_SUMMARY:-/dev/null}
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
export COLUMNS=200
fallo=0

echo "## Cambios en contratos de datos" >> "$SUMMARY"
cambiados=$(git diff --name-only "$BASE"...HEAD -- contracts/ | grep '\.odcs\.yaml$' || true)
if [ -z "$cambiados" ]; then
  echo "Sin cambios en contratos." | tee -a "$SUMMARY"
  exit 0
fi

for c in $cambiados; do
  if [ ! -f "$c" ]; then
    echo "::error file=$c::Se eliminó el contrato. Es un cambio incompatible para sus consumidores."
    echo "- ⛔ \`$c\` eliminado" >> "$SUMMARY"
    fallo=1; continue
  fi
  if ! git cat-file -e "$BASE:$c" 2>/dev/null; then
    echo "🆕 contrato nuevo: $c"
    echo "- 🆕 \`$c\` nuevo" >> "$SUMMARY"
    continue
  fi
  git show "$BASE:$c" > "$TMP/base.yaml"
  { echo "### \`$c\`"; echo '```'; datacontract changelog "$TMP/base.yaml" "$c"; echo '```'; } >> "$SUMMARY" 2>&1
  if datacontract breaking "$TMP/base.yaml" "$c"; then
    echo "✅ $c: cambios compatibles"
  else
    echo "::error file=$c::Cambio incompatible respecto a $BASE. Requiere versión mayor y acuerdo con los consumidores."
    echo "- ⛔ \`$c\` tiene cambios incompatibles" >> "$SUMMARY"
    fallo=1
  fi
done
exit $fallo
