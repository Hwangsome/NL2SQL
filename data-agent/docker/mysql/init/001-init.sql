CREATE DATABASE IF NOT EXISTS meta CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS dw CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON meta.* TO 'data_agent'@'%';
GRANT ALL PRIVILEGES ON dw.* TO 'data_agent'@'%';
FLUSH PRIVILEGES;

USE meta;

CREATE TABLE IF NOT EXISTS table_info (
  id VARCHAR(64) PRIMARY KEY COMMENT '表编号',
  name VARCHAR(128) NOT NULL COMMENT '表名称',
  role VARCHAR(32) NOT NULL COMMENT '表类型(fact/dim)',
  description TEXT NULL COMMENT '表描述'
);

CREATE TABLE IF NOT EXISTS column_info (
  id VARCHAR(64) PRIMARY KEY COMMENT '列编号',
  name VARCHAR(128) NOT NULL COMMENT '列名称',
  type VARCHAR(64) NOT NULL COMMENT '数据类型',
  role VARCHAR(32) NOT NULL COMMENT '列类型(primary_key,foreign_key,measure,dimension)',
  examples JSON NULL COMMENT '数据示例',
  description TEXT NULL COMMENT '列描述',
  alias JSON NULL COMMENT '列别名',
  table_id VARCHAR(64) NOT NULL COMMENT '所属表编号'
);

CREATE TABLE IF NOT EXISTS metric_info (
  id VARCHAR(64) PRIMARY KEY COMMENT '指标编码',
  name VARCHAR(128) NOT NULL COMMENT '指标名称',
  description TEXT NULL COMMENT '指标描述',
  relevant_columns JSON NULL COMMENT '关联字段',
  alias JSON NULL COMMENT '指标别名'
);

CREATE TABLE IF NOT EXISTS column_metric (
  column_id VARCHAR(64) NOT NULL COMMENT '列编号',
  metric_id VARCHAR(64) NOT NULL COMMENT '指标编号',
  PRIMARY KEY (column_id, metric_id)
);
