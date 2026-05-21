-- ============================================================
-- fix_remaining_12.sql
-- Fixes the 12 ingredients not found in fresh_products
-- Run: mysql -u root -p2474 nutribudget < fix_remaining_12.sql
-- ============================================================
USE nutribudget;

-- Add missing products to fresh_products first
INSERT IGNORE INTO fresh_products (sku, source, category, product_name, price, unit_weight_g)
VALUES
('EST-BREAD-001',    'Estimated', 'Bakery',   'Balady Bread',               5.0,  200.0),
('EST-COFFEE-001',   'Estimated', 'Beverages','Nescafe Classic',           30.0,  200.0),
('EST-CUSTARD-001',  'Estimated', 'Dairy',    'Custard Powder',            15.0,  300.0),
('EST-DOUGH-001',    'Estimated', 'Bakery',   'Dough Wrappers',             8.0,  400.0),
('EST-ICE-001',      'Estimated', 'Other',    'Ice',                        0.5, 1000.0),
('EST-INTEST-001',   'Estimated', 'Meat',     'Intestine (Masareen)',      20.0,  500.0),
('EST-TACO-001',     'Estimated', 'Bakery',   'Taco Shells',               20.0,  200.0),
('EST-TORTILLA-001', 'Estimated', 'Bakery',   'Tortilla Wraps',            15.0,  300.0),
('EST-TURNIP-001',   'Estimated', 'Vegetables','Turnip (Lift)',              5.0,  500.0),
('EST-VINEGAR-001',  'Estimated', 'Condiments','White Vinegar',             10.0, 1000.0),
('EST-YEAST-001',    'Estimated', 'Bakery',   'Instant Yeast',             10.0,  200.0);

-- Now add to ingredient_product_map
INSERT IGNORE INTO ingredient_product_map
    (ingredient_key, sku, source, product_name, price_egp, unit_weight_g, price_per_100g)
VALUES
('bread',           'EST-BREAD-001',    'Estimated', 'Balady Bread',          5.0,  200.0,  2.5),
('coffee',          'EST-COFFEE-001',   'Estimated', 'Nescafe Classic',       30.0, 200.0, 15.0),
('custard',         'EST-CUSTARD-001',  'Estimated', 'Custard Powder',        15.0, 300.0,  5.0),
('dough_wrappers',  'EST-DOUGH-001',    'Estimated', 'Dough Wrappers',         8.0, 400.0,  2.0),
('ice',             'EST-ICE-001',      'Estimated', 'Ice',                    0.5,1000.0,  0.05),
('intestine',       'EST-INTEST-001',   'Estimated', 'Intestine (Masareen)', 20.0, 500.0,  4.0),
('sheep_intestine', 'EST-INTEST-001',   'Estimated', 'Intestine (Masareen)', 20.0, 500.0,  4.0),
('taco_shells',     'EST-TACO-001',     'Estimated', 'Taco Shells',           20.0, 200.0, 10.0),
('tortilla',        'EST-TORTILLA-001', 'Estimated', 'Tortilla Wraps',        15.0, 300.0,  5.0),
('turnip',          'EST-TURNIP-001',   'Estimated', 'Turnip (Lift)',           5.0, 500.0,  1.0),
('vinegar',         'EST-VINEGAR-001',  'Estimated', 'White Vinegar',         10.0,1000.0,  1.0),
('yeast',           'EST-YEAST-001',    'Estimated', 'Instant Yeast',         10.0, 200.0,  5.0);

-- Verify — should show 0 Estimated-only ingredients
SELECT COUNT(DISTINCT ingredient_key) AS still_estimated_only
FROM ingredient_product_map
WHERE source = 'Estimated'
  AND ingredient_key NOT IN (
    SELECT ingredient_key FROM ingredient_product_map WHERE source != 'Estimated'
  );
