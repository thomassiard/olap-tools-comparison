CREATE DATABASE IF NOT EXISTS instacart;

CREATE TABLE IF NOT EXISTS instacart.aisles
(
    aisle_id UInt32,
    aisle String
) ENGINE = MergeTree() ORDER BY aisle_id;

CREATE TABLE IF NOT EXISTS instacart.departments
(
    department_id UInt32,
    department String
) ENGINE = MergeTree() ORDER BY department_id;

CREATE TABLE IF NOT EXISTS instacart.products
(
    product_id UInt32,
    product_name String,
    aisle_id UInt32,
    department_id UInt32
) ENGINE = MergeTree() ORDER BY product_id;

CREATE TABLE IF NOT EXISTS instacart.orders
(
    order_id UInt32,
    user_id UInt32,
    eval_set String,
    order_number UInt16,
    order_dow UInt8,
    order_hour_of_day UInt8,
    days_since_prior_order Nullable(Float32)
) ENGINE = MergeTree() ORDER BY order_id;

CREATE TABLE IF NOT EXISTS instacart.order_products_prior
(
    order_id UInt32,
    product_id UInt32,
    add_to_cart_order UInt16,
    reordered UInt8
) ENGINE = MergeTree() ORDER BY (order_id, product_id);

CREATE TABLE IF NOT EXISTS instacart.order_products_train
(
    order_id UInt32,
    product_id UInt32,
    add_to_cart_order UInt16,
    reordered UInt8
) ENGINE = MergeTree() ORDER BY (order_id, product_id);

INSERT INTO instacart.aisles FROM INFILE '/data/aisles.csv' FORMAT CSVWithNames;
INSERT INTO instacart.departments FROM INFILE '/data/departments.csv' FORMAT CSVWithNames;
INSERT INTO instacart.products FROM INFILE '/data/products.csv' FORMAT CSVWithNames;
INSERT INTO instacart.orders FROM INFILE '/data/orders.csv' FORMAT CSVWithNames;
INSERT INTO instacart.order_products_prior FROM INFILE '/data/order_products__prior.csv' FORMAT CSVWithNames;
INSERT INTO instacart.order_products_train FROM INFILE '/data/order_products__train.csv' FORMAT CSVWithNames;
