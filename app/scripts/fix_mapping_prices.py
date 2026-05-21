"""
fix_mapping_prices.py
═══════════════════════════════════════════════════════════════
Fixes ALL Estimated-only ingredients in ingredient_product_map.

Run ONCE:
    cd D:\\desktop\\claude_GP
    python -m app.scripts.fix_mapping_prices
"""
import asyncio
import logging
from sqlalchemy import text
from app.database import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ── Keyword patterns + price/100g floor/ceiling ───────────────────────────────
# ALL patterns MUST have leading % to catch brand-prefixed names
KEYWORD_MAP = {
    # ── Meat ──────────────────────────────────────────────────────────────────
    "beef":              (["% Beef%","% Minced Beef%","% Beef Cubes%","لحمة%"],            25.0,200.0),
    "minced_beef":       (["% Minced Beef%","% Ground Beef%","لحمة مفرومة%"],              25.0,150.0),
    "ground_beef":       (["% Minced Beef%","% Ground Beef%"],                             25.0,150.0),
    "beef_steak":        (["% Beef Steak%","% Beef Fillet%","% Beef%"],                    30.0,200.0),
    "beef_cubes":        (["% Beef Cubes%","% Beef%"],                                     25.0,180.0),
    "lamb":              (["% Lamb%","ضاني%"],                                             35.0,250.0),
    "ground_lamb":       (["% Lamb%","% Minced Lamb%","ضاني مفروم%"],                      35.0,250.0),
    "minced_lamb":       (["% Lamb%","% Minced Lamb%"],                                    35.0,250.0),
    "lamb_chops":        (["% Lamb%","% Lamb Chop%"],                                      35.0,250.0),
    "lamb_ribs":         (["% Lamb%","% Lamb Rack%"],                                      35.0,250.0),
    "veal":              (["% Veal%","عجل%"],                                              30.0,200.0),
    "chicken":           (["% Chicken%","فراخ%","دجاج%"],                                   8.0, 80.0),
    "chicken_breast":    (["% Chicken Breast%","صدر دجاج%"],                              10.0, 80.0),
    "chicken_thigh":     (["% Chicken Thigh%","ران دجاج%"],                                8.0, 70.0),
    "chicken_whole":     (["% Whole Chicken%","% Fresh Chicken%"],                          5.0, 60.0),
    "chicken_liver":     (["% Chicken Liver%","كبدة فراخ%"],                               5.0, 60.0),
    "liver":             (["% Liver%","كبدة%"],                                             5.0, 80.0),
    "beef_sausage":      (["% Beef Sausage%","% Sausage%","سجق%"],                          5.0, 60.0),
    "fish":              (["% Tilapia%","% Fish Fillet%","% Salmon%","بلطي%"],             10.0,200.0),
    "tilapia":           (["% Tilapia%","بلطي%"],                                          10.0, 60.0),
    "salmon":            (["% Salmon%","سلمون%"],                                          50.0,250.0),
    "shrimp":            (["% Shrimp%","% Shrimps%","جمبري%"],                             40.0,200.0),
    "tuna_canned":       (["% Tuna%","تونة%"],                                             15.0,100.0),

    # ── Dairy ─────────────────────────────────────────────────────────────────
    "eggs":              (["% Eggs%","% Egg -%","% Egg C%","بيض%"],                         3.0, 25.0),
    "milk":              (["% Milk%","حليب%"],                                              1.0, 20.0),
    "butter":            (["% Butter%","% Blended Butter%","زبدة%"],                        8.0, 40.0),
    "ghee":              (["% Ghee%","% Samn%","سمن%"],                                    20.0,150.0),
    "cream":             (["% Cream%","% Fresh Cream%","كريمة%"],                           5.0, 80.0),
    "heavy_cream":       (["% Heavy Cream%","% Whipping Cream%","كريمة%"],                  5.0, 80.0),
    "yogurt":            (["% Yoghurt%","% Yogurt%","زبادي%"],                              1.0, 20.0),
    "labneh":            (["% Labneh%","لبنة%"],                                            3.0, 30.0),
    "white_cheese":      (["% White Cheese%","% Feta%","جبنة بيضاء%"],                      8.0, 80.0),
    "cheese":            (["% Cheese%","جبنة%"],                                            5.0,100.0),
    "mozzarella":        (["% Mozzarella%","موتزاريلا%"],                                  10.0, 80.0),
    "cream_cheese":      (["% Cream Cheese%","كريم تشيز%"],                                10.0,100.0),
    "condensed_milk":    (["% Condensed Milk%","لبن مكثف%"],                                3.0, 30.0),

    # ── Bread & Bakery ────────────────────────────────────────────────────────
    "bread":             (["% Balady Bread%","% Pita Bread%","% Lebanese Bread%","عيش%"],   3.0, 20.0),
    "bread_baladi":      (["% Balady Bread%","عيش بلدي%"],                                  3.0, 15.0),
    "toast_bread":       (["% Plain Toast%","% Milk Toast%","تواست%"],                      5.0, 25.0),
    "burger_bun":        (["% Burger Bun%","% Bun%"],                                       5.0, 30.0),
    "breadcrumbs":       (["% Breadcrumb%","% Bread Crumb%","بقسماط%"],                     5.0, 30.0),
    "pizza_dough":       (["% Pizza Dough%","% Pizza Base%","عجينة بيتزا%"],                5.0, 40.0),
    "phyllo_dough":      (["% Kunafa%","% Kataifi%","كنافة%"],                              5.0, 60.0),
    "kunafa_dough":      (["% Kunafa%","% Kataifi%","كنافة%"],                              5.0, 60.0),
    "croissant":         (["% Croissant%","كرواسون%"],                                      5.0, 50.0),

    # ── Vegetables ────────────────────────────────────────────────────────────
    "tomato":            (["% Tomato%","طماطم%"],                                            1.0, 20.0),
    "onion":             (["% Onion%","بصل%"],                                               1.0, 15.0),
    "garlic":            (["% Garlic%","ثوم%"],                                              2.0, 40.0),
    "potato":            (["% Potato%","بطاطس%"],                                            1.0, 15.0),
    "eggplant":          (["% Eggplant%","% Aubergine%","باذنجان%"],                          1.0, 20.0),
    "zucchini":          (["% Zucchini%","% Courgette%","كوسة%"],                            1.0, 20.0),
    "carrot":            (["% Carrot%","جزرة%"],                                             1.0, 15.0),
    "spinach":           (["% Spinach%","سبانخ%"],                                           1.0, 20.0),
    "bell_pepper":       (["% Bell Pepper%","% Sweet Pepper%","فلفل رومي%"],                 3.0, 40.0),
    "green_pepper":      (["% Green Pepper%","% Sweet Green Pepper%","فلفل أخضر%"],          2.0, 30.0),
    "cucumber":          (["% Cucumber%","خيار%"],                                           1.0, 20.0),
    "mushroom":          (["% Mushroom%","مشروم%"],                                          5.0, 60.0),
    "peas":              (["% Peas%","% Green Peas%","بسلة%"],                               2.0, 25.0),
    "okra":              (["% Okra%","% Bamia%","بامية%"],                                   1.0, 20.0),
    "cauliflower":       (["% Cauliflower%","قرنبيط%"],                                      1.0, 20.0),
    "broccoli":          (["% Broccoli%","بروكلي%"],                                         3.0, 30.0),
    "leek":              (["% Leek%","كراث%"],                                               2.0, 25.0),
    "celery":            (["% Celery%","كرفس%"],                                             2.0, 25.0),
    "fresh_molokhia":    (["% Molokhia%","ملوخية%"],                                         1.0, 20.0),
    "frozen_molokhia":   (["% Molokhia%","% Frozen%","ملوخية مجمدة%"],                       2.0, 25.0),
    "mixed_vegetables":  (["% Mixed Veg%","% Mixed Vegetables%","خضار مشكلة%"],              2.0, 30.0),
    "lettuce":           (["% Lettuce%","خس%"],                                              1.0, 20.0),
    "cabbage":           (["% Cabbage%","كرنب%"],                                            1.0, 15.0),
    "fava_beans_dried":  (["% Foul%","% Fava%","فول%"],                                      1.0, 15.0),
    "fava_beans_green":  (["% Foul%","% Fava%","فول أخضر%"],                                 1.0, 20.0),

    # ── Fruits ────────────────────────────────────────────────────────────────
    "lemon":             (["% Lemon%","ليمون%"],                                             2.0, 30.0),
    "lemon_juice":       (["% Lemon%","ليمون%"],                                             2.0, 30.0),
    "orange":            (["% Orange%","برتقال%"],                                           1.0, 20.0),
    "tomato_paste":      (["% Tomato Paste%","% Tomato Puree%","معجون طماطم%"],              2.0, 30.0),
    "tomato_sauce":      (["% Tomato Sauce%","% Tomato Passata%","صلصة طماطم%"],             2.0, 30.0),

    # ── Grains ────────────────────────────────────────────────────────────────
    "rice":              (["% Rice%","أرز%"],                                                1.0, 15.0),
    "pasta":             (["% Pasta%","% Spaghetti%","% Penne%","مكرونة%"],                  1.0, 15.0),
    "lentils":           (["% Lentil%","% Lentils%","عدس%"],                                 1.0, 15.0),
    "chickpeas":         (["% Chickpea%","% Chick Pea%","حمص%"],                             1.0, 20.0),
    "foul":              (["% Foul%","% Fava Bean%","فول%"],                                  1.0, 15.0),
    "flour":             (["% Flour%","% Plain Flour%","دقيق%"],                             0.5, 10.0),
    "sugar":             (["% Sugar%","سكر%"],                                               0.5, 10.0),
    "sugar_syrup":       (["% Honey%","عسل%"],                                               5.0,150.0),
    "qater":             (["% Honey%","عسل%"],                                               5.0,150.0),
    "bulgur":            (["% Bulgur%","% Burghul%","برغل%"],                                2.0, 20.0),
    "couscous":          (["% Couscous%","كسكس%"],                                           3.0, 25.0),
    "spaghetti":         (["% Spaghetti%","% Pasta%","مكرونة%"],                             1.0, 15.0),

    # ── Oils & Sauces ─────────────────────────────────────────────────────────
    "vegetable_oil":     (["% Vegetable Oil%","% Sunflower Oil%","زيت نباتي%"],              3.0, 25.0),
    "olive_oil":         (["% Olive Oil%","زيت زيتون%"],                                   15.0,150.0),
    "oil":               (["% Vegetable Oil%","% Sunflower Oil%","زيت نباتي%"],              3.0, 25.0),
    "cooking_oil":       (["% Vegetable Oil%","% Cooking Oil%","زيت%"],                      3.0, 25.0),
    "tahini":            (["% Tahini%","طحينة%","طحينية%"],                                  5.0, 60.0),
    "mayonnaise":        (["% Mayonnaise%","مايونيز%"],                                      5.0, 50.0),
    "ketchup":           (["% Ketchup%","كاتشب%"],                                           3.0, 30.0),
    "hot_sauce":         (["% Hot Sauce%","% Chili Sauce%","صلصة حارة%"],                    5.0, 50.0),
    "vinegar":           (["% Vinegar%","خل%"],                                              1.0, 15.0),
    "soy_sauce":         (["% Soy Sauce%","صلصة صويا%"],                                     5.0, 50.0),

    # ── Nuts & Seeds ──────────────────────────────────────────────────────────
    "almonds":           (["% Almond%","لوز%"],                                             20.0,200.0),
    "walnuts":           (["% Walnut%","جوز%"],                                             20.0,200.0),
    "pine_nuts":         (["% Pine Nut%","صنوبر%"],                                         30.0,300.0),
    "sesame":            (["% Sesame%","سمسم%"],                                              5.0, 60.0),
    "peanuts":           (["% Peanut%","فول سوداني%"],                                        5.0, 50.0),
    "nuts":              (["% Mixed Nut%","% Nut%","مكسرات%"],                               15.0,200.0),

    # ── Sweets & Dairy-based ──────────────────────────────────────────────────
    "honey":             (["% Honey%","عسل%"],                                               5.0,150.0),
    "chocolate":         (["% Chocolate%","شوكولاتة%"],                                     10.0,100.0),
    "cocoa_powder":      (["% Cocoa%","% Cacao%","كاكاو%"],                                 10.0,100.0),
    "vanilla":           (["% Vanilla%","فانيليا%"],                                          5.0, 80.0),
    "baking_powder":     (["% Baking Powder%","بيكنج باودر%"],                               2.0, 30.0),
    "yeast":             (["% Yeast%","خميرة%"],                                              2.0, 30.0),
    "cornstarch":        (["% Cornstarch%","% Corn Starch%","% Nasha%","نشا%"],               1.0, 20.0),

    # ── Spices ────────────────────────────────────────────────────────────────
    "salt":              (["% Salt%","ملح%"],                                                0.1,  5.0),
    "black_pepper":      (["% Black Pepper%","فلفل أسود%"],                                  2.0, 50.0),
    "cumin":             (["% Cumin%","كمون%"],                                               3.0, 50.0),
    "paprika":           (["% Paprika%","بابريكا%"],                                          3.0, 50.0),
    "turmeric":          (["% Turmeric%","كركم%"],                                            3.0, 50.0),
    "cinnamon":          (["% Cinnamon%","قرفة%"],                                            3.0, 60.0),
    "allspice":          (["% Allspice%","% Mixed Spice%","بهارات%"],                          3.0, 60.0),
    "cardamom":          (["% Cardamom%","هيل%"],                                            10.0,150.0),
    "nutmeg":            (["% Nutmeg%","جوزة الطيب%"],                                       10.0,150.0),
    "ginger":            (["% Ginger%","جنزبيل%"],                                            3.0, 60.0),
    "chili":             (["% Chili%","% Chilli%","فلفل حار%"],                               2.0, 40.0),
    "bay_leaves":        (["% Bay Leaf%","% Bay Leaves%","ورق غار%"],                          2.0, 40.0),
    "spices":            (["% Mixed Spice%","% Seven Spice%","بهارات مشكلة%"],                 3.0, 60.0),
    "mixed_spices":      (["% Mixed Spice%","% Seven Spice%","بهارات%"],                       3.0, 60.0),

    # ── Herbs ─────────────────────────────────────────────────────────────────
    "parsley":           (["% Parsley%","بقدونس%"],                                           1.0, 20.0),
    "coriander":         (["% Coriander%","% Cilantro%","كزبرة%"],                            1.0, 20.0),
    "mint":              (["% Mint%","نعناع%"],                                               1.0, 20.0),
    "dill":              (["% Dill%","شبت%"],                                                 1.0, 20.0),
    "basil":             (["% Basil%","ريحان%"],                                               2.0, 30.0),

    # ── Stock & Misc ──────────────────────────────────────────────────────────
    "chicken_broth":     (["% Chicken Stock%","% Chicken Broth%","مرق دجاج%"],               1.0, 20.0),
    "beef_broth":        (["% Beef Stock%","% Beef Broth%","مرق لحمة%"],                      1.0, 20.0),
    "stock":             (["% Stock%","% Broth%","% Bouillon%","مرق%"],                       1.0, 20.0),
    "coconut":           (["% Coconut%","جوز هند%"],                                          5.0, 60.0),
    "raisins":           (["% Raisin%","زبيب%"],                                              5.0, 50.0),
    "dried_prunes":      (["% Prune%","% Dried Plum%","برقوق مجفف%"],                          5.0, 60.0),

    # ── Extra: all 138 skipped ingredients ───────────────────────────────────
    "almond_flour":      (["% Almond%","لوز%"],                                             20.0,200.0),
    "apricot_jam":       (["% Jam%","% Apricot%","مربى%"],                                   5.0, 80.0),
    "arborio_rice":      (["% Rice%","أرز%"],                                                1.0, 20.0),
    "avocado":           (["% Avocado%","أفوكادو%"],                                         5.0, 60.0),
    "baby_eggplant":     (["% Eggplant%","% Aubergine%","باذنجان%"],                          1.0, 20.0),
    "baking_powder":     (["% Baking%","% Powder%","بيكنج%"],                                2.0, 80.0),
    "bean_sprouts":      (["% Bean%","فول%"],                                                 2.0, 30.0),
    "beans":             (["% Beans%","فاصوليا%","فول%"],                                     1.0, 20.0),
    "bechamel":          (["% Bechamel%","بشاميل%","% Cream Sauce%"],                         5.0, 50.0),
    "beef_slices":       (["% Beef%","% Luncheon%","لحمة%"],                                 20.0,150.0),
    "beef_trotters":     (["% Beef%","كوارع%"],                                              15.0,100.0),
    "beet":              (["% Beet%","% Beetroot%","بنجر%"],                                  1.0, 20.0),
    "biscuit_base":      (["% Biscuit%","% Cookie%","بسكويت%"],                               5.0, 50.0),
    "blueberries":       (["% Blueberr%","توت%"],                                            10.0,100.0),
    "bread":             (["% Balady Bread%","% Pita Bread%","% Lebanese Bread%","عيش%","خبز%"],3.0,20.0),
    "bread_roll":        (["% Roll%","% Fino%","% Petit Pain%"],                              3.0, 30.0),
    "broth":             (["% Stock%","% Broth%","% Bouillon%","مرق%"],                       1.0, 20.0),
    "buckwheat_flour":   (["% Flour%","دقيق%"],                                               0.5, 15.0),
    "butternut_squash":  (["% Squash%","% Butternut%","قرع%"],                                1.0, 20.0),
    "caesar_dressing":   (["% Dressing%","% Caesar%","صلصة%"],                                5.0, 60.0),
    "cake":              (["% Cake%","% Sponge%","كيك%"],                                     5.0, 50.0),
    "calamari":          (["% Calamari%","% Squid%","حبار%"],                                15.0,120.0),
    "cardamom":          (["% Cardamom%","% Cardamon%","هيل%","حبهان%","% Spice%"],          10.0,200.0),
    "cheese_sauce":      (["% Cheese Sauce%","% Cheese Spread%","جبنة%"],                     5.0, 80.0),
    "chicken_stock":     (["% Chicken Stock%","% Bouillon%","% Chicken Broth%","مرق دجاج%"],  1.0, 20.0),
    "chili_flakes":      (["% Chili Flakes%","% Red Pepper%","فلفل أحمر%","% Chili%"],        3.0, 60.0),
    "chili_sauce":       (["% Chili Sauce%","% Hot Sauce%","صلصة حارة%"],                     5.0, 50.0),
    "chocolate_chips":   (["% Chocolate%","شوكولاتة%"],                                      10.0,100.0),
    "chocolate_sauce":   (["% Chocolate%","% Syrup%","شوكولاتة%"],                           10.0,100.0),
    "choux_dough":       (["% Flour%","دقيق%"],                                               0.5, 15.0),
    "clotted_cream":     (["% Cream%","% Clotted%","% Ashta%","قشطة%"],                       5.0, 80.0),
    "cocoa":             (["% Cocoa%","% Cacao%","كاكاو%"],                                  10.0,100.0),
    "coffee":            (["% Coffee%","قهوة%","نسكافيه%"],                                   5.0, 80.0),
    "condensed_milk":    (["% Condensed%","% Caramel%","% Sweetened Milk%","حليب مكثف%"],     3.0, 40.0),
    "cottage_cheese":    (["% Cottage%","% Curd%","% Gebna Qareesh%","جبنة قريش%"],           5.0, 60.0),
    "cream_custard":     (["% Custard%","% Cream%","كريمة%"],                                 5.0, 80.0),
    "croutons":          (["% Crouton%","% Toast%","تواست%"],                                  3.0, 30.0),
    "crushed_wheat":     (["% Bulgur%","% Wheat%","برغل%","قمح%"],                             1.0, 20.0),
    "curry_powder":      (["% Curry%","% Spice%","كاري%","بهارات%"],                           5.0, 80.0),
    "custard":           (["% Custard%","% Vanilla Cream%","كاسترد%"],                         5.0, 60.0),
    "dough":             (["% Flour%","% Dough%","دقيق%","عجين%"],                             0.5, 20.0),
    "dough_wrappers":    (["% Dough%","% Wrapper%","% Wonton%","عجين%"],                       2.0, 30.0),
    "dried_lemon":       (["% Lemon%","% Loomi%","ليمون%"],                                    2.0, 50.0),
    "dried_yogurt":      (["% Yogurt%","% Labneh%","زبادي%","لبنة%"],                          3.0, 40.0),
    "duck":              (["% Duck%","بط%"],                                                  15.0,100.0),
    "egg_whites":        (["% Egg%","بيض%"],                                                   3.0, 25.0),
    "fava_beans_fresh":  (["% Foul%","% Fava%","فول%"],                                        1.0, 20.0),
    "fermented_milk":    (["% Yogurt%","% Fermented%","% Laban%","لبن%"],                      1.0, 20.0),
    "feta_cheese":       (["% Feta%","% White Cheese%","جبنة بيضاء%"],                         8.0, 80.0),
    "fish_fillet":       (["% Fish Fillet%","% Fillet%","فيليه سمك%","% Salmon%"],            15.0,150.0),
    "fish_stock":        (["% Fish Stock%","% Seafood%","% Stock%","مرق%"],                    1.0, 20.0),
    "freekeh":           (["% Freekeh%","% Farik%","فريكة%","% Wheat%"],                       3.0, 30.0),
    "fried_onion":       (["% Fried Onion%","% Crispy Onion%","% Onion%","بصل%"],              3.0, 60.0),
    "fruits":            (["% Fruits%","% Mixed Fruit%","فاكهة%","فواكه%"],                    1.0, 30.0),
    "garlic_sauce":      (["% Garlic%","% Toum%","ثوم%"],                                      2.0, 50.0),
    "gizzard":           (["% Gizzard%","% Chicken Gizzard%","قوانص%","% Chicken%"],           5.0, 50.0),
    "granola":           (["% Granola%","% Oat%","جرانولا%","شوفان%"],                          5.0, 60.0),
    "grape_leaves":      (["% Grape Leaves%","% Vine Leaves%","ورق عنب%"],                     3.0, 40.0),
    "green_beans":       (["% Green Bean%","% French Bean%","فاصوليا خضرا%","% Beans%"],       2.0, 25.0),
    "grilled_chicken":   (["% Chicken%","فراخ%","دجاج%"],                                      8.0, 80.0),
    "grilled_tomato":    (["% Tomato%","طماطم%"],                                              1.0, 20.0),
    "ground_pork_alt":   (["% Minced Beef%","% Beef%","لحمة مفرومة%"],                        25.0,150.0),
    "ham":               (["% Beef Luncheon%","% Luncheon%","لانشون%"],                       10.0, 80.0),
    "herring":           (["% Herring%","% Fish%","رنجة%","سمك%"],                            10.0, 80.0),
    "hot_dog_bun":       (["% Bun%","% Burger Bun%","% Bread%","خبز%"],                        3.0, 30.0),
    "ice_cream":         (["% Ice Cream%","% Gelato%","آيس كريم%"],                            5.0, 60.0),
    "intestine":         (["% Intestine%","% Tripe%","كرشة%","مصارين%"],                       5.0, 60.0),
    "jalapeño":          (["% Jalapeno%","% Pepper%","فلفل%"],                                 3.0, 40.0),
    "kebab":             (["% Minced Beef%","% Beef%","لحمة مفرومة%"],                        25.0,150.0),
    "kofta":             (["% Minced Beef%","% Beef%","لحمة مفرومة%"],                        25.0,150.0),
    "ladyfinger_biscuits":(["% Biscuit%","% Ladyfinger%","بسكويت%"],                           5.0, 50.0),
    "lamb_whole":        (["% Lamb%","ضاني%","خروف%"],                                        35.0,250.0),
    "lasagna_sheets":    (["% Lasagna%","% Pasta%","لازانيا%","مكرونة%"],                      2.0, 20.0),
    "lemongrass":        (["% Lemongrass%","% Lemon%","ليمون%"],                               2.0, 50.0),
    "lime_juice":        (["% Lime%","% Lemon%","ليمون%"],                                     2.0, 30.0),
    "lotus_biscuits":    (["% Lotus%","% Biscuit%","بسكويت%"],                                 8.0, 80.0),
    "mascarpone":        (["% Mascarpone%","% Cream Cheese%","% Cheese%","جبنة%"],            15.0,100.0),
    "mixed_fruits":      (["% Mixed Fruit%","% Tropical%","فواكه%"],                           2.0, 40.0),
    "mustard":           (["% Mustard%","مسطردة%"],                                            5.0, 50.0),
    "noodles":           (["% Noodle%","% Pasta%","مكرونة%","نودلز%"],                          1.0, 20.0),
    "nori":              (["% Nori%","% Seaweed%","نوري%","% Rice%"],                          5.0,120.0),
    "nutella":           (["% Nutella%","% Hazelnut Spread%","% Hazelnut%","نوتيلا%"],        10.0, 80.0),
    "orzo_pasta":        (["% Orzo%","% Pasta%","% Lissan%","مكرونة%"],                        2.0, 20.0),
    "pad_thai_sauce":    (["% Sauce%","% Soy%","صلصة%"],                                       3.0, 50.0),
    "pancake_batter":    (["% Flour%","% Pancake%","دقيق%"],                                   0.5, 20.0),
    "parmesan":          (["% Parmesan%","% Grated Cheese%","% Cheese%","جبنة%"],             20.0,150.0),
    "pastirma":          (["% Pastirma%","% Basturma%","بسطرمة%"],                            20.0,150.0),
    "pepperoni":         (["% Pepperoni%","% Beef Pepperoni%","% Luncheon%","بيبروني%"],       15.0,100.0),
    "pie_crust":         (["% Flour%","% Dough%","دقيق%","عجين%"],                             0.5, 20.0),
    "pigeon":            (["% Pigeon%","% Squab%","حمام%","% Chicken%"],                       10.0, 80.0),
    "pine_nuts":         (["% Pine%","% Nut%","% Mixed Nut%","صنوبر%","مكسرات%"],             15.0,300.0),
    "pistachio":         (["% Pistachio%","% Pistachios%","فستق%"],                           20.0,250.0),
    "pizza_dough":       (["% Dough%","% Flour%","% Bread%","عجين%","دقيق%"],                  0.5, 20.0),
    "popcorn_kernels":   (["% Popcorn%","% Corn%","بوشار%","ذرة%"],                            2.0, 30.0),
    "preserved_lemon":   (["% Pickled%","% Lemon%","ليمون%","مخلل%"],                          2.0, 40.0),
    "puff_pastry":       (["% Puff%","% Pastry%","% Dough%","عجين%"],                          3.0, 40.0),
    "rabbit":            (["% Rabbit%","أرنب%"],                                              10.0, 80.0),
    "radish":            (["% Radish%","فجل%"],                                                1.0, 20.0),
    "red_lentils":       (["% Lentil%","% Lentils%","عدس%"],                                   1.0, 15.0),
    "rice_noodles":      (["% Rice%","% Noodle%","% Pasta%","مكرونة%"],                        2.0, 25.0),
    "ricotta":           (["% Ricotta%","% White Cheese%","% Cottage%","جبنة%"],               8.0, 80.0),
    "ripe_banana":       (["% Banana%","موز%"],                                                1.0, 20.0),
    "rose_water":        (["% Rose Water%","% Rosewater%","ماء ورد%"],                         3.0, 40.0),
    "rosemary":          (["% Rosemary%","% Herb%","إكليل الجبل%"],                            3.0, 60.0),
    "saffron":           (["% Saffron%","% Spice%","زعفران%"],                                20.0,500.0),
    "salsa":             (["% Salsa%","% Tomato Sauce%","صلصة طماطم%"],                        3.0, 40.0),
    "salted_fish":       (["% Salted Fish%","% Fiseekh%","% Fish%","سمك%"],                    5.0, 80.0),
    "sheep_intestine":   (["% Intestine%","% Tripe%","كرشة%","مصارين%"],                       5.0, 60.0),
    "shortcrust_pastry": (["% Flour%","% Butter%","دقيق%"],                                    0.5, 20.0),
    "smoked_fish":       (["% Smoked%","% Fish%","سمك%"],                                     10.0,100.0),
    "snails":            (["% Snail%","% Escargot%","حلزون%","% Chicken%"],                    5.0, 80.0),
    "sour_cream":        (["% Cream%","% Sour%","% Labneh%","كريمة%","لبنة%"],                 5.0, 60.0),
    "spring_roll_wrappers":(["% Dough%","% Spring Roll%","% Wrapper%","عجين%"],                2.0, 30.0),
    "squid":             (["% Squid%","% Calamari%","حبار%"],                                 15.0,120.0),
    "starch":            (["% Starch%","% Cornstarch%","% Nasha%","نشا%"],                     1.0, 20.0),
    "sugarcane_juice":   (["% Sugar%","% Cane%","سكر%"],                                       0.5, 20.0),
    "sujuk":             (["% Sujuk%","% Soujouk%","% Beef Sausage%","سجق%"],                  5.0, 60.0),
    "sumac":             (["% Sumac%","% Spice%","سماق%","بهارات%"],                            3.0, 80.0),
    "sushi_rice":        (["% Sushi%","% Short Grain%","% Rice%","أرز%"],                      1.0, 20.0),
    "taco_shells":       (["% Taco%","% Tortilla%","تاكو%"],                                   5.0, 50.0),
    "tea":               (["% Tea%","شاي%"],                                                   2.0, 50.0),
    "thai_curry_paste":  (["% Curry%","% Paste%","% Spice%","كاري%"],                          5.0, 80.0),
    "thin_dough":        (["% Flour%","% Dough%","عجين%","دقيق%"],                             0.5, 20.0),
    "thyme":             (["% Thyme%","% Zaatar%","زعتر%"],                                    3.0, 60.0),
    "tikka_spices":      (["% Tikka%","% Mixed Spice%","% Spice%","بهارات%"],                  3.0, 60.0),
    "tortilla":          (["% Tortilla%","% Wrap%","تورتيلا%"],                                5.0, 40.0),
    "tortilla_chips":    (["% Tortilla%","% Chips%","تورتيلا%"],                                5.0, 50.0),
    "turkey_bacon":      (["% Turkey%","% Bacon%","% Luncheon%","لانشون%"],                   10.0, 80.0),
    "turnip":            (["% Turnip%","لفت%"],                                                1.0, 15.0),
    "vegetables":        (["% Mixed Veg%","% Vegetables%","% Fresh%","خضار%"],                 1.0, 25.0),
    "vinegar":           (["% Vinegar%","% Apple Cider%","% White Vinegar%","خل%"],            0.5, 20.0),
    "walnut":            (["% Walnut%","جوز%","مكسرات%"],                                     15.0,200.0),
    "wheat":             (["% Wheat%","% Whole Wheat%","قمح%"],                                1.0, 15.0),
    "wheat_berries":     (["% Wheat%","قمح%"],                                                 1.0, 15.0),
    "whole_wheat_flour": (["% Whole Wheat%","% Wholemeal%","دقيق أسمر%"],                      1.0, 15.0),
    "yeast":             (["% Yeast%","% Instant Yeast%","% Dry Yeast%","% Baking%","خميرة%"], 2.0, 80.0),
    "zaatar":            (["% Zaatar%","% Thyme%","زعتر%"],                                    3.0, 60.0),
}


