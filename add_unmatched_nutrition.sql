SET NAMES utf8mb4;
USE nutribudget;

INSERT IGNORE INTO nutrition_facts
  (normalized_name, display_name, calories_per_100g, protein_g, carbs_g, fats_g, fiber_g, data_source)
VALUES

-- ── Juices (all brands map to these) ──────────────────────────────────────
('apple_juice',          'عصير تفاح',          46,  0.1, 11.0,  0.1, 0.2, 'manual'),
('mango_juice',          'عصير مانجو',          60,  0.4, 15.0,  0.2, 0.4, 'manual'),
('orange_juice',         'عصير برتقال',         45,  0.7, 10.0,  0.2, 0.2, 'manual'),
('guava_juice',          'عصير جوافة',          50,  0.6, 12.0,  0.3, 0.5, 'manual'),
('cocktail_juice',       'عصير كوكتيل',         52,  0.4, 13.0,  0.1, 0.3, 'manual'),
('pineapple_juice',      'عصير أناناس',         53,  0.3, 13.0,  0.1, 0.2, 'manual'),
('grape_juice',          'عصير عنب',            60,  0.4, 15.0,  0.1, 0.1, 'manual'),
('peach_juice',          'عصير خوخ',            57,  0.5, 14.0,  0.1, 1.0, 'manual'),
('pomegranate_juice',    'عصير رمان',           54,  0.2, 13.0,  0.3, 0.1, 'manual'),
('strawberry_juice',     'عصير فراولة',         36,  0.5,  8.0,  0.2, 0.5, 'manual'),
('lemon_mint_juice',     'عصير ليمون بالنعناع', 25,  0.3,  6.0,  0.1, 0.1, 'manual'),
('carrot_juice',         'عصير جزر',            40,  0.9,  9.0,  0.2, 0.8, 'manual'),
('carrot_orange_juice',  'عصير جزر وبرتقال',    42,  0.8, 10.0,  0.2, 0.5, 'manual'),
('banana_strawberry_juice','عصير موز وفراولة',  65,  0.8, 15.0,  0.3, 0.5, 'manual'),
('mixed_berries_juice',  'عصير توت مشكل',       45,  0.5, 11.0,  0.2, 0.5, 'manual'),
('tangerine_juice',      'عصير يوسفي',          43,  0.7, 10.0,  0.2, 0.1, 'manual'),
('kiwi_juice',           'عصير كيوي',           61,  1.1, 15.0,  0.5, 3.0, 'manual'),
('hibiscus_juice',       'عصير كركديه',         20,  0.0,  5.0,  0.0, 0.0, 'manual'),
('tamarind_juice',       'عصير تمر هندي',       40,  0.3,  9.0,  0.1, 0.0, 'manual'),
('sobia_juice',          'سوبيا',               80,  1.0, 18.0,  1.0, 0.0, 'manual'),
('doum_juice',           'عصير دوم',            45,  0.5, 11.0,  0.2, 0.0, 'manual'),
('carob_juice',          'عصير خروب',           50,  0.5, 12.0,  0.1, 0.0, 'manual'),
('beet_juice',           'عصير بنجر',           43,  1.6, 10.0,  0.2, 0.0, 'manual'),
('dates_milk_juice',     'عصير تمر باللبن',    120,  3.0, 22.0,  2.5, 0.5, 'manual'),

-- ── Yogurt types (branded → generic) ──────────────────────────────────────
('flavored_yogurt',      'زبادي بالفاكهة',      90,  3.5, 14.0,  2.0, 0.0, 'manual'),
('greek_yogurt',         'زبادي يوناني',         97,  9.0,  4.0,  5.0, 0.0, 'manual'),
('light_yogurt',         'زبادي لايت',           50,  4.5,  6.0,  0.5, 0.0, 'manual'),
('stirred_yogurt',       'زبادي مخلوط',          65,  3.5,  8.0,  2.0, 0.0, 'manual'),
('yogurt_drink',         'مشروب زبادي',          70,  3.0, 12.0,  1.0, 0.0, 'manual'),
('rayeb_milk',           'لبن رايب',             65,  3.5,  5.0,  3.3, 0.0, 'manual'),
('rice_pudding',         'أرز باللبن',          130,  3.5, 22.0,  3.0, 0.0, 'manual'),
('vanilla_pudding',      'بودينج فانيليا',      120,  3.0, 20.0,  3.0, 0.0, 'manual'),
('caramel_pudding',      'كريم كراميل',         130,  3.0, 21.0,  3.5, 0.0, 'manual'),
('protein_yogurt',       'زبادي بروتين',        100, 15.0,  6.0,  0.5, 0.0, 'manual'),

