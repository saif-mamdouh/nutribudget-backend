USE nutribudget;

CREATE TABLE IF NOT EXISTS user_interactions (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT          NOT NULL,
    recipe_name      VARCHAR(255) NOT NULL,
    interaction_type VARCHAR(50)  NOT NULL DEFAULT 'liked',
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_user      (user_id),
    INDEX idx_recipe    (recipe_name),
    INDEX idx_user_type (user_id, interaction_type)
);

DESCRIBE user_interactions;
SELECT 'user_interactions created' AS status;
