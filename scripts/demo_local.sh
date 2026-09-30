#!/usr/bin/env bash
# Demo local de punta a punta, sin Databricks (usa DuckDB sobre CSV).
# Uso: scripts/demo_local.sh
set -uo pipefail
cd "$(dirname "$0")/.."

C=contracts/landing_ded/ded_tarifario_prestacion.odcs.yaml
DATA=data/sample
TMP=$(mktemp -d)
trap 'cp "$DATA/ded_tarifario_prestacion_ok.csv" "$DATA/ded_tarifario_prestacion.csv"; rm -rf "$TMP"' EXIT

paso() { printf '\n\033[1m━━ %s\033[0m\n' "$1"; }

paso "1. Excel del documento de alcance → contrato YAML"
scripts/excel_a_contrato.sh

paso "2. Artefactos derivados del contrato (DDL Databricks + HTML)"
scripts/generar_artefactos.sh
cat generated/ded_tarifario_prestacion.databricks.sql

paso "3. Test con datos correctos (esperado: 🟢)"
cp "$DATA/ded_tarifario_prestacion_ok.csv" "$DATA/ded_tarifario_prestacion.csv"
datacontract test --server local "$C" | tail -1

paso "4. Test con datos con errores (esperado: 🔴)"
cp "$DATA/ded_tarifario_prestacion_errores.csv" "$DATA/ded_tarifario_prestacion.csv"
datacontract test --server local "$C" | grep -E "failed|🔴"

paso "5. Cambio compatible en el contrato: agregar columna opcional (esperado: pasa)"
python3 - "$C" "$TMP/v_compatible.yaml" <<'EOF'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
d["version"] = "1.1.0"
d["schema"][0]["properties"].append({
    "id": "obs_registro", "name": "obs_registro", "logicalType": "string",
    "physicalType": "STRING", "required": False, "description": "Observación opcional."})
yaml.safe_dump(d, open(sys.argv[2], "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
EOF
datacontract breaking "$C" "$TMP/v_compatible.yaml" > /dev/null && echo "✅ breaking: sin cambios incompatibles"

paso "6. Cambio que rompe: eliminar columna usr_registro (esperado: bloquea)"
python3 - "$C" "$TMP/v_rompe.yaml" <<'EOF'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
d["version"] = "2.0.0"
d["schema"][0]["properties"] = [p for p in d["schema"][0]["properties"] if p["name"] != "usr_registro"]
yaml.safe_dump(d, open(sys.argv[2], "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
EOF
if datacontract breaking "$C" "$TMP/v_rompe.yaml" > /dev/null; then
  echo "⚠️  no se detectó el cambio incompatible"
else
  echo "⛔ breaking: cambio incompatible detectado → el PR se bloquearía"
fi
