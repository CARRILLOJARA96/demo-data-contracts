#!/usr/bin/env bash
# Genera los artefactos derivados de cada contrato:
#   generated/<nombre>.databricks.sql  (DDL para Unity Catalog)
#   generated/<nombre>.html            (documentación navegable)
# Uso: scripts/generar_artefactos.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p generated

for contrato in contracts/*/*.odcs.yaml; do
  nombre=$(basename "$contrato" .odcs.yaml)
  echo "▶ ${contrato}"
  datacontract export sql --dialect databricks --server databricks_dev \
    --output "generated/${nombre}.databricks.sql" "$contrato" > /dev/null
  datacontract export html --output "generated/${nombre}.html" "$contrato" > /dev/null
done
ls -1 generated
