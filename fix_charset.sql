-- fix_charset.sql
-- Run once to fix Arabic encoding in MySQL

USE nutribudget;

-- Fix database charset
ALTER DATABASE nutribudget CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Fix recipes table
ALTER TABLE recipes
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Fix fresh_products table  
ALTER TABLE fresh_products
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Fix meal_plans table
ALTER TABLE meal_plans
  CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

SELECT 'charset fix done ✅' AS status;
