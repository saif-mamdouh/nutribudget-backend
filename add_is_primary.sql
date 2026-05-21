USE nutribudget;

-- ── 1. Add is_primary column (MySQL 8.0 compatible) ──────────────
ALTER TABLE ingredient_product_map 
ADD COLUMN is_primary TINYINT(1) NOT NULL DEFAULT 1;

-- ── 2. Mark bad mappings as is_primary = 0 ────────────────────────

-- honey: cheese, cereal, flavored products
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'honey' AND (
    product_name LIKE '%Cheese%' OR product_name LIKE '%Cream%'
    OR product_name LIKE '%Cereal%' OR product_name LIKE '%Corn Flakes%'
    OR product_name LIKE '%Granola%' OR product_name LIKE '%Bar%'
    OR product_name LIKE '%Rings%' OR product_name LIKE '%Loops%'
    OR product_name LIKE '%Flavor%' OR product_name LIKE '%Candy%'
    OR product_name LIKE '%Wax%'
);

-- coconut: energy drinks, sodas
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'coconut' AND (
    product_name LIKE '%Energy Drink%' OR product_name LIKE '%Red Bull%'
    OR product_name LIKE '%Soda%' OR product_name LIKE '%Vitamin Water%'
    OR product_name LIKE '%Protein Bar%' OR product_name LIKE '%Drink%'
);

-- yogurt: yogurt drinks, flavored yogurts
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'yogurt' AND (
    product_name LIKE '%Yogurt Drink%' OR product_name LIKE '%Zabado%'
    OR product_name LIKE '%You Go%' OR product_name LIKE '%HiPro%'
    OR product_name LIKE '%Strawberry%' OR product_name LIKE '%Mango%'
    OR product_name LIKE '%Peach%' OR product_name LIKE '%Berry%'
    OR product_name LIKE '%Berries%' OR product_name LIKE '%Mixed%'
    OR product_name LIKE '%Fruit%' OR product_name LIKE '%Treats%'
    OR product_name LIKE '%Drinking%'
);

-- flour: tortilla bread (not wheat flour)
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'flour' AND (
    product_name LIKE '%Tortilla%' OR product_name LIKE '%Tortilla Bread%'
);

-- milk: chocolate milk, flavored drinks
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'milk' AND (
    product_name LIKE '%Chocolate%' OR product_name LIKE '%Strawberry%'
    OR product_name LIKE '%Mango%' OR product_name LIKE '%Banana%'
    OR product_name LIKE '%Flavored%' OR product_name LIKE '%Caramel%'
);

-- cream: ice cream, body care, flavored
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'cream' AND (
    product_name LIKE '%Ice Cream%' OR product_name LIKE '%Body%'
    OR product_name LIKE '%Skin%' OR product_name LIKE '%Face%'
    OR product_name LIKE '%Lotion%' OR product_name LIKE '%Soda%'
    OR product_name LIKE '%Wafer%' OR product_name LIKE '%Biscuit%'
);

-- butter: peanut butter, flavored spreads
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'butter' AND (
    product_name LIKE '%Peanut Butter%' OR product_name LIKE '%Almond Butter%'
    OR product_name LIKE '%Hazelnut%' OR product_name LIKE '%Popcorn%'
    OR product_name LIKE '%Flavor%'
);

-- cheese: cheese-flavored snacks
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'cheese' AND (
    product_name LIKE '%Cheese Puff%' OR product_name LIKE '%Cheese Ball%'
    OR product_name LIKE '%Cheese Snack%' OR product_name LIKE '%Cheese Cracker%'
    OR product_name LIKE '%Popcorn%' OR product_name LIKE '%Chips%'
    OR product_name LIKE '%Cheetos%' OR product_name LIKE '%Doritos%'
    OR product_name LIKE '%Flavor%'
);

-- mushroom: soups, sauces, powders
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'mushroom' AND (
    product_name LIKE '%Soup%' OR product_name LIKE '%Sauce%'
    OR product_name LIKE '%Powder%' OR product_name LIKE '%Seasoning%'
    OR product_name LIKE '%Chips%' OR product_name LIKE '%Flavor%'
);

-- pepper: spices, sauces (keep fresh bell pepper only)
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'pepper' AND (
    product_name LIKE '%Black Pepper%' OR product_name LIKE '%White Pepper%'
    OR product_name LIKE '%Chili%' OR product_name LIKE '%Sauce%'
    OR product_name LIKE '%Flakes%' OR product_name LIKE '%Spice%'
    OR product_name LIKE '%Seasoning%' OR product_name LIKE '%Powder%'
    OR product_name LIKE '%Chips%' OR product_name LIKE '%Snack%'
);

-- vanilla: drinks, supplements, baked goods
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'vanilla' AND (
    product_name LIKE '%Drink%' OR product_name LIKE '%Soda%'
    OR product_name LIKE '%Supplement%' OR product_name LIKE '%Protein%'
    OR product_name LIKE '%Energy%' OR product_name LIKE '%Ice Cream%'
    OR product_name LIKE '%Wafer%' OR product_name LIKE '%Biscuit%'
    OR product_name LIKE '%Cake Mix%' OR product_name LIKE '%Candy%'
);

-- sugar_syrup: wax products (hair removal)
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key = 'sugar_syrup' AND product_name LIKE '%Wax%';

-- eggs: eggplant, egg-flavored products
UPDATE ingredient_product_map SET is_primary = 0
WHERE ingredient_key IN ('eggs', 'egg') AND (
    product_name LIKE '%Eggplant%' OR product_name LIKE '%Egg Noodle%'
    OR product_name LIKE '%Egg Roll%' OR product_name LIKE '%Custard%'
    OR product_name LIKE '%Liquid Egg%' OR product_name LIKE '%Egg Powder%'
);

-- ── 3. Verify ─────────────────────────────────────────────────────
SELECT 
    ingredient_key,
    SUM(is_primary = 1) AS primary_count,
    SUM(is_primary = 0) AS excluded_count,
    COUNT(*) AS total
FROM ingredient_product_map
WHERE ingredient_key IN (
    'honey','coconut','yogurt','flour','milk','cream',
    'butter','cheese','mushroom','pepper','vanilla',
    'sugar_syrup','eggs','egg'
)
GROUP BY ingredient_key
ORDER BY ingredient_key;

-- Show what got excluded
SELECT ingredient_key, product_name
FROM ingredient_product_map
WHERE is_primary = 0
ORDER BY ingredient_key, product_name;