-- ── Milk types ─────────────────────────────────────────────────────────────
('full_cream_milk',      'لبن كامل الدسم',       61,  3.2,  4.8,  3.3, 0.0, 'manual'),
('skimmed_milk',         'لبن خالي الدسم',       35,  3.5,  5.0,  0.1, 0.0, 'manual'),
('semi_skimmed_milk',    'لبن نص دسم',           46,  3.3,  4.9,  1.5, 0.0, 'manual'),
('chocolate_milk',       'لبن بالشوكولاتة',      83,  3.4, 12.0,  2.3, 0.3, 'manual'),
('flavored_milk',        'لبن بالنكهات',         75,  3.0, 12.0,  1.5, 0.0, 'manual'),
('lactose_free_milk',    'لبن خالي اللاكتوز',    61,  3.2,  4.8,  3.3, 0.0, 'manual'),
('oat_milk',             'لبن شوفان',             45,  1.0,  7.0,  1.5, 1.0, 'manual'),

-- ── Butter & Ghee types ────────────────────────────────────────────────────
('buffalo_ghee',         'سمن جاموسي',          900,  0.0,  0.0,100.0, 0.0, 'manual'),
('beef_ghee',            'سمن بقري',            900,  0.0,  0.0,100.0, 0.0, 'manual'),
('whipping_cream',       'كريمة للخفق',         300,  2.5,  3.0, 30.0, 0.0, 'manual'),
('sour_cream',           'كريمة حامضة',         193,  2.4,  4.6, 19.0, 0.0, 'manual'),
('cooking_cream',        'كريمة للطبخ',         150,  2.5,  4.0, 14.0, 0.0, 'manual'),
('double_cream',         'كريمة مزدوجة',        350,  2.0,  2.5, 37.0, 0.0, 'manual'),

-- ── Bread types ────────────────────────────────────────────────────────────
('whole_wheat_bread',    'خبز قمح كامل',        247,  9.0, 44.0,  3.4, 6.0, 'manual'),
('barley_bread',         'خبز شعير',            220,  8.0, 44.0,  2.0, 8.0, 'manual'),
('Lebanese_bread',       'خبز لبناني',          265,  9.0, 54.0,  1.0, 2.0, 'manual'),
('shamy_bread',          'خبز شامي',            270,  9.0, 55.0,  1.5, 2.0, 'manual'),
('fino_bread',           'خبز فينو',            290, 10.0, 55.0,  4.0, 1.5, 'manual'),
('toast_whole_wheat',    'تواست قمح كامل',      240,  9.0, 42.0,  3.5, 5.0, 'manual'),
('tortilla',             'تورتيلا',             300,  8.0, 50.0,  7.0, 2.0, 'manual'),
('hamburger_bun',        'خبز همبرغر',          279,  9.0, 51.0,  4.5, 2.0, 'manual'),
('croissant',            'كرواسون',             406, 8.0,  45.0, 21.0, 1.5, 'manual'),
('feteer_meshaltet',     'فطير مشلتت',          400,  8.0, 40.0, 22.0, 1.0, 'manual'),
('kahk',                 'كعك',                 450,  7.0, 60.0, 20.0, 2.0, 'manual'),
('kunafa',               'كنافة',               260,  5.0, 35.0, 12.0, 1.0, 'manual'),
('qatayef',              'قطايف',               220,  5.0, 35.0,  8.0, 1.5, 'manual'),
('meshabek',             'مشبك',                380,  3.0, 65.0, 13.0, 0.5, 'manual'),

-- ── Pickles & Olives (Olivetta brands) ────────────────────────────────────
('mixed_pickles',        'طرشي مشكل',            15,  0.6,  3.0,  0.2, 1.5, 'manual'),
('stuffed_olives',       'زيتون محشي',          145,  1.0,  4.0, 15.0, 2.0, 'manual'),
('kalamata_olives',      'زيتون كالاماتا',       185,  1.5,  5.0, 19.0, 2.5, 'manual'),
('grape_leaves',         'ورق عنب',              95,  3.0, 17.0,  2.0, 3.0, 'manual'),
('pearl_onion_pickled',  'بصل صغير مخلل',        25,  0.8,  5.0,  0.1, 1.0, 'manual'),
('jalapeno',             'جالابينيو',             29,  1.4,  6.0,  0.4, 2.0, 'manual'),
('harissa',              'هريسة',                50,  1.5,  8.0,  1.5, 2.0, 'manual'),
('sun_dried_tomato',     'طماطم مجففة',          258, 14.0, 56.0,  3.0, 12.0,'manual'),

