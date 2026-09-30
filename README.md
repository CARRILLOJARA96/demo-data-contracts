# Demo · Data Contracts para Landing DED

Demo de punta a punta de **data contracts** con herramientas open source sobre un flujo
**Data Entry de Landing (DED)**: el documento de alcance en Excel se convierte en un contrato
[ODCS v3.2](https://bitol-io.github.io/open-data-contract-standard/), y de ese contrato salen el
DDL, la documentación, los controles de CI y la validación de datos en Databricks.

> Todos los datos son **sintéticos** (tarifario de prestaciones por clínica). No hay datos de pacientes.

## El flujo

```
 Gobierno              Modelamiento            CI (GitHub Actions)              Ingeniería (Databricks)
 ─────────             ────────────            ──────────────────               ───────────────────────
 Excel de alcance ──▶  tipos, llaves,  ──▶  1. Excel ↔ YAML sincronizados  ──▶  DDL desde el contrato
 (plantilla ODCS)      descripciones        2. Lint ODCS                        Gate: valida el DataFrame
                       (en el mismo Excel)  3. Breaking changes vs main          Carga solo si pasa
                                            4. Test de humo con muestra         Validación post-carga
                                            5. DDL + HTML como artefactos
```

La **fuente de verdad es el Excel** (`alcance/`). El YAML (`contracts/`) se genera siempre con
`scripts/excel_a_contrato.sh` y CI falla si alguien sube uno sin el otro.

## Estructura

| Ruta | Qué es |
|---|---|
| `alcance/landing_ded/ded_tarifario_prestacion.xlsx` | Documento de alcance DED (plantilla Excel ODCS). Lo edita gobierno/modelamiento. |
| `contracts/landing_ded/ded_tarifario_prestacion.odcs.yaml` | Contrato ODCS generado desde el Excel. **No editar a mano.** |
| `generated/` | DDL Databricks y documentación HTML generados desde el contrato. |
| `data/sample/` | Datos de muestra: `_ok.csv` (cumple) y `_errores.csv` (8 violaciones sembradas). |
| `databricks/demo_data_contract_ded.py` | Notebook: estructura → gate → carga → validación post-carga. |
| `databricks/contratos.py` | Módulo reutilizable: resolver la tabla del ambiente, DDL no destructivo, gate, carga. |
| `scripts/` | Conversión Excel→YAML, generación de artefactos, chequeo de breaking changes, demo local. |
| `.github/workflows/data-contracts.yml` | Pipeline de CI para cada PR. |

## Qué define el contrato

- **Esquema**: 10 columnas con tipo lógico y físico, obligatoriedad, clasificación y descripción.
- **Llave primaria** compuesta: `cod_clinica + cod_prestacion + fec_inicio_vigencia` (el CLI genera solo el check de duplicados).
- **Reglas de calidad**: patrón `^CL[0-9]{3}$` en clínica, largo 6 en prestación, moneda ∈ {PEN, USD},
  tarifa > 0, fin de vigencia ≥ inicio, tabla no vacía.
- **Propiedades propias del framework** (`customProperties`): `capa`, `flujo`, `subdominio`, `frecuenciaCarga`.
- **Servidores**: `local` (CSV + DuckDB), `gate` (DataFrame de Spark) y un servidor Databricks por ambiente:
  `desa` → `desa_landing.tarifarios` y `prod` → `prod_landing.tarifarios`.
  Convención: catálogo `<ambiente>_<capa>`, esquema `<subdominio>` (se valida al desplegar).

---

## 1 · Probarlo en tu máquina (5 min)

Requiere Python 3.10–3.12.

```bash
pip install -r requirements.txt
chmod +x scripts/*.sh
scripts/demo_local.sh
```

Recorre los 6 pasos: Excel→YAML, DDL/HTML, test con datos buenos (🟢), test con datos malos (🔴),
cambio compatible (pasa) y cambio que rompe (se bloquea).

Para abrir el contrato en el editor visual:

```bash
npx datacontract-editor contracts/landing_ded/ded_tarifario_prestacion.odcs.yaml
# o con Docker: docker run -d -p 4173:4173 datacontract/editor  →  http://localhost:4173
```

## 2 · Subirlo a tu GitHub

```bash
git init -b main
git add -A
git commit -m "Demo data contracts DED"
git remote add origin git@github.com:<tu-usuario>/demo-data-contracts.git
git push -u origin main
```

El workflow corre en cada PR (y en cada push a `main` que toque `alcance/` o `contracts/`).
Para verlo funcionar:

- **PR compatible**: abre el Excel, agrega una fila opcional en la hoja `Schema ded_tarifario_prestacion`,
  sube la versión a `1.1.0` en `Fundamentals`, ejecuta `scripts/excel_a_contrato.sh` y crea el PR.
  → pasos 1–3 en verde. El paso 4 fallará hasta que los datos de muestra traigan la nueva columna
  (es lo esperado: el contrato promete una columna que el productor aún no entrega).
- **PR que rompe**: elimina la fila `usr_registro` del Excel, regenera y crea el PR.
  → el paso 3 falla con una anotación en el archivo y el resumen del job muestra el changelog.
- **Olvido de sincronizar**: sube solo el Excel sin regenerar el YAML → el paso 1 falla.

Para exigirlo, activa en *Settings → Branches* una regla sobre `main` que requiera el check
**Validar contratos de datos**.

## 3 · Ejecutarlo en Databricks

Probado en **Databricks Free Edition** (serverless).

1. **Catálogos**: crea uno por ambiente y capa (convención `<ambiente>_<capa>`), p. ej. en el SQL Editor:
   `CREATE CATALOG IF NOT EXISTS desa_landing;` (y `prod_landing` para producción). El esquema lo crea el notebook.
2. **Clonar el repo** en el workspace: *Workspace → Create → Git folder* → URL HTTPS de tu repo.
3. **Cómputo**: serverless (o un cluster con Databricks Runtime 15.4 LTS o superior), con acceso a PyPI.
4. **Abrir** `databricks/demo_data_contract_ded`, elegir los widgets y **Run all**:
   - `ambiente`: `desa` o `prod` (servidor del contrato → tabla `<ambiente>_landing.tarifarios.ded_tarifario_prestacion`).
   - `escenario`: `ok` o `errores`.

| Escenario | Qué pasa |
|---|---|
| `ok` | Crea la tabla si no existe (o agrega columnas opcionales nuevas del contrato), el gate pasa (39 checks), carga 8 filas y la validación post-carga pasa. |
| `errores` | El gate falla con 8 checks en rojo y el notebook se detiene **antes de escribir**: la tabla conserva sus datos vigentes. |

La estructura de la tabla nunca se recrea. Si el contrato agrega una columna **opcional**, se aplica con
`ALTER TABLE ADD COLUMNS`. Cualquier otra diferencia (columna eliminada, tipo distinto, columna nueva obligatoria)
detiene el proceso: son cambios incompatibles que el CI ya bloquea en el PR.

Para usarlo en un Job, basta con programar el notebook: si el contrato no se cumple, la tarea falla.

---

## Notas y límites de la demo

- **Unity Catalog es necesario** para la llave primaria del DDL (en UC es informativa, no bloquea duplicados;
  por eso el contrato también la valida como regla de calidad). En `hive_metastore` hay que quitar la línea `CONSTRAINT`.
- En serverless (entorno por defecto con pandas 1.5) el notebook instala también `pandas>=2.2,<3`: el motor de
  validación del CLI (ibis 12) lo necesita. Sin eso, los checks de datos fallan con `OptionError: No such option`.
- La conversión Excel↔YAML es **determinística y sin pérdidas** (verificado): el Excel puede ir y volver.
- La plantilla usada es la **oficial de ODCS**, no el documento de alcance DED real de la empresa. El siguiente paso
  sería mapear ese documento a esta plantilla o escribir un conversor propio.
- Versión fijada: `datacontract-cli==1.2.2`, ODCS `v3.2.0`.

## Licencias

Data Contract CLI, Data Contract Editor y la plantilla Excel: **MIT**. Open Data Contract Standard: **Apache 2.0**.
