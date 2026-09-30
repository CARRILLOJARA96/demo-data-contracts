-- Data Contract: landing_ded_tarifario_prestacion
-- SQL Dialect: databricks
CREATE OR REPLACE TABLE desa_landing.tarifarios.ded_tarifario_prestacion (
  cod_clinica STRING not null COMMENT "Código interno de la clínica (formato CL + 3 dígitos).",
  nom_clinica STRING not null COMMENT "Nombre comercial de la clínica.",
  cod_prestacion STRING not null COMMENT "Código de la prestación médica según catálogo interno.",
  des_prestacion STRING not null COMMENT "Descripción de la prestación.",
  cod_moneda STRING not null COMMENT "Moneda de la tarifa (ISO 4217).",
  mto_tarifa DECIMAL(12,2) not null COMMENT "Monto negociado de la tarifa, sin IGV.",
  fec_inicio_vigencia DATE not null COMMENT "Fecha desde la que rige la tarifa.",
  fec_fin_vigencia DATE COMMENT "Fecha hasta la que rige la tarifa. Vacío = vigente.",
  flg_activo BOOLEAN not null COMMENT "Indica si la tarifa está activa.",
  usr_registro STRING not null COMMENT "Usuario del área que ingresó el registro en el DED.",
  CONSTRAINT pk_ded_tarifario_prestacion PRIMARY KEY (cod_clinica, cod_prestacion, fec_inicio_vigencia)
) COMMENT "Tarifas por clínica y prestación con su periodo de vigencia.";