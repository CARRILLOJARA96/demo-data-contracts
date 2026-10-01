-- Data Contract: landing_dataentry_int_de_maestro_canal
-- SQL Dialect: databricks
CREATE OR REPLACE TABLE desa_landing.dataentry_int.de_maestro_canal (
  cod_intermediario STRING not null primary key COMMENT "Código del intermediario (corredor o agente) que comercializa los productos.",
  cod_canal_venta STRING not null COMMENT "Código del canal de venta.",
  des_canal_venta STRING not null COMMENT "Descripción del canal de venta.",
  nom_canal_distribucion STRING not null COMMENT "Canal de distribución al que pertenece el canal de venta.",
  nom_grupo_canal STRING not null COMMENT "Agrupación de canales usada en los reportes comerciales.",
  nom_grupo_venta STRING not null COMMENT "Grupo comercial responsable del canal.",
  cod_grupo_venta STRING not null COMMENT "Código del grupo comercial.",
  nbrusuariode STRING not null COMMENT "Nombre del usuario que realizó la carga del archivo",
  tipingresode STRING not null COMMENT "Tipo de ingreso del registro: Masivo (M) o Individual (I), según el origen del proceso.",
  fecrutina DATE not null COMMENT "Fecha en que se ejecutó el proceso de carga hacia la capa Landing.",
  fecactualizacionregistro TIMESTAMP not null COMMENT "Fecha y hora en que se insertó o actualizó el registro en el data entry.",
  fecdia DATE not null COMMENT "Fecha de generación del registro en la fuente de usuario."
) COMMENT "Maestro de canales de venta e intermediarios, mantenido por el área comercial vía data entry.";