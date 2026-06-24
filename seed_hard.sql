-- Larger analytics dataset.
-- Load with: DB_FILE=shop_hard.db SEED_FILE=seed_hard.sql uv run uvicorn app.main:app

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS refunds;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS addresses;
DROP TABLE IF EXISTS subscription_events;
DROP TABLE IF EXISTS subscriptions;
DROP TABLE IF EXISTS plans;
DROP TABLE IF EXISTS usage_events;
DROP TABLE IF EXISTS support_tickets;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS product_categories;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS countries;
DROP TABLE IF EXISTS fx_rates;
DROP TABLE IF EXISTS revenue_daily;
DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS api_keys;
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS webhooks;
DROP TABLE IF EXISTS feature_flags;

CREATE TABLE countries (
  code   TEXT PRIMARY KEY,
  name   TEXT NOT NULL,
  region TEXT NOT NULL
);

CREATE TABLE fx_rates (
  currency    TEXT PRIMARY KEY,
  rate_to_usd REAL NOT NULL,
  as_of       TEXT NOT NULL
);

CREATE TABLE product_categories (
  id        INTEGER PRIMARY KEY,
  name      TEXT NOT NULL,
  parent_id INTEGER REFERENCES product_categories(id)
);

CREATE TABLE customers (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  country     TEXT REFERENCES countries(code),
  created_at  TEXT NOT NULL,
  deleted_at  TEXT
);

CREATE TABLE addresses (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  kind        TEXT NOT NULL,
  country     TEXT REFERENCES countries(code)
);

CREATE TABLE products (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,
  category    TEXT NOT NULL,
  list_price  REAL NOT NULL,
  currency    TEXT NOT NULL
);

CREATE TABLE orders (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  ordered_at  TEXT NOT NULL,
  status      TEXT NOT NULL,
  currency    TEXT NOT NULL REFERENCES fx_rates(currency)
);

CREATE TABLE order_items (
  id          INTEGER PRIMARY KEY,
  order_id    INTEGER NOT NULL REFERENCES orders(id),
  product_id  INTEGER NOT NULL REFERENCES products(id),
  quantity    INTEGER NOT NULL,
  unit_price  REAL NOT NULL
);

CREATE TABLE refunds (
  id          INTEGER PRIMARY KEY,
  order_id    INTEGER NOT NULL REFERENCES orders(id),
  amount      REAL NOT NULL,
  refunded_at TEXT NOT NULL
);

CREATE TABLE payments (
  id          INTEGER PRIMARY KEY,
  order_id    INTEGER NOT NULL REFERENCES orders(id),
  amount      REAL NOT NULL,
  method      TEXT NOT NULL,
  paid_at     TEXT NOT NULL
);

CREATE TABLE plans (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  monthly_price REAL NOT NULL,
  currency      TEXT NOT NULL
);

CREATE TABLE subscriptions (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  plan_id     INTEGER NOT NULL REFERENCES plans(id),
  started_at  TEXT NOT NULL,
  ended_at    TEXT,
  status      TEXT NOT NULL
);

CREATE TABLE subscription_events (
  id              INTEGER PRIMARY KEY,
  subscription_id INTEGER NOT NULL REFERENCES subscriptions(id),
  event_type      TEXT NOT NULL,
  event_at        TEXT NOT NULL
);

CREATE TABLE usage_events (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  metric      TEXT NOT NULL,
  quantity    INTEGER NOT NULL,
  occurred_at TEXT NOT NULL
);

CREATE TABLE support_tickets (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  opened_at   TEXT NOT NULL,
  closed_at   TEXT,
  priority    TEXT NOT NULL,
  status      TEXT NOT NULL
);

CREATE TABLE revenue_daily (
  day           TEXT PRIMARY KEY,
  gross_revenue REAL NOT NULL
);