async def run():
    async with AsyncSessionLocal() as db:
        log.info("🔍 Finding Estimated-only ingredients...")

        result = await db.execute(text("""
            SELECT ingredient_key,
                   SUM(CASE WHEN source != 'Estimated' THEN 1 ELSE 0 END) AS real_count
            FROM ingredient_product_map
            GROUP BY ingredient_key
            HAVING real_count = 0
            ORDER BY ingredient_key
        """))
        estimated_keys = [r.ingredient_key for r in result.fetchall()]
        log.info(f"Found {len(estimated_keys)} Estimated-only ingredients\n")

        fixed   = []
        skipped = []

        for key in estimated_keys:
            if key not in KEYWORD_MAP:
                skipped.append(f"{key} — no pattern defined")
                continue

            patterns, floor, ceil = KEYWORD_MAP[key]

            # Build OR conditions
            conds  = " OR ".join([f"product_name LIKE :p{i}" for i in range(len(patterns))])
            params = {f"p{i}": p for i, p in enumerate(patterns)}
            params.update({"floor": floor, "ceil": ceil})

            product = (await db.execute(text(f"""
                SELECT sku, source, product_name, price, unit_weight_g,
                       (price / unit_weight_g) * 100 AS ppg
                FROM fresh_products
                WHERE price > 0 AND unit_weight_g > 0
                  AND (price / unit_weight_g) * 100 BETWEEN :floor AND :ceil
                  AND ({conds})
                ORDER BY ppg ASC
                LIMIT 1
            """), params)).fetchone()

            if not product:
                skipped.append(f"{key} — no product in DB matching patterns")
                continue

            ppg = round(float(product.ppg), 2)

            await db.execute(text("""
                INSERT INTO ingredient_product_map
                    (ingredient_key, sku, source, product_name,
                     price_egp, unit_weight_g, price_per_100g)
                VALUES
                    (:key, :sku, :src, :name, :price, :wgt, :ppg)
                ON DUPLICATE KEY UPDATE
                    price_egp      = VALUES(price_egp),
                    unit_weight_g  = VALUES(unit_weight_g),
                    price_per_100g = VALUES(price_per_100g)
            """), {
                "key": key, "sku": product.sku, "src": product.source,
                "name": product.product_name,   "price": float(product.price),
                "wgt":  float(product.unit_weight_g), "ppg": ppg,
            })

            fixed.append(f"✅ {key:25s} → {product.product_name[:40]}  ({ppg} EGP/100g)")

        await db.commit()

        log.info("=" * 65)
        log.info(f"FIXED ({len(fixed)}):")
        for f in fixed:
            log.info(f"   {f}")

        if skipped:
            log.info(f"\nSKIPPED ({len(skipped)}) — add patterns manually:")
            for s in skipped:
                log.info(f"   ⚠️  {s}")

        log.info("=" * 65)
        log.info(f"Done: {len(fixed)} fixed, {len(skipped)} skipped.")


if __name__ == "__main__":
    asyncio.run(run())
