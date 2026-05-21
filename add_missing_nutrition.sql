USE nutribudget;
INSERT IGNORE INTO nutrition_facts
  (normalized_name, display_name, calories_per_100g, protein_g, carbs_g, fats_g, fiber_g, data_source)
VALUES
('ground_lamb',   'ضاني مفروم',     294, 25.0, 0.0, 21.0, 0, 'manual'),
('minced_lamb',   'ضاني مفروم',     294, 25.0, 0.0, 21.0, 0, 'manual'),
('lamb_ribs',     'ريش ضاني',       294, 25.0, 0.0, 21.0, 0, 'manual'),
('lamb_chops',    'كوتليت ضاني',    294, 25.0, 0.0, 21.0, 0, 'manual'),
('lamb_whole',    'خروف كامل',      294, 25.0, 0.0, 21.0, 0, 'manual'),
('ground_beef',   'لحمة مفرومة',    254, 26.0, 0.0, 17.0, 0, 'manual'),
('fish_fillet',   'فيليه سمك',       96, 20.0, 0.0,  2.0, 0, 'manual'),
('toast_bread',   'تواست',          265,  8.0,50.0,  3.0, 0, 'manual'),
('bread_roll',    'رول خبز',        289, 10.0,55.0,  4.2, 0, 'manual'),
('kofta',         'كفتة',           250, 20.0, 2.0, 18.0, 0, 'manual'),
('garlic_sauce',  'صلصة ثومية',     150,  1.5, 5.0, 14.0, 0, 'manual'),
('spices',        'بهارات',         263,  6.1,72.0,  9.0, 0, 'manual'),
('dried_yogurt',  'لبن جافة',        60,  3.5, 5.0,  3.3, 0, 'manual'),
('freekeh',       'فريكة',          347, 12.0,72.0,  1.5, 0, 'manual'),
('dried_prunes',  'برقوق مجفف',     240,  2.2,63.0,  0.4, 0, 'manual'),
('clotted_cream', 'قشطة',           440,  3.0, 4.0, 47.0, 0, 'manual'),
('cottage_cheese','جبنة قريش',       98, 11.0, 3.4,  4.3, 0, 'manual'),
('romi_cheese',   'جبنة رومي',      400, 26.0, 0.0, 33.0, 0, 'manual'),
('tuna_canned',   'تونة معلبة',     116, 26.0, 0.0,  1.0, 0, 'manual'),
('zaatar',        'زعتر',           265, 10.0,56.0,  7.0, 0, 'manual'),
('sumac',         'سماق',           315, 11.0,73.0,  5.0, 0, 'manual'),
('radish',        'فجل',             16,  0.7, 3.4,  0.1, 0, 'manual'),
('nuts',          'مكسرات',         600, 20.0,20.0, 50.0, 0, 'manual'),
('wheat',         'قمح',            339, 14.0,71.0,  2.5, 0, 'manual'),
('chili_flakes',  'فلفل أحمر مجفف', 282, 10.0,56.0,  7.0, 0, 'manual'),
('vanilla_extract','خلاصة فانيليا',  288,  0.1,13.0,  0.1, 0, 'manual'),
('oil',           'زيت',            884,  0.0, 0.0,100.0, 0, 'manual'),
('vegetables',    'خضار',            65,  3.0,14.0,  0.5, 0, 'manual'),
('egg',           'بيضة',           155, 13.0, 1.1, 11.0, 0, 'manual');

SELECT COUNT(*) AS total FROM nutrition_facts;
