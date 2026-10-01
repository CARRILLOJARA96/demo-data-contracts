"""Utilidades para aplicar un contrato ODCS en Databricks, reutilizables por cualquier capa.

Convención de nombres (se valida contra el contrato):
    catálogo = <ambiente>_<capa>   (customProperty `capa`, en minúsculas)
    esquema  = el que declara el documento de alcance, tal cual. Si el contrato viene de un DED,
               debe coincidir con su SCHEMA LANDING (customProperty `schemaLanding`).
El servidor del contrato con id = <ambiente> (p. ej. `desa`, `prod`) declara ese catálogo y esquema.
"""

import re

import pandas as pd
import yaml
from datacontract.data_contract import DataContract


class ContratoError(Exception):
    """El contrato, la tabla o los datos no permiten continuar."""


def cargar_contrato(ruta, ambiente):
    """Lee el contrato y resuelve la tabla destino del ambiente. Devuelve un dict con lo necesario."""
    with open(ruta, encoding="utf-8") as f:
        contrato = yaml.safe_load(f)

    servidor = next((s for s in contrato.get("servers", []) if s["server"] == ambiente), None)
    if servidor is None or servidor.get("type") != "databricks":
        raise ContratoError(f"El contrato {contrato['id']} no declara un servidor databricks '{ambiente}'.")

    props = {p["property"]: p["value"] for p in contrato.get("customProperties", [])}
    catalogo = f"{ambiente}_{str(props.get('capa', '')).lower()}"
    if servidor.get("catalog") != catalogo:
        raise ContratoError(
            f"El servidor '{ambiente}' usa el catálogo {servidor.get('catalog')}, "
            f"pero la convención exige {catalogo} (<ambiente>_<capa>)."
        )
    if not servidor.get("schema"):
        raise ContratoError(f"El servidor '{ambiente}' no declara esquema.")
    if props.get("schemaLanding") and servidor["schema"] != props["schemaLanding"]:
        raise ContratoError(
            f"El servidor '{ambiente}' usa el esquema {servidor['schema']}, pero el documento de alcance "
            f"declara {props['schemaLanding']} (SCHEMA LANDING)."
        )

    modelo = contrato["schema"][0]
    return {
        "contrato": contrato,
        "texto": yaml.safe_dump(contrato, allow_unicode=True, sort_keys=False),
        "ambiente": ambiente,
        "modelo": modelo,
        "catalogo": servidor["catalog"],
        "esquema": servidor["schema"],
        "tabla": modelo["physicalName"],
        "fqn": f"{servidor['catalog']}.{servidor['schema']}.{modelo['physicalName']}",
    }


def _normalizar_tipo(tipo):
    return re.sub(r"\s+", "", tipo).lower()


def _sql_str(texto):
    return "'" + (texto or "").replace("\\", "\\\\").replace("'", "\\'") + "'"


def asegurar_tabla(spark, c):
    """Crea la tabla si no existe y aplica solo cambios compatibles (columnas opcionales nuevas).

    Nunca recrea ni borra: cualquier diferencia no aditiva (columna eliminada o de otro tipo)
    detiene el proceso, porque debió bloquearse en el PR con `datacontract breaking`.
    Devuelve la lista de acciones realizadas.
    """
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {c['catalogo']}.{c['esquema']}")

    if not spark.catalog.tableExists(c["fqn"]):
        # El exportador SQL del CLI (1.2.2) ignora el server del DataContract y solo lo lee de los argumentos
        # extra del export: sin `server=` usaría el primer servidor databricks del contrato (desa).
        ddl = DataContract(data_contract_str=c["texto"], server=c["ambiente"]).export(
            "sql", sql_server_type="databricks", server=c["ambiente"]
        )
        ddl = re.sub(r"CREATE\s+OR\s+REPLACE\s+TABLE", "CREATE TABLE IF NOT EXISTS", ddl.strip().rstrip(";"), count=1)
        if f"CREATE TABLE IF NOT EXISTS {c['fqn']} " not in ddl:
            raise ContratoError(f"El DDL generado no apunta a {c['fqn']}:\n{ddl[:300]}")
        spark.sql(ddl)
        return [f"tabla creada: {c['fqn']}"]

    actuales = {f.name: _normalizar_tipo(f.dataType.simpleString()) for f in spark.table(c["fqn"]).schema}
    esperadas = {p["name"]: p for p in c["modelo"]["properties"]}

    problemas = [f"columna {n} existe en la tabla pero no en el contrato" for n in actuales if n not in esperadas]
    problemas += [
        f"columna {n}: tabla={actuales[n]} contrato={_normalizar_tipo(p['physicalType'])}"
        for n, p in esperadas.items()
        if n in actuales and actuales[n] != _normalizar_tipo(p["physicalType"])
    ]
    nuevas = [p for n, p in esperadas.items() if n not in actuales]
    problemas += [f"columna nueva {p['name']} es obligatoria: no se puede agregar a una tabla existente" for p in nuevas if p.get("required")]
    if problemas:
        raise ContratoError(f"La tabla {c['fqn']} no se puede alinear con el contrato sin un cambio incompatible:\n- " + "\n- ".join(problemas))

    acciones = []
    for p in nuevas:
        spark.sql(
            f"ALTER TABLE {c['fqn']} ADD COLUMNS (`{p['name']}` {p['physicalType']} COMMENT {_sql_str(p.get('description'))})"
        )
        acciones.append(f"columna agregada: {p['name']} {p['physicalType']}")
    return acciones or ["tabla existente, sin cambios de estructura"]


def validar(spark, c, servidor):
    """Ejecuta los checks del contrato contra `servidor` (`gate` o el ambiente). Devuelve (pasó, resumen)."""
    run = DataContract(data_contract_str=c["texto"], server=servidor, spark=spark).test()
    resumen = pd.DataFrame(
        [
            {
                "resultado": str(ch.result.value if hasattr(ch.result, "value") else ch.result),
                "check": ch.name,
                "campo": ch.field,
                "detalle": ch.reason,
            }
            for ch in run.checks
        ]
    )
    return run.has_passed(), resumen


def validar_dataframe(spark, c, df):
    """Quality gate: valida un DataFrame antes de escribirlo, expuesto como vista temporal con el nombre del modelo."""
    df.createOrReplaceTempView(c["tabla"])
    try:
        return validar(spark, c, "gate")
    finally:
        spark.catalog.dropTempView(c["tabla"])  # si no, taparía a la tabla física en la validación post-carga


def tipar_segun_contrato(df_texto, c):
    """Castea un DataFrame de strings a los tipos físicos del contrato.

    TRY_CAST: un valor no convertible queda NULL. Una columna del contrato que el archivo aún no trae
    también queda NULL. En ambos casos es el gate quien decide si eso incumple el contrato.
    """
    origen = set(df_texto.columns)
    return df_texto.selectExpr(
        *[
            f"TRY_CAST(`{p['name']}` AS {p['physicalType']}) AS `{p['name']}`"
            if p["name"] in origen
            else f"CAST(NULL AS {p['physicalType']}) AS `{p['name']}`"
            for p in c["modelo"]["properties"]
        ]
    )


def publicar(spark, c, df):
    """Reemplaza el contenido de la tabla con `df`, alineando columnas por nombre (no por posición)."""
    df.select(*spark.table(c["fqn"]).columns).write.insertInto(c["fqn"], overwrite=True)
    return spark.table(c["fqn"]).count()