CREATE TABLE employees (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  team       TEXT NOT NULL,
  manager_id INTEGER REFERENCES employees(id)
);
CREATE TABLE api_keys (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER REFERENCES customers(id),
  created_at  TEXT NOT NULL,
  revoked     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY,
  table_name TEXT NOT NULL,
  action     TEXT NOT NULL,
  at         TEXT NOT NULL
);
CREATE TABLE webhooks (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER REFERENCES customers(id),
  url         TEXT NOT NULL,
  active      INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE feature_flags (
  id      INTEGER PRIMARY KEY,
  key     TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0
);

INSERT INTO countries (code, name, region) VALUES
  ('US','United States','Americas'),
  ('CA','Canada','Americas'),
  ('GB','United Kingdom','EMEA'),
  ('DE','Germany','EMEA'),
  ('FR','France','EMEA'),
  ('JP','Japan','APAC'),
  ('AE','United Arab Emirates','EMEA'),
  ('AU','Australia','APAC');

INSERT INTO fx_rates (currency, rate_to_usd, as_of) VALUES
  ('USD',1.00,'2024-06-01'),
  ('EUR',1.08,'2024-06-01'),
  ('GBP',1.27,'2024-06-01');

INSERT INTO product_categories (id, name, parent_id) VALUES
  (1,'Hardware',NULL),
  (2,'Subscription',NULL),
  (3,'Accessory',1);

INSERT INTO customers (id, name, country, created_at, deleted_at) VALUES
  (1,'Alice','US','2024-01-05',NULL),
  (2,'Bob','US','2024-02-11',NULL),
  (3,'Carla','CA','2024-02-20',NULL),
  (4,'Dieter','DE','2024-03-02',NULL),
  (5,'Emi','JP','2024-03-15',NULL),
  (6,'Farah','AE','2024-04-01',NULL),
  (7,'Grace','US','2024-04-22',NULL),
  (8,'Hugo','FR','2024-05-09',NULL),
  (9,'Ines','GB','2024-02-18','2024-05-30'),
  (10,'Jon','AU','2024-05-20',NULL),
  (11,'Kira','DE','2024-01-30','2024-04-15'),
  (12,'Liam','GB','2024-06-01',NULL);

INSERT INTO addresses (id, customer_id, kind, country) VALUES
  (1,1,'billing','US'),(2,2,'billing','US'),
  (3,3,'billing','US'),(4,3,'shipping','CA'),
  (5,4,'billing','DE'),(6,5,'billing','JP'),
  (7,6,'billing','AE'),(8,7,'billing','US'),
  (9,8,'billing','FR'),(10,10,'billing','AU'),
  (11,12,'billing','GB');

INSERT INTO products (id, name, category, list_price, currency) VALUES
  (1,'Widget','Hardware',25.00,'USD'),
  (2,'Gadget','hardware ',40.00,'USD'),
  (3,'Pro Plan','Subscription',100.00,'USD'),
  (4,'Starter Plan','subscription',30.00,'USD'),
  (5,'Cable',' Accessory',8.00,'USD'),
  (6,'Case','ACCESSORY',15.00,'USD'),
  (7,'Enterprise Plan','Subscription',500.00,'USD');

INSERT INTO orders (id, customer_id, ordered_at, status, currency) VALUES
  (1, 1,'2024-02-03T10:00:00-05:00','completed','USD'),
  (2, 1,'2024-03-10T11:00:00-05:00','completed','USD'),
  (3, 2,'2024-03-12T09:30:00-05:00','Completed','USD'),
  (4, 3,'2024-03-15T14:00:00-05:00','CANCELLED','USD'),
  (5, 4,'2024-04-02T08:00:00+02:00','completed','EUR'),
  (6, 5,'2024-04-05T12:00:00+09:00','completed','USD'),
  (7, 2,'2024-04-18T16:00:00-04:00','refunded','USD'),
  (8, 6,'2024-05-01T10:00:00+04:00','completed','USD'),
  (9, 7,'2024-05-07T13:00:00-04:00','completed','USD'),
  (10,1,'2024-05-20T15:00:00-04:00','completed','USD'),
  (11,8,'2024-06-02T10:00:00+02:00','completed','EUR'),
  (12,3,'2024-06-09T11:00:00-04:00','completed','USD'),
  (13,5,'2024-06-15T12:00:00+09:00','cancelled','USD'),
  (14,7,'2024-06-20T13:00:00-04:00','completed','USD'),
  (15,4,'2024-06-28T09:00:00+02:00','completed','EUR'),
  (16,12,'2024-06-25T10:00:00+01:00','completed','GBP'),
  (17,10,'2024-06-29T10:00:00+10:00','pending','USD'),
  (18,1,'2024-06-30T18:00:00-04:00','completed','USD');

INSERT INTO order_items (id, order_id, product_id, quantity, unit_price) VALUES
  (1,1,1,2,25.00),(2,1,5,1,8.00),
  (3,2,3,1,100.00),
  (4,3,2,1,40.00),(5,3,6,2,15.00),
  (6,4,1,1,25.00),
  (7,5,3,1,90.00),(8,5,1,1,22.00),
  (9,6,4,2,30.00),
  (10,7,2,2,40.00),
  (11,8,1,3,25.00),(12,8,5,2,8.00),
  (13,9,3,1,100.00),
  (14,10,6,1,15.00),(15,10,5,1,8.00),
  (16,11,2,1,38.00),(17,11,1,1,25.00),
  (18,12,4,1,30.00),
  (19,13,3,1,100.00),
  (20,14,1,1,25.00),(21,14,6,1,15.00),
  (22,15,2,1,40.00),
  (23,16,7,1,500.00),
  (24,17,1,1,25.00),
  (25,18,3,1,100.00),(26,18,6,1,15.00);

INSERT INTO refunds (id, order_id, amount, refunded_at) VALUES
  (1,7,80.00,'2024-04-25'),
  (2,10,8.00,'2024-05-25');

INSERT INTO payments (id, order_id, amount, method, paid_at) VALUES
  (1,1,58.00,'card','2024-02-03'),
  (2,2,100.00,'card','2024-03-10'),
  (3,3,70.00,'card','2024-03-12'),
  (4,5,112.00,'card','2024-04-02'),
  (5,6,60.00,'paypal','2024-04-05'),
  (6,7,80.00,'card','2024-04-18'),
  (7,8,91.00,'card','2024-05-01'),
  (8,9,100.00,'card','2024-05-07'),
  (9,10,23.00,'card','2024-05-20'),
  (10,11,101.00,'card','2024-06-02'),
  (11,12,30.00,'card','2024-06-09'),
  (12,14,40.00,'card','2024-06-20'),
  (13,15,40.00,'card','2024-06-28'),
  (14,16,500.00,'wire','2024-06-25'),
  (15,18,115.00,'card','2024-06-30');

INSERT INTO plans (id, name, monthly_price, currency) VALUES
  (1,'Basic',30.00,'USD'),
  (2,'Pro',100.00,'USD'),
  (3,'Enterprise',500.00,'USD');

INSERT INTO subscriptions (id, customer_id, plan_id, started_at, ended_at, status) VALUES
  (1,1,2,'2024-02-01',NULL,'active'),
  (2,2,1,'2024-03-01','2024-05-01','cancelled'),
  (3,4,2,'2024-04-01',NULL,'active'),
  (4,6,3,'2024-05-01',NULL,'active'),
  (5,8,1,'2024-05-15',NULL,'active'),
  (6,9,2,'2024-02-20','2024-05-30','cancelled'),
  (7,12,3,'2024-06-01',NULL,'active');

INSERT INTO subscription_events (id, subscription_id, event_type, event_at) VALUES
  (1,1,'started','2024-02-01'),
  (2,2,'started','2024-03-01'),(3,2,'cancelled','2024-05-01'),
  (4,3,'started','2024-04-01'),
  (5,4,'started','2024-05-01'),
  (6,6,'started','2024-02-20'),(7,6,'cancelled','2024-05-30'),
  (8,1,'upgraded','2024-04-10');

INSERT INTO usage_events (id, customer_id, metric, quantity, occurred_at) VALUES
  (1,1,'api_call',1200,'2024-05-01'),(2,1,'api_call',1500,'2024-06-01'),
  (3,4,'api_call',800,'2024-05-01'),(4,4,'export',12,'2024-06-01'),
  (5,6,'api_call',5000,'2024-06-01'),(6,6,'seat',8,'2024-06-01'),
  (7,8,'api_call',300,'2024-06-01'),(8,12,'api_call',9000,'2024-06-15');

INSERT INTO support_tickets (id, customer_id, opened_at, closed_at, priority, status) VALUES
  (1,1,'2024-05-02','2024-05-03','low','closed'),
  (2,4,'2024-05-10','2024-05-14','high','closed'),
  (3,6,'2024-06-01',NULL,'urgent','open'),
  (4,8,'2024-06-05','2024-06-06','medium','closed');

INSERT INTO revenue_daily (day, gross_revenue) VALUES
  ('2024-02-03',58.00),
  ('2024-03-10',100.00),
  ('2024-03-12',70.00),
  ('2024-04-02',121.00),
  ('2024-04-05',60.00),
  ('2024-04-18',80.00),
  ('2024-05-01',91.00),
  ('2024-05-07',100.00);

INSERT INTO employees (id, name, team, manager_id) VALUES
  (1,'Sam','Exec',NULL),(2,'Pat','Sales',1),(3,'Robin','Sales',2),(4,'Devon','Eng',1);
INSERT INTO api_keys (id, customer_id, created_at, revoked) VALUES
  (1,1,'2024-02-01',0),(2,6,'2024-05-01',0),(3,2,'2024-03-01',1);
INSERT INTO audit_log (id, table_name, action, at) VALUES
  (1,'orders','insert','2024-02-03'),(2,'customers','update','2024-05-30');
INSERT INTO webhooks (id, customer_id, url, active) VALUES
  (1,6,'https://example.com/hook',1),(2,1,'https://example.com/h2',0);
INSERT INTO feature_flags (id, key, enabled) VALUES
  (1,'new_dashboard',1),(2,'beta_export',0);
