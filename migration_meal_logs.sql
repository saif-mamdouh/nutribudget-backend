-- migration_meal_logs.sql
USE nutribudget;

CREATE TABLE IF NOT EXISTS meal_logs (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT           NOT NULL,
    plan_id     INT           NULL,
    recipe_id   INT           NULL,
    recipe_name VARCHAR(255)  NOT NULL,
    meal_type   VARCHAR(20)   NULL,
    day_num     INT           NULL,      -- day in weekly plan (1-7)
    calories    DECIMAL(8,2)  DEFAULT 0,
    protein_g   DECIMAL(8,2)  DEFAULT 0,
    carbs_g     DECIMAL(8,2)  DEFAULT 0,
    fats_g      DECIMAL(8,2)  DEFAULT 0,
    cost_egp    DECIMAL(8,2)  DEFAULT 0,
    logged_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_date (user_id, logged_at),
    INDEX idx_plan (plan_id)
);

SELECT 'meal_logs table ready' AS status;
