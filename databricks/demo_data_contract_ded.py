# Databricks notebook source
# MAGIC %md
# MAGIC # Demo Data Contract — Landing DED: `ded_tarifario_prestacion`
# MAGIC
# MAGIC Flujo que demuestra este notebook, todo derivado del contrato ODCS del repo:
# MAGIC
# MAGIC 1. **DDL desde el contrato** → crea la tabla en Unity Catalog (tipos, NOT NULL, PK, comentarios).
# MAGIC 2. **Quality gate** → valida el DataFrame *antes* de escribir. Si falla, no se publica nada.
# MAGIC 3. **Carga** → escribe la tabla solo si el gate pasó.
# MAGIC 4. **Validación post-carga** → vuelve a validar el contrato contra la tabla física.
# MAGIC
# MAGIC Usa el widget **escenario** para cargar datos correctos (`ok`) o con errores (`errores`).
# MAGIC
# MAGIC > Datos 100% sintéticos. Requiere que el repo esté clonado como Git folder en el workspace.

# COMMAND ----------

# MAGIC %pip install -q "datacontract-cli[databricks]==1.2.2"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace", "Catálogo UC")
dbutils.widgets.text("schema", "landing_ded", "Esquema")
dbutils.widgets.dropdown("escenario", "ok", ["ok", "errores"], "Datos a cargar")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
ESCENARIO = dbutils.widgets.get("escenario")
print(f"catálogo={CATALOG} | esquema={SCHEMA} | escenario={ESCENARIO}")

# COMMAND ----------

# MAGIC %md ## 0. Leer el contrato del repo

# COMMAND ----------

import os

import pandas as pd
import yaml
from datacontract.data_contract import DataContract

# El notebook vive en <repo>/databricks/, el contrato en <repo>/contracts/
REPO_ROOT = os.path.abspath(os.path.join(os.getcwd(), ".."))
CONTRACT_PATH = os.path.join(REPO_ROOT, "contracts", "landing_ded", "ded_tarifario_prestacion.odcs.yaml")

with open(CONTRACT_PATH, encoding="utf-8") as f:
    contract = yaml.safe_load(f)

# El catálogo/esquema del ambiente se toman de los widgets, no del YAML
for server in contract["servers"]:
    if server["server"] == "databricks_dev":
        server["catalog"] = CATALOG
        server["schema"] = SCHEMA

CONTRACT_STR = yaml.safe_dump(contract, allow_unicode=True, sort_keys=False)
MODEL = contract["schema"][0]
TABLE = MODEL["physicalName"]
FQN = f"{CATALOG}.{SCHEMA}.{TABLE}"

print(f"Contrato: {contract['id']} v{contract['version']} ({contract['status']})")
print(f"Tabla destino: {FQN}")


def mostrar_resultado(run, titulo):
    """Muestra los checks de un run del CLI y devuelve True si pasó."""
    filas = [
        {
            "resultado": str(c.result.value if hasattr(c.result, "value") else c.result),
            "check": c.name,
            "campo": c.field,
            "detalle": c.reason,
        }
        for c in run.checks
    ]
    resumen = pd.DataFrame(filas)
    fallidos = resumen[resumen["resultado"] != "passed"]
    estado = "🟢 CUMPLE" if run.has_passed() else "🔴 NO CUMPLE"
    print(f"{titulo}: {estado} — {len(resumen)} checks, {len(fallidos)} fallidos")
    display(fallidos if len(fallidos) else resumen)
    return run.has_passed()

# COMMAND ----------

# MAGIC %md ## 1. DDL generado desde el contrato

# COMMAND ----------

ddl = DataContract(data_contract_str=CONTRACT_STR, server="databricks_dev").export(
    "sql", sql_server_type="databricks"
)
print(ddl)

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(ddl.strip().rstrip(";"))  # CREATE OR REPLACE: la demo recrea la tabla en cada corrida

# COMMAND ----------

# MAGIC %md ## 2. Leer el archivo del DED y tipar según el contrato

# COMMAND ----------

from pyspark.sql.types import StringType, StructField, StructType

archivo = f"ded_tarifario_prestacion_{ESCENARIO}.csv"
pdf = pd.read_csv(os.path.join(REPO_ROOT, "data", "sample", archivo), dtype=str, keep_default_na=False)
pdf = pdf.astype(object).where(pdf != "", None)  # vacíos -> NULL

df_raw = spark.createDataFrame(pdf, schema=StructType([StructField(c, StringType(), True) for c in pdf.columns]))

# Tipos físicos tomados del contrato (TRY_CAST: un valor no convertible queda NULL y lo atrapa el gate)
columnas = [
    f"TRY_CAST(`{p['name']}` AS {p['physicalType']}) AS `{p['name']}`" for p in MODEL["properties"]
]
df = df_raw.selectExpr(*columnas)
print(f"Archivo: {archivo} — {df.count()} filas")
display(df)

# COMMAND ----------

# MAGIC %md ## 3. Quality gate: validar el DataFrame ANTES de publicar

# COMMAND ----------

df.createOrReplaceTempView(TABLE)
run_gate = DataContract(data_contract_str=CONTRACT_STR, server="gate", spark=spark).test()
spark.catalog.dropTempView(TABLE)  # evita que la vista tape a la tabla física en el paso 5

if not mostrar_resultado(run_gate, "Gate pre-publicación"):
    raise Exception(
        f"El archivo {archivo} no cumple el contrato {contract['id']}. "
        "No se publica la tabla. Revisa los checks fallidos arriba."
    )

# COMMAND ----------

# MAGIC %md ## 4. Carga (solo llega aquí si el gate pasó)

# COMMAND ----------

df.write.mode("overwrite").insertInto(FQN)
print(f"Cargadas {spark.table(FQN).count()} filas en {FQN}")

# COMMAND ----------

# MAGIC %md ## 5. Validación post-carga contra la tabla física

# COMMAND ----------

run_tabla = DataContract(data_contract_str=CONTRACT_STR, server="databricks_dev", spark=spark).test()
if not mostrar_resultado(run_tabla, f"Tabla {FQN}"):
    raise Exception(f"La tabla {FQN} no cumple el contrato {contract['id']}.")
