-- ============================================================
-- add_missing_mappings.sql
-- ============================================================
-- Adds real product mappings for ingredients that were
-- previously "Estimated" or missing from ingredient_product_map
-- ============================================================

USE nutribudget;

INSERT IGNORE INTO ingredient_product_map
  (ingredient_key, sku, source, product_name, price_egp, unit_weight_g, price_per_100g)
VALUES

-- ── Pizza / Dough ─────────────────────────────────────────────────────────────
('pizza_dough',      'HYP-04524', 'Hyperone',  'Top Value Plain pizza Crust - 3 Pieces',      59.95,  300,  19.98),
('pizza_dough',      'HYP-04538', 'Hyperone',  'Molto Forni Plain Pizza Crust - 3 Pieces',    79.95,  500,  15.99),
('dough',            'HYP-04524', 'Hyperone',  'Top Value Plain pizza Crust - 3 Pieces',      59.95,  300,  19.98),
('thin_dough',       'HYP-04517', 'Hyperone',  'Top Value Frozen Fillo Pastry - 350g',        23.95,  350,   6.84),
('puff_pastry',      'HYP-04517', 'Hyperone',  'Top Value Frozen Fillo Pastry - 350g',        23.95,  350,   6.84),
('puff_pastry',      'HYP-04519', 'Hyperone',  'Al Zahar Extra Frozen Fillo Pastry - 500g',   39.95,  500,   7.99),
('shortcrust_pastry','HYP-04517', 'Hyperone',  'Top Value Frozen Fillo Pastry - 350g',        23.95,  350,   6.84),
('pie_crust',        'HYP-04517', 'Hyperone',  'Top Value Frozen Fillo Pastry - 350g',        23.95,  350,   6.84),
('kunafa_dough',     'HYP-04517', 'Hyperone',  'Top Value Frozen Fillo Pastry - 350g',        23.95,  350,   6.84),
('biscuit_base',     'HYP-04226', 'Hyperone',  'Abu Auf Caramelized Cinnamon Biscuit Protein Bar - 70g', 63.45, 70, 90.64),

-- ── Cheese varieties ──────────────────────────────────────────────────────────
('mozzarella',       'CAR-00326', 'Carrefour', 'Domty Shredded Mozzarella Cheese - 280 gm',   71.25,  280,  25.45),
('mozzarella',       'HYP-03659', 'Hyperone',  'Domty Shredded Mozzarella Cheese - 280g',     72.95,  280,  26.05),
('mozzarella',       'HYP-03632', 'Hyperone',  'Top Value Mozzarella Cheese - 1K',           234.95, 1000,  23.50),
('cheddar',          'CAR-01289', 'Carrefour', 'Rhodes Cheddar Cheese - 250 grams',            28.95,  250,  11.58),
('cheddar',          'HYP-03715', 'Hyperone',  'Almarai Cheddar Fita Cheese - 250g',           23.95,  250,   9.58),
('parmesan',         'HYP-03784', 'Hyperone',  'Saluti Italian Parmesan Cheese -250g',        389.95,  250, 155.98),
('parmesan',         'SPN-01932', 'Spinneys',  'Farm Cheese Shredded Parmesan Cheese',        489.95, 1000,  48.99),
('ricotta',          'CAR-01246', 'Carrefour', 'Dina Farms Ricotta Cheese - 250gm',            66.95,  250,  26.78),
('cream_cheese',     'CAR-00697', 'Carrefour', 'Obour Land Cream Cheese - 250 gram',           24.00,  250,   9.60),
('cream_cheese',     'HYP-03664', 'Hyperone',  'Prima Cream Cheese - 240g',                    88.50,  240,  36.88),
('cream_cheese',     'CAR-00493', 'Carrefour', 'Dina Farms Cream Cheese Spread - 500gm',      176.95,  500,  35.39),
('mascarpone',       'CAR-00680', 'Carrefour', 'Le Gall Natural Cream Cheese - 1 Kg',         466.70, 1000,  46.67),
('cheese_sauce',     'HYP-03552', 'Hyperone',  'Good France Cheddar Sauce - 400ml',            84.75,  400,  21.19),

-- ── Mushrooms ────────────────────────────────────────────────────────────────
('mushrooms',        'CAR-00025', 'Carrefour', 'Mushroom - 200 gm',                            68.60,  200,  34.30),
('mushrooms',        'SPN-02020', 'Spinneys',  'PICO - WHITE BUTTON MUSHROOM - 200G',          84.95,  200,  42.48),
('mushrooms',        'SPN-02023', 'Spinneys',  'Souna Mushroom White - 200G',                  69.95,  200,  34.98),
('mushrooms',        'HYP-02953', 'Hyperone',  'Kenana Pieces & Stems Mushroom - 400g',        49.50,  400,  12.37),

-- ── Avocado ───────────────────────────────────────────────────────────────────
('avocado',          'HYP-04288', 'Hyperone',  'Avocado',                                     160.95, 1000,  16.10),
('avocado',          'SPN-02203', 'Spinneys',  'Green Avocados',                              189.95, 1000,  19.00),
('avocado',          'SPN-02015', 'Spinneys',  'Pico Avocado Ready to Eat',                   229.95, 1000,  23.00),

