#!/usr/bin/env bash
# Demo local de punta a punta, sin Databricks (DuckDB sobre CSV), con el DED de_maestro_canal.
# Uso: scripts/demo_local.sh
set -uo pipefail
cd "$(dirname "$0")/.."
PY=$(command -v python3 || command -v python)

DED=alcance/landing_ded/de_maestro_canal.xlsx
C=contracts/landing_ded/de_maestro_canal.odcs.yaml
DATA=data/sample
TMP=$(mktemp -d)
trap 'cp "$DATA/de_maestro_canal_ok.csv" "$DATA/de_maestro_canal.csv"; rm -rf "$TMP"' EXIT

paso() { printf '\n\033[1m━━ %s\033[0m\n' "$1"; }

paso "1. Documentos de alcance (DED de gobierno y plantilla ODCS) → contratos ODCS"
scripts/excel_a_contrato.sh

paso "2. DED mal llenado → el conversor se detiene y dice qué corregir y quién (esperado: ❌)"
"$PY" - "$DED" "$TMP/de_con_errores.xlsx" <<'EOF'
import sys, warnings, openpyxl
warnings.filterwarnings("ignore")
wb = openpyxl.load_workbook(sys.argv[1])
t, d = wb["Informacion - tabla"], wb["DED"]
t["I8"] = "De Maestro Canal"                 # nombre de tabla no válido (Data Modeler)
t["D8"] = "Canales"                          # dominio fuera de la lista (Data Steward)
d["G12"] = "Cod Canal Venta"                 # nombre modelado con espacios (Data Modeler)
d["J15"] = "Numerico"                        # formato landing inválido
d["K13"] = None                              # falta la definición del campo (Data Governance)
wb.save(sys.argv[2])
EOF
if "$PY" scripts/ded_a_contrato.py "$TMP/de_con_errores.xlsx" --output "$TMP/x.yaml"; then
  echo "⚠️  el conversor no detectó los errores"
fi

paso "3. Artefactos derivados del contrato (DDL Databricks + HTML)"
scripts/generar_artefactos.sh
cat generated/de_maestro_canal.databricks.sql

paso "4. Test con datos correctos (esperado: 🟢)"
cp "$DATA/de_maestro_canal_ok.csv" "$DATA/de_maestro_canal.csv"
datacontract test --server local "$C" | tail -1

paso "5. Test con datos con errores (esperado: 🔴)"
cp "$DATA/de_maestro_canal_errores.csv" "$DATA/de_maestro_canal.csv"
datacontract test --server local "$C" | grep -E "failed|🔴"

paso "6. Cambio compatible: nuevo campo que admite nulos (esperado: pasa)"
"$PY" - "$C" "$TMP/v_compatible.yaml" <<'EOF'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
d["version"] = "1.1.0"
d["schema"][0]["properties"].append({
    "id": "obs_canal", "name": "obs_canal", "logicalType": "string",
    "physicalType": "STRING", "required": False, "description": "Observación opcional."})
yaml.safe_dump(d, open(sys.argv[2], "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
EOF
datacontract breaking "$C" "$TMP/v_compatible.yaml" > /dev/null && echo "✅ breaking: sin cambios incompatibles"

paso "7. Cambio que rompe: se elimina el campo nom_canal_distribucion (esperado: bloquea)"
"$PY" - "$C" "$TMP/v_rompe.yaml" <<'EOF'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
d["version"] = "2.0.0"
d["schema"][0]["properties"] = [p for p in d["schema"][0]["properties"] if p["name"] != "nom_canal_distribucion"]
yaml.safe_dump(d, open(sys.argv[2], "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
EOF
if datacontract breaking "$C" "$TMP/v_rompe.yaml" > /dev/null; then
  echo "⚠️  no se detectó el cambio incompatible"
else
  echo "⛔ breaking: cambio incompatible detectado → el PR se bloquearía"
fi
