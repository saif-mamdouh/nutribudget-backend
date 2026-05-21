-- ============================================================
-- create_active_learning.sql
-- Active Learning table for Vision AI corrections
-- ============================================================

USE nutribudget;

CREATE TABLE IF NOT EXISTS needs_retraining (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT           NOT NULL,
    predicted_class VARCHAR(100)  NOT NULL,
    correct_class   VARCHAR(100)  NOT NULL,
    confidence      FLOAT         DEFAULT 0.0,
    image_base64    TEXT,                           -- thumbnail only (500 chars)
    created_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_predicted  (predicted_class),
    INDEX idx_correct    (correct_class),
    INDEX idx_user       (user_id),
    INDEX idx_created    (created_at),
    INDEX idx_pair       (predicted_class, correct_class)   -- for boost queries
);

-- ── Verify ────────────────────────────────────────────────────────────────────
DESCRIBE needs_retraining;
SELECT 'Table created successfully ✅' AS status;
