-- E-commerce analytics dataset. Loaded automatically on first run.

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  country    TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE products (
  id       INTEGER PRIMARY KEY,
  name     TEXT NOT NULL,
  category TEXT NOT NULL,
  price    REAL NOT NULL
);

CREATE TABLE orders (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  order_date  TEXT NOT NULL,
  status      TEXT NOT NULL
);

CREATE TABLE order_items (
  id         INTEGER PRIMARY KEY,
  order_id   INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  quantity   INTEGER NOT NULL
);

INSERT INTO customers (id, name, country, created_at) VALUES
  (1,'Alice','USA','2024-01-05'),
  (2,'Bob','USA','2024-02-11'),
  (3,'Carla','Canada','2024-02-20'),
  (4,'Dieter','Germany','2024-03-02'),
  (5,'Emi','Japan','2024-03-15'),
  (6,'Farah','UAE','2024-04-01'),
  (7,'Grace','USA','2024-04-22'),
  (8,'Hugo','France','2024-05-09');

INSERT INTO products (id, name, category, price) VALUES
  (1,'Widget','Hardware',25.00),
  (2,'Gadget','Hardware',40.00),
  (3,'Pro Plan','Subscription',100.00),
  (4,'Starter Plan','Subscription',30.00),
  (5,'Cable','Accessory',8.00),
  (6,'Case','Accessory',15.00);

INSERT INTO orders (id, customer_id, order_date, status) VALUES
  (1,1,'2024-02-03','completed'),
  (2,1,'2024-03-10','completed'),
  (3,2,'2024-03-12','completed'),
  (4,3,'2024-03-15','cancelled'),
  (5,4,'2024-04-02','completed'),
  (6,5,'2024-04-05','completed'),
  (7,2,'2024-04-18','completed'),
  (8,6,'2024-05-01','completed'),
  (9,7,'2024-05-07','completed'),
  (10,1,'2024-05-20','completed'),
  (11,8,'2024-06-02','completed'),
  (12,3,'2024-06-09','completed'),
  (13,5,'2024-06-15','cancelled'),
  (14,7,'2024-06-20','completed'),
  (15,4,'2024-06-28','completed');

INSERT INTO order_items (id, order_id, product_id, quantity) VALUES
  (1,1,1,2),(2,1,5,1),
  (3,2,3,1),
  (4,3,2,1),(5,3,6,2),
  (6,4,1,1),
  (7,5,3,1),(8,5,1,1),
  (9,6,4,2),
  (10,7,2,2),
  (11,8,1,3),(12,8,5,2),
  (13,9,3,1),
  (14,10,6,1),(15,10,5,1),
  (16,11,2,1),(17,11,1,1),
  (18,12,4,1),
  (19,13,3,1),
  (20,14,1,1),(21,14,6,1),
  (22,15,2,1);
