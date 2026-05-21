-- ============================================================
-- migration_needs_retraining.sql
-- Active Learning Loop: stores user corrections for future retraining
-- Run ONCE:
--   mysql -u root -p2474 nutribudget < migration_needs_retraining.sql
-- ============================================================

USE nutribudget;

CREATE TABLE IF NOT EXISTS needs_retraining (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT NOT NULL,
    predicted_class  VARCHAR(50)  NOT NULL,
    correct_class    VARCHAR(50)  NOT NULL,
    confidence       FLOAT        DEFAULT 0.0,
    image_base64     TEXT,
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_correct_class (correct_class),
    INDEX idx_created (created_at)
);

SELECT 'needs_retraining table created' AS status;
