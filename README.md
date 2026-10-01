# Demo · Data Contracts para Landing DED

Demo de punta a punta de **data contracts** con herramientas open source sobre el flujo
**Data Entry de Landing (DED)**: el documento de alcance en Excel se convierte en un contrato
[ODCS v3.2](https://bitol-io.github.io/open-data-contract-standard/), y de ese contrato salen el
DDL, la documentación, los controles de CI y la validación de datos en Databricks.

> Todos los documentos y datos del repo son **sintéticos**: sin nombres de personas, sistemas internos,
> logos, etiquetas de sensibilidad ni datos reales. **Nunca subir documentos reales** (ver *Notas*).

## El flujo

```
 Gobierno + Modelamiento        Conversión                  CI (GitHub Actions)              Ingeniería (Databricks)
 ───────────────────────        ──────────                  ───────────────────              ───────────────────────
 Documento de alcance      ──▶  DED → ded_a_contrato.py ──▶  1. Alcance ↔ contrato sincr. ──▶  Estructura desde el contrato
 (Excel)                        ODCS → datacontract import  2. Lint ODCS                     Gate: valida el DataFrame
  + complemento .contrato.yaml  (falla con errores          3. Breaking changes vs main      Carga solo si pasa
    (versión, servidores,        legibles: hoja, fila, rol) 4. Test de humo con muestra      Validación post-carga
     reglas de negocio)                                      5. DDL + HTML como artefactos
```

- **El documento de alcance es la fuente de verdad.** El YAML en `contracts/` es generado y **no se edita a mano**:
  CI lo regenera y falla si no coincide.
- `scripts/excel_a_contrato.sh` reconoce **dos formatos** de documento de alcance:

| Formato | Cómo se reconoce | Conversión | Ejemplo en el repo |
|---|---|---|---|
| **DED de gobierno** | tiene la hoja `DED` | `scripts/ded_a_contrato.py` (+ complemento) | `de_maestro_canal` |
| **Plantilla Excel ODCS** | cualquier otro Excel | `datacontract import excel` | `ded_tarifario_prestacion` |

## Estructura

| Ruta | Qué es |
|---|---|
| `alcance/landing_ded/de_maestro_canal.xlsx` | **DED** en el formato de gobierno (sintético). |
| `alcance/landing_ded/de_maestro_canal.contrato.yaml` | Complemento del DED: versión, tenant, servidores, reglas de negocio. |
| `alcance/landing_ded/ded_tarifario_prestacion.xlsx` | Documento de alcance en la plantilla Excel ODCS. |
| `contracts/landing_ded/*.odcs.yaml` | Contratos ODCS **generados**. No editar. |
| `generated/` | DDL Databricks y documentación HTML generados desde cada contrato. |
| `data/sample/` | Datos de muestra por tabla: `_ok.csv` (cumple) y `_errores.csv` (violaciones sembradas). |
| `scripts/ded_a_contrato.py` | **Conversor DED → ODCS** con validación estricta. |
| `scripts/` (resto) | Conversión de todos los documentos, artefactos, breaking changes, demo local. |
| `databricks/contratos.py` | Módulo reutilizable: resolver la tabla del ambiente, DDL no destructivo, gate, carga. |
| `databricks/aplicar_contrato.py` | **Notebook genérico**: aplica cualquier contrato (estructura → gate → carga → validación post-carga). |
| `databricks/demo_data_contract_ded.py` | Notebook de ejemplo fijo para tarifario (widgets `ambiente` y `escenario`). |
| `.github/workflows/data-contracts.yml` | Pipeline de CI para cada PR. |

## Qué toma el conversor del DED

**Hoja `Informacion - tabla`** (una fila por tabla):

| Columna del DED | En el contrato |
|---|---|
| NOMBRE DE TABLA/ ARCHIVO LANDING *(Data Modeler)* | nombre y nombre físico de la tabla |
| SCHEMA LANDING/ ARCHIVO | `schemaLanding` y esquema de los servidores Databricks (tal cual) |
| Dominio / Subdominio | `domain` |
| DESCRIPCIÓN DE LA TABLA LANDING | descripción |
| Empresa, Tipo de fuente, Tipo de carga, Frecuencia, Historia, Rutas, PO, Squad | `customProperties` |

**Hoja `DED`** (una fila por campo, tabla de Excel `Tabla14`):

| Columna del DED | En el contrato |
|---|---|
| Nombre Campo Modelado *(Data Modeler)* | `name` de la columna |
| Nombre Campo | `businessName` |
| Formato Landing (+ Longitud Landing) | tipo: `String→STRING`, `Decimal`+`12,2`→`DECIMAL(12,2)`, `Date`, `Time_Stamp`, `Boolean` |
| Longitud del campo Landing (texto) | `maxLength` |
| ¿Es una llave primaria? | `primaryKey` (+ check automático de duplicados) |
| ¿El campo contiene nulos? = NO | `required: true` |
| Catálogo / Dominio de valores | regla de valores permitidos |
| ¿Es un Dato DAC? = SI | `tags: [dac]` y clasificación mínima `restricted` |
| Nivel de clasificación del Dato | `classification` (public / internal / restricted) |
| ¿Campo descartado? = SI | **se excluye** del contrato |
| Fuente, Criticidad, Sustento, Tipo de Formato, … | `customProperties` de la columna |

El **complemento** (`<nombre>.contrato.yaml`) guarda solo lo que el DED no tiene dónde expresar: `version`,
`status`, `tenant`, `dataProduct`, `servers`, reglas de negocio a nivel tabla (`quality`) y `slaProperties`.

### Validación estricta del DED

Si el DED está incompleto o tiene valores fuera de las listas, el conversor **no genera nada** y lista todos
los errores con hoja, fila y el **rol responsable** que figura en la propia plantilla:

```
❌ El DED 'de_con_errores.xlsx' tiene 5 error(es). Corrígelos y vuelve a ejecutar:
   • 'Informacion - tabla' fila 8: 'Dominio / Subdominio' = 'Canales' no está en la lista de valores (responsable: Custodio Técnico / Data Steward)
   • 'DED' fila 12 (COD_CANAL_VENTA): 'Nombre Campo Modelado' = 'Cod Canal Venta' debe ser snake_case en minúsculas, sin espacios ni tildes (responsable: DATA MODELER)
   • 'DED' fila 13 (DES_CANAL_VENTA): falta 'Definición del campo' (responsable: DATA GOVERNANCE)
   ...
```

## Ambientes y nombres en Databricks

Cada contrato declara un servidor Databricks por ambiente (`desa`, `prod`):

- **Catálogo** = `<ambiente>_<capa>` (p. ej. `desa_landing`).
- **Esquema** = el que declara el documento de alcance, **tal cual** (en un DED, su SCHEMA LANDING).

| Contrato | `desa` | `prod` |
|---|---|---|
| `de_maestro_canal` | `desa_landing.dataentry_int.de_maestro_canal` | `prod_landing.dataentry_int.de_maestro_canal` |
| `ded_tarifario_prestacion` | `desa_landing.prestaciones_tarifarios.ded_tarifario_prestacion` | `prod_landing.prestaciones_tarifarios.ded_tarifario_prestacion` |

`databricks/contratos.py` valida esa convención antes de desplegar.

---

## 1 · Probarlo en tu máquina

Requiere Python 3.10–3.12. En Windows usa Git Bash.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt
export PYTHONUTF8=1                # Windows: la salida usa emojis y tildes
chmod +x scripts/*.sh
scripts/demo_local.sh
```

Recorre 7 pasos con el DED `de_maestro_canal`: documentos de alcance → contratos, DED mal llenado (❌ con
errores legibles), DDL/HTML, datos correctos (🟢), datos con errores (🔴), cambio compatible (pasa) y cambio
que rompe (se bloquea).

Convertir un DED puntual:

```bash
python scripts/ded_a_contrato.py alcance/landing_ded/de_maestro_canal.xlsx
```

## 2 · Flujo de trabajo y CI

1. Gobierno y modelamiento llenan el documento de alcance y lo guardan en `alcance/<flujo>/`.
2. `scripts/excel_a_contrato.sh` genera los contratos (o muestra qué corregir).
3. Se sube documento + contrato en un PR. CI valida todo y bloquea si hay cambios incompatibles.

Para agregar un DED nuevo: copia el Excel a `alcance/landing_ded/` y crea su `<nombre>.contrato.yaml`
tomando el existente como ejemplo (sin complemento, el contrato sale con versión `1.0.0` y sin servidores).

El workflow corre en cada PR (y en cada push a `main` que toque `alcance/` o `contracts/`). Para verlo funcionar:
cambia algo en el DED (ej. marca un campo como descartado), ejecuta `scripts/excel_a_contrato.sh` y abre el PR.
Quitar un campo es un cambio incompatible y el paso 3 falla. Si subes el Excel sin regenerar el contrato, falla el paso 1.

Para exigirlo, activa en *Settings → Rules* una regla sobre `main` que requiera el check **Validar contratos de datos**.

## 3 · Ejecutarlo en Databricks

Probado en **Databricks Free Edition** (serverless).

1. **Catálogos**: crea uno por ambiente y capa, p. ej. en el SQL Editor:
   `CREATE CATALOG IF NOT EXISTS desa_landing;` (y `prod_landing` para producción). El esquema lo crea el notebook.
2. **Clonar el repo** en el workspace: *Workspace → Create → Git folder* → URL HTTPS de tu repo.
3. **Cómputo**: serverless (o un cluster con Databricks Runtime 15.4 LTS o superior), con acceso a PyPI.
4. **Abrir** `databricks/aplicar_contrato`, completar los widgets y **Run all**:
   - `contrato`: ruta del contrato, p. ej. `contracts/landing_ded/de_maestro_canal.odcs.yaml`.
   - `ambiente`: `desa` o `prod` (servidor del contrato).
   - `archivo`: CSV de entrada, p. ej. `data/sample/de_maestro_canal_ok.csv` o `..._errores.csv`.

Los mismos parámetros sirven como `base_parameters` de un Job.

| Contrato · archivo | Qué pasa |
|---|---|
| `de_maestro_canal` · `_ok.csv` | Crea `desa_landing.dataentry_int.de_maestro_canal` si no existe, el gate pasa (40 checks), carga 8 filas y la validación post-carga pasa. |
| `de_maestro_canal` · `_errores.csv` | El gate falla con 5 checks (PK duplicada, 2 nulos, valor fuera de catálogo, canal con dos descripciones) y se detiene **antes de escribir**: la tabla conserva sus filas. |
| `ded_tarifario_prestacion` · `_ok.csv` | Gate 39/39, carga 8 filas en `desa_landing.prestaciones_tarifarios.ded_tarifario_prestacion`. |

La estructura de la tabla nunca se recrea. Si el contrato agrega una columna **opcional**, se aplica con
`ALTER TABLE ADD COLUMNS`. Cualquier otra diferencia (columna eliminada, tipo distinto, columna nueva obligatoria)
detiene el proceso: son cambios incompatibles que el CI ya bloquea en el PR.

---

## Notas y límites

- **Nunca subir documentos de alcance reales al repo.** Las carpetas `privado/` y `doc-privado/` están en
  `.gitignore` para probar con ellos localmente.
- El conversor DED está probado con la **versión 3** de la plantilla (lee la versión de `Historial de versiones`
  y avisa si es otra). Si la plantilla cambia de columnas, falla indicando cuáles no encuentra. Solo cubre
  **Landing DED**: landing core, trusted (Data Vault) y enriched tienen plantillas distintas.
- La lista de empresas válidas del conversor es de demostración (`demo`, `corp`).
- **Unity Catalog es necesario** para la llave primaria del DDL (en UC es informativa, no bloquea duplicados;
  por eso el contrato también la valida como regla de calidad).
- En serverless (entorno por defecto con pandas 1.5) el notebook instala también `pandas>=2.2,<3`: el motor de
  validación del CLI (ibis 12) lo necesita. Sin eso, los checks de datos fallan con `OptionError: No such option`.
- Versión fijada: `datacontract-cli==1.2.2`, ODCS `v3.2.0`.

## Licencias

Data Contract CLI, Data Contract Editor y la plantilla Excel ODCS: **MIT**. Open Data Contract Standard: **Apache 2.0**.
