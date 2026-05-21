-- migration_chat_history.sql
-- Run: mysql -u root -p2474 nutribudget < migration_chat_history.sql

USE nutribudget;

CREATE TABLE IF NOT EXISTS chat_history (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    user_id    INT          NOT NULL,
    role       VARCHAR(20)  NOT NULL,   -- 'user' | 'assistant'
    content    TEXT         NOT NULL,
    created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_created (created_at)
);

SELECT 'chat_history table ready' AS status;
