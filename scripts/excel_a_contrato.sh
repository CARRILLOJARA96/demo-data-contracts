#!/usr/bin/env bash
# Convierte cada documento de alcance en su contrato ODCS. Reconoce dos formatos:
#   - DED de gobierno (tiene la hoja "DED"):
#       alcance/<flujo>/<nombre>.xlsx  (+ <nombre>.contrato.yaml opcional)
#       → contracts/<flujo>/<tabla_landing>.odcs.yaml   con scripts/ded_a_contrato.py
#   - Plantilla Excel ODCS:
#       alcance/<flujo>/<nombre>.xlsx → contracts/<flujo>/<nombre>.odcs.yaml   con datacontract import excel
# Uso: scripts/excel_a_contrato.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY=$(command -v python3 || command -v python)

shopt -s nullglob
archivos=(alcance/*/*.xlsx)
if [ ${#archivos[@]} -eq 0 ]; then
  echo "No hay documentos de alcance en alcance/*/*.xlsx"
  exit 0
fi

es_ded() {
  "$PY" -c "import sys, warnings, openpyxl; warnings.filterwarnings('ignore'); \
sys.exit(0 if 'DED' in openpyxl.load_workbook(sys.argv[1], read_only=True).sheetnames else 1)" "$1"
}

for xlsx in "${archivos[@]}"; do
  [[ "$(basename "$xlsx")" == ~\$* ]] && continue   # archivos temporales de Excel abiertos
  if es_ded "$xlsx"; then
    echo "▶ ${xlsx}  (DED)"
    "$PY" scripts/ded_a_contrato.py "$xlsx"
  else
    flujo=$(basename "$(dirname "$xlsx")")
    destino="contracts/${flujo}/$(basename "$xlsx" .xlsx).odcs.yaml"
    mkdir -p "contracts/${flujo}"
    echo "▶ ${xlsx}  (plantilla ODCS)  →  ${destino}"
    datacontract import excel --source "$xlsx" --output "$destino" > /dev/null
  fi
done

for contrato in contracts/*/*.odcs.yaml; do
  if ! datacontract lint "$contrato" > /dev/null; then
    echo "  ❌ lint ODCS falló: ${contrato}"
    datacontract lint "$contrato"
    exit 1
  fi
  echo "  🟢 lint ODCS: ${contrato}"
done
