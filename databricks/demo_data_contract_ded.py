# Databricks notebook source
# MAGIC %md
# MAGIC # Demo Data Contract — Landing DED: `ded_tarifario_prestacion`
# MAGIC
# MAGIC Flujo que demuestra este notebook, todo derivado del contrato ODCS del repo:
# MAGIC
# MAGIC 1. **Estructura desde el contrato** → crea la tabla si no existe; si existe, solo agrega columnas opcionales
# MAGIC    nuevas. Nunca la recrea: una carga fallida no borra los datos vigentes.
# MAGIC 2. **Quality gate** → valida el DataFrame *antes* de escribir. Si falla, no se publica nada.
# MAGIC 3. **Carga** → reemplaza el contenido de la tabla solo si el gate pasó.
# MAGIC 4. **Validación post-carga** → vuelve a validar el contrato contra la tabla física.
# MAGIC
# MAGIC Widgets: **ambiente** (`desa` / `prod`, servidor del contrato) y **escenario** (`ok` / `errores`).
# MAGIC La tabla destino sale del contrato: `<ambiente>_<capa>.<dominio>_<subdominio>.<tabla>`.
# MAGIC
# MAGIC > Datos 100% sintéticos. Requiere que el repo esté clonado como Git folder en el workspace.

# COMMAND ----------

# MAGIC %pip install -q "datacontract-cli[databricks]==1.2.2" "pandas>=2.2,<3"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.dropdown("ambiente", "desa", ["desa", "prod"], "Ambiente")
dbutils.widgets.dropdown("escenario", "ok", ["ok", "errores"], "Datos a cargar")

AMBIENTE = dbutils.widgets.get("ambiente")
ESCENARIO = dbutils.widgets.get("escenario")

# COMMAND ----------

# MAGIC %md ## 0. Leer el contrato del repo y resolver la tabla destino

# COMMAND ----------

import os

import pandas as pd
from pyspark.sql.types import StringType, StructField, StructType

import contratos  # databricks/contratos.py, junto a este notebook

# El notebook vive en <repo>/databricks/, el contrato en <repo>/contracts/
REPO_ROOT = os.path.abspath(os.path.join(os.getcwd(), ".."))
c = contratos.cargar_contrato(
    os.path.join(REPO_ROOT, "contracts", "landing_ded", "ded_tarifario_prestacion.odcs.yaml"), AMBIENTE
)
print(f"Contrato: {c['contrato']['id']} v{c['contrato']['version']} ({c['contrato']['status']})")
print(f"Ambiente: {AMBIENTE} | escenario: {ESCENARIO} | tabla destino: {c['fqn']}")


def mostrar(titulo, paso, resumen):
    fallidos = resumen[resumen["resultado"] != "passed"]
    print(f"{titulo}: {'🟢 CUMPLE' if paso else '🔴 NO CUMPLE'} — {len(resumen)} checks, {len(fallidos)} fallidos")
    display(fallidos if len(fallidos) else resumen)

# COMMAND ----------

# MAGIC %md ## 1. Estructura de la tabla desde el contrato (idempotente, no destructiva)

# COMMAND ----------

for accion in contratos.asegurar_tabla(spark, c):
    print(accion)

# COMMAND ----------

# MAGIC %md ## 2. Leer el archivo del DED y tipar según el contrato

# COMMAND ----------

archivo = f"ded_tarifario_prestacion_{ESCENARIO}.csv"
pdf = pd.read_csv(os.path.join(REPO_ROOT, "data", "sample", archivo), dtype=str, keep_default_na=False)
pdf = pdf.astype(object).where(pdf != "", None)  # vacíos -> NULL

df_raw = spark.createDataFrame(pdf, schema=StructType([StructField(col, StringType(), True) for col in pdf.columns]))
df = contratos.tipar_segun_contrato(df_raw, c)
print(f"Archivo: {archivo} — {df.count()} filas")
display(df)

# COMMAND ----------

# MAGIC %md ## 3. Quality gate: validar el DataFrame ANTES de publicar

# COMMAND ----------

paso_gate, resumen_gate = contratos.validar_dataframe(spark, c, df)
mostrar("Gate pre-publicación", paso_gate, resumen_gate)

if not paso_gate:
    filas_vigentes = spark.table(c["fqn"]).count()
    raise contratos.ContratoError(
        f"El archivo {archivo} no cumple el contrato {c['contrato']['id']}. No se publica: "
        f"{c['fqn']} conserva sus {filas_vigentes} filas vigentes. Revisa los checks fallidos arriba."
    )

# COMMAND ----------

# MAGIC %md ## 4. Carga (solo llega aquí si el gate pasó)

# COMMAND ----------

print(f"Cargadas {contratos.publicar(spark, c, df)} filas en {c['fqn']}")

# COMMAND ----------

# MAGIC %md ## 5. Validación post-carga contra la tabla física

# COMMAND ----------

paso_tabla, resumen_tabla = contratos.validar(spark, c, AMBIENTE)
mostrar(f"Tabla {c['fqn']}", paso_tabla, resumen_tabla)
if not paso_tabla:
    raise contratos.ContratoError(f"La tabla {c['fqn']} no cumple el contrato {c['contrato']['id']}.")
