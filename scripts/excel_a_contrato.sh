#!/usr/bin/env bash
# Convierte cada documento de alcance (Excel ODCS) en su contrato YAML.
#   alcance/<flujo>/<nombre>.xlsx  ->  contracts/<flujo>/<nombre>.odcs.yaml
# Uso: scripts/excel_a_contrato.sh
set -euo pipefail
cd "$(dirname "$0")/.."

shopt -s nullglob
archivos=(alcance/*/*.xlsx)
if [ ${#archivos[@]} -eq 0 ]; then
  echo "No hay documentos de alcance en alcance/*/*.xlsx"
  exit 0
fi

for xlsx in "${archivos[@]}"; do
  [[ "$(basename "$xlsx")" == ~\$* ]] && continue   # archivos temporales de Excel
  flujo=$(basename "$(dirname "$xlsx")")
  nombre=$(basename "$xlsx" .xlsx)
  destino="contracts/${flujo}/${nombre}.odcs.yaml"
  mkdir -p "contracts/${flujo}"
  echo "▶ ${xlsx}  →  ${destino}"
  datacontract import excel --source "$xlsx" --output "$destino" > /dev/null
  datacontract lint "$destino"
done