-- ── Tortilla / Wraps ─────────────────────────────────────────────────────────
('tortilla',         'HYP-04169', 'Hyperone',  'Breadway Flour Tortilla Bread - 240g',         44.95,  240,  18.73),
('tortilla_chips',   'HYP-04169', 'Hyperone',  'Breadway Flour Tortilla Bread - 240g',         44.95,  240,  18.73),

-- ── Lasagna ───────────────────────────────────────────────────────────────────
('lasagna_sheets',   'HYP-02751', 'Hyperone',  'El Maleka Lasagna - 400g',                     30.00,  400,   7.50),
('lasagna_sheets',   'HYP-02738', 'Hyperone',  'Italiano Premium Range Lasagna - 400g',        45.00,  400,  11.25),
('lasagna_sheets',   'HYP-02851', 'Hyperone',  'Don Lopez Lasagna - 400g',                     77.50,  400,  19.38),

-- ── Nuts ─────────────────────────────────────────────────────────────────────
('almond',           'HYP-04268', 'Hyperone',  'Ragab El-Attar Raw Almonds-By Weight',        490.00,  500,  98.00),
('almond',           'HYP-04257', 'Hyperone',  'Abu Auf Salted Almonds - By Weight',          710.00,  500, 142.00),
('almond_flour',     'HYP-04268', 'Hyperone',  'Ragab El-Attar Raw Almonds-By Weight',        490.00,  500,  98.00),
('walnut',           'HYP-04254', 'Hyperone',  'Ragab El-Attar Walnuts -By Weight',           480.00,  500,  96.00),
('pistachio',        'HYP-04277', 'Hyperone',  'Abu Auf Pistachio - By Weight',               665.00,  500, 133.00),
('pistachio',        'HYP-04271', 'Hyperone',  'Ragab El-Attar Raw Pistachio -By Weight',    1600.00,  500, 320.00),

-- ── Coconut products ──────────────────────────────────────────────────────────
('coconut',          'HYP-04258', 'Hyperone',  'Abu Auf Coconut - By Weight',                 450.00,  400, 112.50),
('coconut_milk',     'CAR-00937', 'Carrefour', 'Juhayna Vegan Coconut Milk - 1 Liter',        108.00, 1000,  10.80),
('coconut_milk',     'CAR-00701', 'Carrefour', 'Alpro Coconut Milk - 1 Liter',                197.70, 1000,  19.77),
('coconut_milk',     'CAR-00998', 'Carrefour', 'Lamar Tom Coconut Milk - 1 Liter',            107.75, 1000,  10.78),

-- ── Almond milk ───────────────────────────────────────────────────────────────
('almond_milk',      'CAR-01214', 'Carrefour', 'Juhayna Vegan Almond Milk - 1 Liter',         108.00, 1000,  10.80),
('almond_milk',      'CAR-00766', 'Carrefour', 'Alpro Almond Milk - 1 Liter',                 197.70, 1000,  19.77),
('almond_milk',      'CAR-00739', 'Carrefour', 'Lamar Almond Milk - 1 Liter',                 107.75, 1000,  10.78),

-- ── Granola ───────────────────────────────────────────────────────────────────
('granola',          'SPN-01694', 'Spinneys',  'Abu Auf Granola Cranberries & Raisins - 400 Gm', 185.95, 400, 46.49),
('granola',          'SPN-01681', 'Spinneys',  'Sante Gold Granola Nuts And Honey - 300Gm',   191.50,  300,  63.83),
('granola_bar',      'SPN-01669', 'Spinneys',  'Lino Granola Bar With Coconut & Almond - 40 Gr', 36.95, 40, 92.38),

-- ── Nutella / Spreads ────────────────────────────────────────────────────────
('nutella',          'HYP-03069', 'Hyperone',  'Nutella Chocolate Spread - 350g',             213.75,  350,  61.07),
('nutella',          'HYP-03070', 'Hyperone',  'Nutella Chocolate Spread - 600g',             400.00,  600,  66.67),

-- ── Croissant ────────────────────────────────────────────────────────────────
('croissant',        'HYP-04201', 'Hyperone',  'Hyperone Plain Croissants - 4 Pieces',         56.00,  250,  22.40),
('croissant',        'HYP-04202', 'Hyperone',  'Hyperone Croissant With Thyme - 4 Pieces',     65.00,  250,  26.00),

-- ── Protein bar ───────────────────────────────────────────────────────────────
('protein_bar',      'HYP-04242', 'Hyperone',  'Abu Auf Chocolate Brownie Protein Bar - 70g',  63.45,   70,  90.64),
('protein_bar',      'SPN-01676', 'Spinneys',  'Advanced Sports Nutrition Chocolate Protein Bar - 70 Gr', 49.45, 70, 70.64);

-- ── Verify ────────────────────────────────────────────────────────────────────
SELECT
  ingredient_key,
  COUNT(*) AS products_count,
  MIN(price_per_100g) AS cheapest,
  GROUP_CONCAT(source ORDER BY price_per_100g SEPARATOR ', ') AS sources
FROM ingredient_product_map
WHERE ingredient_key IN (
  'pizza_dough','mozzarella','cheddar','parmesan','ricotta',
  'cream_cheese','mushrooms','avocado','tortilla','lasagna_sheets',
  'almond','walnut','pistachio','coconut','coconut_milk',
  'almond_milk','granola','nutella','croissant','protein_bar'
)
GROUP BY ingredient_key
ORDER BY ingredient_key;
