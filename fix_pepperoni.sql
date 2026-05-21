USE nutribudget;

-- ══════════════════════════════════════════════════════════════
-- 1. PEPPERONI → Salami (أفضل بديل مصري)
-- ══════════════════════════════════════════════════════════════

-- امسح الـ Beef Luncheon الغلط
DELETE FROM ingredient_product_map
WHERE ingredient_key = 'pepperoni'
  AND (product_name LIKE '%Luncheon%' OR product_name LIKE '%luncheon%');

-- ضيف Salami كبديل حقيقي
INSERT IGNORE INTO ingredient_product_map
  (ingredient_key, sku, source, product_name, price_egp, unit_weight_g, price_per_100g)
VALUES
('pepperoni', 'CAR-00367', 'Carrefour', 'Halwani Dried Salami Beef',         439.95, 1000, 43.99),
('pepperoni', 'CAR-00402', 'Carrefour', 'Halwani Salami Beef',               439.95, 1000, 43.99),
('pepperoni', 'CAR-00648', 'Carrefour', 'Egy Swiss Dried Salami - 200 gm',   140.00,  200, 70.00),
('pepperoni', 'HYP-03800', 'Hyperone',  'Swiss Choice Air Dried Salami - 200g', 144.95, 200, 72.48),
('pepperoni', 'CAR-00678', 'Carrefour', 'Merai Salami Dried',                499.95, 1000, 49.99);

-- ══════════════════════════════════════════════════════════════
-- 2. BREAD → Real balady bread from Hyperone
-- ══════════════════════════════════════════════════════════════
INSERT IGNORE INTO ingredient_product_map
  (ingredient_key, sku, source, product_name, price_egp, unit_weight_g, price_per_100g)
VALUES
('bread',       'HYP-04159', 'Hyperone',  'Hyperone Balady Bread - 5 Pieces',       17.50, 300, 5.83),
('bread',       'HYP-04173', 'Hyperone',  'Hyperone Baguette Bread - 1 Piece',      17.50, 350, 5.00),
('bread',       'HYP-04162', 'Hyperone',  'Rich Bake Lebanese Bread - 185g',        15.95, 185, 8.62),
('white_bread', 'HYP-04191', 'Hyperone',  'Breadway Plain Toast - 500g',            53.50, 500, 10.70),
('white_bread', 'HYP-04183', 'Hyperone',  'Rich Bake Normal Toast Bread - 500g',    56.95, 500, 11.39),
('toast_bread', 'HYP-04191', 'Hyperone',  'Breadway Plain Toast - 500g',            53.50, 500, 10.70),
('toast_bread', 'HYP-04193', 'Hyperone',  'Breadway Milk Toast Bread - 500g',       53.50, 500, 10.70);

-- ══════════════════════════════════════════════════════════════
-- 3. SALAMI → Direct mapping
-- ══════════════════════════════════════════════════════════════
INSERT IGNORE INTO ingredient_product_map
  (ingredient_key, sku, source, product_name, price_egp, unit_weight_g, price_per_100g)
VALUES
('sausage',    'HYP-04371', 'Hyperone',  'Balady Beef Sausage',              390.00,  500, 78.00),
('pastirma',   'HYP-03788', 'Hyperone',  'Balady Pastrami - By Weight',      649.50,  300, 216.50),
('pastirma',   'CAR-00323', 'Carrefour', 'Almarai Basterma',                 889.95, 1000, 88.99),
('ham',        'CAR-00367', 'Carrefour', 'Halwani Dried Salami Beef',        439.95, 1000, 43.99),
('turkey_bacon','CAR-00367','Carrefour', 'Halwani Dried Salami Beef',        439.95, 1000, 43.99);

-- ══════════════════════════════════════════════════════════════
-- 4. VERIFY — شوف الـ pepperoni دلوقتي
-- ══════════════════════════════════════════════════════════════
SELECT ingredient_key, product_name, source, price_per_100g
FROM ingredient_product_map
WHERE ingredient_key = 'pepperoni'
ORDER BY price_per_100g;
