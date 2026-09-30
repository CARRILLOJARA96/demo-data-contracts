# CLAUDE.md

Demo de **data contracts** (ODCS v3.2.0 + Data Contract CLI 1.2.2) para un flujo **Landing DED**
(Data Entry de Landing) de un lakehouse en Azure/Databricks con capas landing → trusted (Data Vault 2.0)
→ enriched. El objetivo es validar el enfoque antes de llevarlo al framework del área de datos.
Ver `README.md` para la guía de uso.

## Reglas del repo (no romper)

- **El Excel es la fuente de verdad.** `alcance/<flujo>/<nombre>.xlsx` (plantilla oficial ODCS) genera
  `contracts/<flujo>/<nombre>.odcs.yaml` con `scripts/excel_a_contrato.sh`. **No editar el YAML a mano**:
  CI regenera desde el Excel y falla con `git diff` si no coinciden.
- Para cambiar un contrato de forma programática: modificar un YAML temporal → `datacontract export excel`
  al `.xlsx` → `scripts/excel_a_contrato.sh`. La conversión Excel↔YAML es determinística y sin pérdidas (verificado).
- `generated/` (DDL + HTML) es derivado: regenerar con `scripts/generar_artefactos.sh`, nunca editar.
- Datos siempre **sintéticos**. Nunca agregar datos reales ni de pacientes.
- Versión fijada: `datacontract-cli==1.2.2`. Si se cambia, actualizar `requirements.txt`, el workflow y el `%pip` del notebook.

## Comandos

```bash
scripts/demo_local.sh                     # demo completa local (DuckDB sobre CSV), 6 pasos
scripts/excel_a_contrato.sh               # Excel -> YAML + lint
scripts/generar_artefactos.sh             # DDL Databricks + HTML
scripts/ci_breaking.sh origin/main        # breaking changes vs rama base (lo usa CI)
datacontract test --server local contracts/landing_ded/ded_tarifario_prestacion.odcs.yaml
datacontract lint <contrato>
datacontract changelog <v1> <v2>
```

`data/sample/ded_tarifario_prestacion.csv` es el archivo que lee el servidor `local`; es copia de `_ok.csv`.
`demo_local.sh` lo reemplaza temporalmente por `_errores.csv` y lo restaura al terminar.

## Entorno local (Windows + Git Bash)

- Activar: `source .venv/Scripts/activate` (no `bin/`), y `export PYTHONUTF8=1` en cada terminal nueva
  (la salida del CLI usa emojis; sin esto puede fallar la consola).
- Existe `.venv/Scripts/python3.exe` (copia de `python.exe`) porque los scripts llaman a `python3`.
- Instalar siempre dentro del `.venv`: el Python global (Microsoft Store) falla con `WinError 206` (ruta larga).

## Diseño y decisiones

- **Servidores del contrato**: `local` (CSV + DuckDB), `gate` (`type: custom` + `customProperties.customType: dataframe`,
  forma estándar ODCS de declarar un DataFrame de Spark) y `databricks_dev` (Unity Catalog, `catalog: workspace`,
  `schema: landing_ded`; el notebook los sobreescribe con widgets).
- **Notebook** `databricks/demo_data_contract_ded.py` (formato source de Databricks): DDL desde el contrato →
  lee CSV y castea con `TRY_CAST` a los tipos físicos del contrato → **gate** sobre una temp view con el nombre
  del modelo → `insertInto` solo si pasa → validación post-carga contra la tabla. La temp view se elimina antes
  del paso post-carga porque taparía a la tabla física.
- El CLI genera solo el check de duplicados desde `primaryKey`; no duplicar esa regla como SQL.
- Propiedades del framework van en `customProperties` (contrato: `capa`, `flujo`, `subdominio`, `frecuenciaCarga`).
- El DDL exportado usa `CREATE OR REPLACE TABLE` y una PK informativa (requiere Unity Catalog).

## Comportamiento verificado

- Datos `_ok`: 29 checks en local / 39 en Spark, todos en verde. Datos `_errores`: 8 checks fallidos
  (patrón clínica, largo prestación, moneda EUR, tarifa 0 ×2, usuario nulo, PK duplicada, vigencia invertida).
- `datacontract breaking` sale con 1 solo ante cambios incompatibles (quitar columna, cambiar tipo); agregar columna
  opcional sale con 0. `datacontract test` sale con 1 ante datos inválidos.
- Agregar una columna al contrato hace fallar el test de humo hasta que los datos de muestra la traigan (esperado).
- El notebook se probó con PySpark 4 local, no en un workspace real; en UC `information_schema.columns` sí existe.

## Próximos pasos posibles

- Mapear el documento de alcance DED real (no la plantilla ODCS) o escribir un conversor desde su formato.
- Convenciones Data Vault (hub/link/sat, business key, hash key) como `customProperties` para la capa trusted.
- Clasificación DAC en el atributo `classification` de cada campo.
- Job de Databricks disparado desde GitHub Actions al hacer merge a `main`.