-- ── Specialty / Egyptian drinks ────────────────────────────────────────────
('nescafe',              'نسكافيه',               2,  0.3,  0.4,  0.0, 0.0, 'manual'),
('custard_powder',       'كاسترد باودر',         350,  3.0, 85.0,  1.0, 0.0, 'manual'),
('instant_yeast',        'خميرة فورية',          325, 41.0, 41.0,  7.0, 0.0, 'manual'),
('dough_wrappers',       'عجينة للف',            290,  7.5, 52.0,  5.0, 1.5, 'manual'),
('intestine_masareen',   'مصارين',               150, 14.0,  0.0,  9.0, 0.0, 'manual'),
('taco_shells',          'قشرة تاكو',            483,  7.0, 62.0, 23.0, 3.0, 'manual'),

-- ── Fresh fruits (extra variants) ─────────────────────────────────────────
('peach',                'خوخ',                  39,  0.9, 10.0,  0.3, 1.5, 'manual'),
('guava',                'جوافة',                68,  2.6, 14.0,  1.0, 5.4, 'manual'),
('cantaloupe',           'شمام',                 34,  0.8,  8.0,  0.2, 0.9, 'manual'),
('kiwi',                 'كيوي',                 61,  1.1, 15.0,  0.5, 3.0, 'manual'),
('pineapple',            'أناناس',               50,  0.5, 13.0,  0.1, 1.4, 'manual'),
('pear',                 'إجاص',                 57,  0.4, 15.0,  0.1, 3.1, 'manual'),
('african_pear',         'إجاص أفريقي',          57,  0.4, 15.0,  0.1, 3.1, 'manual'),
('dried_apricot',        'مشمش مجفف',           241,  3.4, 63.0,  0.5, 7.3, 'manual'),
('raisins',              'زبيب',                299,  3.1, 79.0,  0.5, 3.7, 'manual'),
('dried_figs',           'تين مجفف',            249,  3.3, 64.0,  0.9, 9.8, 'manual'),
('hazelnut',             'بندق',                628, 15.0, 17.0, 61.0, 9.7, 'manual'),
('coconut_flakes',       'رقائق جوز الهند',     354,  3.3, 15.0, 33.0, 9.0, 'manual'),
('carob',                'خروب',                222,  4.6, 49.0,  0.7,40.0, 'manual'),

-- ── Snacks & Protein bars ──────────────────────────────────────────────────
('protein_bar',          'بروتين بار',           350, 20.0, 38.0, 12.0, 3.0, 'manual'),
('granola_bar',          'جرانولا بار',          400,  8.0, 60.0, 15.0, 4.0, 'manual'),
('hummus_chips',         'شيبس حمص',            450,  8.0, 55.0, 22.0, 5.0, 'manual'),
('lentil_chips',         'شيبس عدس',            390,  9.0, 58.0, 13.0, 5.0, 'manual'),
('rice_cake',            'كيك أرز',             387,  8.0, 82.0,  3.0, 2.0, 'manual'),
('baked_chips',          'شيبس مخبوز',          430,  6.0, 60.0, 18.0, 3.0, 'manual'),
('oat_biscuits',         'بسكويت شوفان',        430,  7.0, 65.0, 16.0, 4.0, 'manual'),
('digestive_biscuits',   'بسكويت دايجستف',      480,  7.0, 62.0, 23.0, 4.0, 'manual'),
('peanut_snack',         'سناك فول سوداني',     567, 26.0, 16.0, 49.0, 8.0, 'manual'),

-- ── Water ──────────────────────────────────────────────────────────────────
('mineral_water',        'مياه معدنية',           0,  0.0,  0.0,  0.0, 0.0, 'manual'),

-- ── Vegetables (extra variants) ───────────────────────────────────────────
('sweet_corn',           'ذرة حلوة',             86,  3.2, 19.0,  1.2, 2.0, 'manual'),
('colored_peppers',      'فلفل ملون',             31,  1.0,  6.0,  0.3, 2.0, 'manual'),
('red_cabbage',          'كرنب أحمر',             31,  1.5,  7.0,  0.1, 2.1, 'manual'),
('baby_potatoes',        'بطاطس صغيرة',           77,  2.0, 17.0,  0.1, 2.2, 'manual'),
('fresh_ginger',         'جنزبيل طازج',           80,  1.8, 18.0,  0.8, 2.0, 'manual'),
('leek',                 'كراث',                  61,  1.5, 14.0,  0.3, 1.8, 'manual'),
('red_onion',            'بصل أحمر',              40,  1.1,  9.3,  0.1, 1.7, 'manual');

-- Verify
SELECT COUNT(*) AS total FROM nutrition_facts;
