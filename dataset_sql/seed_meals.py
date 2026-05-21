import pandas as pd
from sqlalchemy import create_engine

# شيل كلمة YOUR_PASSWORD وحط الباسورد الحقيقية بتاعتك
DATABASE_URL = "mysql+pymysql://root:2474@localhost:3306/nutribudget"
def seed_database():
    print("⏳ جاري قراءة الداتاسيت...")
    
    # اسم الملف الإكسيل بتاعك
    excel_file = "egyptian_meals.xlsx"
    
    try:
        # 🛠️ السحر هنا: هنستخدم read_excel بدل read_csv
        # الإكسيل مش بيحتاج تفاصيل الـ encoding والـ separators المعقدة
        df = pd.read_excel(excel_file)
        
        # لو في صفوف فاضية خالص نمسحها
        df = df.dropna(how='all')
        df = df.fillna("")
        
        print(f"✅ تم قراءة {len(df)} وجبة مصرية بنجاح.")
        print("⏳ جاري الحقن في قاعدة البيانات...")

        engine = create_engine(DATABASE_URL)
        df.to_sql(name='egyptian_meals_dataset', con=engine, if_exists='append', index=False)
        
        print("🚀 عاااش! الداتا كلها اترفعت، والسيستم دلوقتي جاهز يشتغل.")
        
    except Exception as e:
        print(f"❌ المحاولة فشلت: {e}")

if __name__ == "__main__":
    seed_database()