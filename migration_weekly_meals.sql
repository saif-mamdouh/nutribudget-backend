USE nutribudget;

ALTER TABLE meal_plans
  ADD COLUMN meals_json LONGTEXT NULL COMMENT 'JSON array of planned meals with day/slot/recipe info',
  ADD COLUMN plan_name VARCHAR(100) NULL COMMENT 'User-friendly plan name';

SELECT 'migration_weekly_meals done' AS status;