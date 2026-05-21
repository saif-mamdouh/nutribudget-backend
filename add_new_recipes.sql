SET NAMES utf8mb4;
USE nutribudget;

INSERT INTO recipes (recipe_id, recipe_name, meal_type, ingredients_json, prep_time) VALUES

-- ══ فطار ════════════════════════════════════════════════════════════════════
(317,'أفوكادو توست','فطار','[{"name":"avocado","weight_g":100},{"name":"toast_bread","weight_g":80},{"name":"lemon_juice","weight_g":10},{"name":"salt","weight_g":2}]',10),
(318,'جرانولا باليوغرت','فطار','[{"name":"granola","weight_g":80},{"name":"yogurt","weight_g":150},{"name":"honey","weight_g":20},{"name":"almond","weight_g":15}]',5),
(319,'كرواسون بالنوتيلا','فطار','[{"name":"croissant","weight_g":80},{"name":"nutella","weight_g":30}]',5),
(320,'بيض بالجبنة الشيدر','فطار','[{"name":"eggs","weight_g":120},{"name":"cheddar","weight_g":30},{"name":"butter","weight_g":10},{"name":"salt","weight_g":2}]',15),
(321,'شوفان بالموز والعسل','فطار','[{"name":"oats","weight_g":80},{"name":"milk","weight_g":200},{"name":"banana","weight_g":100},{"name":"honey","weight_g":15}]',10),
(322,'توست بالجبنة الكريمي','فطار','[{"name":"toast_bread","weight_g":80},{"name":"cream_cheese","weight_g":40},{"name":"cucumber","weight_g":50}]',5),
(323,'بروتين بار مع اللبن','فطار','[{"name":"protein_bar","weight_g":70},{"name":"milk","weight_g":200}]',2),
(324,'جبنة ريكوتا مع العسل','فطار','[{"name":"ricotta","weight_g":100},{"name":"honey","weight_g":25},{"name":"walnut","weight_g":20},{"name":"toast_bread","weight_g":60}]',5),

-- ══ غداء ════════════════════════════════════════════════════════════════════
(325,'بيتزا مارغريتا','غداء','[{"name":"pizza_dough","weight_g":200},{"name":"tomato_sauce","weight_g":80},{"name":"mozzarella","weight_g":100},{"name":"olive_oil","weight_g":15}]',35),
(326,'دجاج بالفطر والكريمة','غداء','[{"name":"chicken","weight_g":200},{"name":"mushrooms","weight_g":100},{"name":"cream_cheese","weight_g":50},{"name":"onion","weight_g":50},{"name":"oil","weight_g":15}]',30),
(327,'لازانيا باللحم','غداء','[{"name":"lasagna_sheets","weight_g":150},{"name":"minced_beef","weight_g":200},{"name":"tomato_sauce","weight_g":100},{"name":"mozzarella","weight_g":80},{"name":"parmesan","weight_g":30}]',60),
(328,'سمك بالطماطم والثوم','غداء','[{"name":"fish","weight_g":250},{"name":"tomatoes","weight_g":150},{"name":"garlic","weight_g":10},{"name":"oil","weight_g":20},{"name":"lemon_juice","weight_g":20}]',35),
(329,'ماكرونة بالجبنة البيضاء','غداء','[{"name":"pasta","weight_g":150},{"name":"cream_cheese","weight_g":80},{"name":"cheddar","weight_g":40},{"name":"butter","weight_g":15},{"name":"salt","weight_g":2}]',25),
(330,'سلطة أفوكادو والجمبري','غداء','[{"name":"avocado","weight_g":100},{"name":"shrimp","weight_g":150},{"name":"lemon_juice","weight_g":15},{"name":"olive_oil","weight_g":15},{"name":"tomatoes","weight_g":80}]',20),
(331,'فتة دجاج بالجبنة','غداء','[{"name":"chicken","weight_g":200},{"name":"bread","weight_g":100},{"name":"yogurt","weight_g":150},{"name":"cheddar","weight_g":50},{"name":"tomato_sauce","weight_g":60}]',40),
(332,'تورتيلا بالدجاج والخضار','غداء','[{"name":"tortilla","weight_g":80},{"name":"chicken","weight_g":150},{"name":"cheddar","weight_g":40},{"name":"tomatoes","weight_g":60},{"name":"cucumber","weight_g":50}]',20),
(333,'أرز بالفطر والكريمة','غداء','[{"name":"rice","weight_g":150},{"name":"mushrooms","weight_g":100},{"name":"cream_cheese","weight_g":50},{"name":"onion","weight_g":40},{"name":"butter","weight_g":15}]',30),
(334,'سمك بالليمون والأعشاب','غداء','[{"name":"fish","weight_g":300},{"name":"lemon_juice","weight_g":30},{"name":"garlic","weight_g":10},{"name":"olive_oil","weight_g":20},{"name":"parsley","weight_g":15}]',25),

-- ══ عشاء ════════════════════════════════════════════════════════════════════
(335,'شوربة الفطر بالكريمة','عشاء','[{"name":"mushrooms","weight_g":150},{"name":"cream_cheese","weight_g":60},{"name":"onion","weight_g":50},{"name":"butter","weight_g":15},{"name":"milk","weight_g":100}]',25),
(336,'بيتزا الجبنة الأربعة','عشاء','[{"name":"pizza_dough","weight_g":180},{"name":"mozzarella","weight_g":80},{"name":"cheddar","weight_g":40},{"name":"parmesan","weight_g":25},{"name":"cream_cheese","weight_g":30}]',30),
(337,'سلطة أفوكادو والجبنة','عشاء','[{"name":"avocado","weight_g":100},{"name":"cheddar","weight_g":40},{"name":"tomatoes","weight_g":80},{"name":"lemon_juice","weight_g":15},{"name":"olive_oil","weight_g":10}]',10),
(338,'شوربة عدس بالليمون','عشاء','[{"name":"lentils","weight_g":150},{"name":"lemon_juice","weight_g":20},{"name":"onion","weight_g":60},{"name":"cumin","weight_g":3},{"name":"oil","weight_g":15}]',30),
(339,'توست الفطر بالجبنة','عشاء','[{"name":"toast_bread","weight_g":80},{"name":"mushrooms","weight_g":100},{"name":"cheddar","weight_g":40},{"name":"butter","weight_g":10}]',15),
(340,'سلطة المكسرات والجبنة','عشاء','[{"name":"walnut","weight_g":30},{"name":"almond","weight_g":25},{"name":"cheddar","weight_g":50},{"name":"cucumber","weight_g":80},{"name":"olive_oil","weight_g":10}]',10),
(341,'دجاج بالليمون والثوم','عشاء','[{"name":"chicken","weight_g":200},{"name":"lemon_juice","weight_g":30},{"name":"garlic","weight_g":10},{"name":"olive_oil","weight_g":20},{"name":"cumin","weight_g":3}]',35),
(342,'ماكرونة بالتونة والطماطم','عشاء','[{"name":"pasta","weight_g":150},{"name":"tuna","weight_g":80},{"name":"tomato_sauce","weight_g":80},{"name":"olive_oil","weight_g":15},{"name":"garlic","weight_g":5}]',20),
(343,'جبنة مشوية بالأفوكادو','عشاء','[{"name":"toast_bread","weight_g":80},{"name":"cheddar","weight_g":60},{"name":"avocado","weight_g":80},{"name":"butter","weight_g":10}]',10);

-- Verify
SELECT COUNT(*) as total_recipes FROM recipes;
SELECT meal_type, COUNT(*) as count FROM recipes GROUP BY meal_type;
