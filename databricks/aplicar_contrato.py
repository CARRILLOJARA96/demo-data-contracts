# Databricks notebook source
# MAGIC %md
# MAGIC # Aplicar un data contract
# MAGIC
# MAGIC Notebook **genérico**: sirve para cualquier contrato del repo. Todo sale del contrato ODCS:
# MAGIC
# MAGIC 1. **Tabla destino** → `<ambiente>_<capa>.<esquema del documento de alcance>.<tabla>`, validada contra la convención.
# MAGIC 2. **Estructura** → crea la tabla si no existe; si existe, solo agrega columnas opcionales nuevas.
# MAGIC    Nunca la recrea: una carga fallida no borra los datos vigentes.
# MAGIC 3. **Quality gate** → valida el archivo *antes* de escribir. Si falla, no se publica nada.
# MAGIC 4. **Carga** → reemplaza el contenido de la tabla solo si el gate pasó.
# MAGIC 5. **Validación post-carga** → vuelve a validar el contrato contra la tabla física.
# MAGIC
# MAGIC Parámetros (widgets o `base_parameters` de un job), con rutas relativas a la raíz del repo:
# MAGIC - **contrato**: p. ej. `contracts/landing_ded/de_maestro_canal.odcs.yaml`
# MAGIC - **ambiente**: `desa` o `prod` (servidor del contrato)
# MAGIC - **archivo**: CSV de entrada, p. ej. `data/sample/de_maestro_canal_ok.csv`
# MAGIC
# MAGIC > Datos 100% sintéticos. Requiere que el repo esté en el workspace (Git folder o bundle).

# COMMAND ----------

# MAGIC %pip install -q "datacontract-cli[databricks]==1.2.2" "pandas>=2.2,<3"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("contrato", "contracts/landing_ded/de_maestro_canal.odcs.yaml", "Contrato")
dbutils.widgets.dropdown("ambiente", "desa", ["desa", "prod"], "Ambiente")
dbutils.widgets.text("archivo", "data/sample/de_maestro_canal_ok.csv", "Archivo de entrada")

CONTRATO = dbutils.widgets.get("contrato")
AMBIENTE = dbutils.widgets.get("ambiente")
ARCHIVO = dbutils.widgets.get("archivo")

# COMMAND ----------

# MAGIC %md ## 1. Leer el contrato y resolver la tabla destino

# COMMAND ----------

import os

import pandas as pd
from pyspark.sql.types import StringType, StructField, StructType

import contratos  # databricks/contratos.py, junto a este notebook

# El notebook vive en <repo>/databricks/; las rutas de los parámetros son relativas a <repo>
REPO_ROOT = os.path.abspath(os.path.join(os.getcwd(), ".."))
c = contratos.cargar_contrato(os.path.join(REPO_ROOT, CONTRATO), AMBIENTE)
print(f"Contrato: {c['contrato']['id']} v{c['contrato']['version']} ({c['contrato']['status']})")
print(f"Ambiente: {AMBIENTE} | archivo: {ARCHIVO} | tabla destino: {c['fqn']}")


def mostrar(titulo, paso, resumen):
    fallidos = resumen[resumen["resultado"] != "passed"]
    print(f"{titulo}: {'🟢 CUMPLE' if paso else '🔴 NO CUMPLE'} — {len(resumen)} checks, {len(fallidos)} fallidos")
    display(fallidos if len(fallidos) else resumen)

# COMMAND ----------

# MAGIC %md ## 2. Estructura de la tabla desde el contrato (idempotente, no destructiva)

# COMMAND ----------

for accion in contratos.asegurar_tabla(spark, c):
    print(accion)

# COMMAND ----------

# MAGIC %md ## 3. Leer el archivo y tipar según el contrato

# COMMAND ----------

pdf = pd.read_csv(os.path.join(REPO_ROOT, ARCHIVO), dtype=str, keep_default_na=False)
pdf = pdf.astype(object).where(pdf != "", None)  # vacíos -> NULL

df_raw = spark.createDataFrame(pdf, schema=StructType([StructField(col, StringType(), True) for col in pdf.columns]))
df = contratos.tipar_segun_contrato(df_raw, c)
print(f"Archivo: {ARCHIVO} — {df.count()} filas")
display(df)

# COMMAND ----------

# MAGIC %md ## 4. Quality gate: validar ANTES de publicar

# COMMAND ----------

paso_gate, resumen_gate = contratos.validar_dataframe(spark, c, df)
mostrar("Gate pre-publicación", paso_gate, resumen_gate)

if not paso_gate:
    filas_vigentes = spark.table(c["fqn"]).count()
    raise contratos.ContratoError(
        f"El archivo {ARCHIVO} no cumple el contrato {c['contrato']['id']}. No se publica: "
        f"{c['fqn']} conserva sus {filas_vigentes} filas vigentes. Revisa los checks fallidos arriba."
    )

# COMMAND ----------

# MAGIC %md ## 5. Carga (solo llega aquí si el gate pasó)

# COMMAND ----------

print(f"Cargadas {contratos.publicar(spark, c, df)} filas en {c['fqn']}")

# COMMAND ----------

# MAGIC %md ## 6. Validación post-carga contra la tabla física

# COMMAND ----------

paso_tabla, resumen_tabla = contratos.validar(spark, c, AMBIENTE)
mostrar(f"Tabla {c['fqn']}", paso_tabla, resumen_tabla)
if not paso_tabla:
    raise contratos.ContratoError(f"La tabla {c['fqn']} no cumple el contrato {c['contrato']['id']}.")
