# ==========================================================
# NutriBudget EG Dataset Image Collector (Google Images  Bing)
# Collect images for each food class automatically
# Best for training YOLO  CLIP  CNN models
# ==========================================================

# Install
# pip install icrawler pandas tqdm

import os
import re
import pandas as pd
from tqdm import tqdm
from icrawler.builtin import GoogleImageCrawler

# ==========================================================
# FOOD CLASSES
# ==========================================================

foods_text = 
كشري مصري بيتي
فول مدمس
طعمية
ملوخية بالأرنب
كوارع
حمام محشي
مسقعة
بامية باللحمة
أرز بالشعرية
عيش بلدي
شوربة عدس
فراخ مشوية
كباب حلة
لحمة بالبصل
سمك مقلي
سمك بالطحينة
بيض بالطماطم
عجة
حمص بالطحينة
متبل
ورق عنب
محشي كوسة
محشي فلفل
مكرونة بشاميل
شاكشوكة
كفتة
فتة
فتة لحمة
سلطة خضرا
طاجن لحمة بطاطس
طاجن فراخ
أرز أحمر
فراخ بالكريمة
صيادية سمك
شوربة خضار
شوربة فراخ
حواوشي
بطاطس بالبيض
إسكالوب دجاج
كبدة اسكندراني
بط محشي
جبنة بيضاء
كنافة
أم علي
بسبوسة
مهلبية
قطايف
شاورما دجاج
شاورما لحمة
برجر لحمة
بيتزا مارجريتا
بيتزا بيبروني
تشيكن ألفريدو
كشري مصري


food_classes = [x.strip() for x in foods_text.split(n) if x.strip()]

# ==========================================================
# SETTINGS
# ==========================================================

DOWNLOAD_PER_CLASS = 150      # عدد الصور لكل صنف
ROOT_DIR = nutribudget_food_dataset

os.makedirs(ROOT_DIR, exist_ok=True)

# ==========================================================
# CLEAN FOLDER NAME
# ==========================================================

def clean_name(name)
    name = re.sub(r'[]', , name)
    return name.strip()

# ==========================================================
# DOWNLOAD LOOP
# ==========================================================

for food in tqdm(food_classes)

    folder = os.path.join(ROOT_DIR, clean_name(food))
    os.makedirs(folder, exist_ok=True)

    crawler = GoogleImageCrawler(
        storage={root_dir folder}
    )

    query = f{food} food dish meal

    try
        crawler.crawl(
            keyword=query,
            max_num=DOWNLOAD_PER_CLASS,
            min_size=(256,256),
            max_size=None
        )
        print(f✅ Done {food})

    except Exception as e
        print(f❌ Error {food} {e})

print(=======================================)
print(ALL DOWNLOADS COMPLETE)
print(Dataset folder, ROOT_DIR)
print(=======================================)