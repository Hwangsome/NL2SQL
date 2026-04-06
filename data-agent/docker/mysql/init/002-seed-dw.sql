USE dw;
SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS dim_region (
  region_id INT PRIMARY KEY,
  province VARCHAR(64) NOT NULL,
  region_name VARCHAR(64) NOT NULL,
  country VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_customer (
  customer_id INT PRIMARY KEY,
  customer_name VARCHAR(64) NOT NULL,
  gender VARCHAR(16) NOT NULL,
  member_level VARCHAR(32) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_product (
  product_id INT PRIMARY KEY,
  product_name VARCHAR(128) NOT NULL,
  category VARCHAR(64) NOT NULL,
  brand VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_date (
  date_id INT PRIMARY KEY,
  year INT NOT NULL,
  quarter VARCHAR(8) NOT NULL,
  month INT NOT NULL,
  day INT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_order (
  order_id INT PRIMARY KEY,
  customer_id INT NOT NULL,
  product_id INT NOT NULL,
  date_id INT NOT NULL,
  region_id INT NOT NULL,
  order_quantity INT NOT NULL,
  order_amount DECIMAL(12, 2) NOT NULL
);

INSERT INTO dim_region (region_id, province, region_name, country) VALUES
  (1, '北京', '华北', '中国'),
  (2, '上海', '华东', '中国'),
  (3, '广东', '华南', '中国'),
  (4, '四川', '西南', '中国')
ON DUPLICATE KEY UPDATE province = VALUES(province);

INSERT INTO dim_customer (customer_id, customer_name, gender, member_level) VALUES
  (1001, '张三', '男', '黄金'),
  (1002, '李四', '女', '白银'),
  (1003, '王五', '男', '钻石'),
  (1004, '赵六', '女', '黄金')
ON DUPLICATE KEY UPDATE customer_name = VALUES(customer_name);

INSERT INTO dim_product (product_id, product_name, category, brand) VALUES
  (2001, 'MateBook X', '笔记本', '华为'),
  (2002, 'iPhone 15', '手机', '苹果'),
  (2003, '小米电视 S', '电视', '小米'),
  (2004, 'AirPods Pro', '耳机', '苹果')
ON DUPLICATE KEY UPDATE product_name = VALUES(product_name);

INSERT INTO dim_date (date_id, year, quarter, month, day) VALUES
  (20240115, 2024, 'Q1', 1, 15),
  (20240308, 2024, 'Q1', 3, 8),
  (20240618, 2024, 'Q2', 6, 18),
  (20240909, 2024, 'Q3', 9, 9),
  (20241211, 2024, 'Q4', 12, 11),
  (20250105, 2025, 'Q1', 1, 5),
  (20250214, 2025, 'Q1', 2, 14),
  (20250320, 2025, 'Q1', 3, 20)
ON DUPLICATE KEY UPDATE year = VALUES(year);

INSERT INTO fact_order (order_id, customer_id, product_id, date_id, region_id, order_quantity, order_amount) VALUES
  (1, 1001, 2001, 20240115, 1, 1, 8999.00),
  (2, 1002, 2002, 20240308, 2, 1, 5999.00),
  (3, 1003, 2003, 20240618, 3, 2, 6998.00),
  (4, 1004, 2004, 20240909, 4, 3, 5997.00),
  (5, 1001, 2002, 20241211, 1, 1, 6299.00),
  (6, 1002, 2001, 20250105, 2, 1, 9199.00),
  (7, 1003, 2004, 20250214, 3, 2, 3998.00),
  (8, 1004, 2003, 20250320, 1, 1, 3599.00),
  (9, 1001, 2003, 20250320, 3, 1, 3499.00),
  (10, 1002, 2004, 20250214, 2, 1, 1999.00)
ON DUPLICATE KEY UPDATE order_amount = VALUES(order_amount);
