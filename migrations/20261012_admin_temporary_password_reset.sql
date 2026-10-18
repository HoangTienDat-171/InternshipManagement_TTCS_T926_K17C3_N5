-- Supports expiring, single-use passwords created by an administrator reset.
-- Existing temporary-password and account data are retained unchanged.
USE `internship_management`;

DROP PROCEDURE IF EXISTS `_migrate_admin_temporary_password_reset`;
DELIMITER $$
CREATE PROCEDURE `_migrate_admin_temporary_password_reset`()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'NGUOI_DUNG'
          AND COLUMN_NAME = 'temporary_password_expires_at'
    ) THEN
        ALTER TABLE NGUOI_DUNG
            ADD COLUMN temporary_password_expires_at DATETIME NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'NGUOI_DUNG'
          AND COLUMN_NAME = 'temporary_password_consumed_at'
    ) THEN
        ALTER TABLE NGUOI_DUNG
            ADD COLUMN temporary_password_consumed_at DATETIME NULL;
    END IF;

    CREATE TABLE IF NOT EXISTS ADMIN_PASSWORD_RESET_AUDIT (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        actor_user_id INT NOT NULL,
        target_user_id INT NOT NULL,
        outcome VARCHAR(24) NOT NULL,
        created_at DATETIME(6) NOT NULL,
        KEY idx_admin_password_reset_target_created (target_user_id, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
END$$
DELIMITER ;

CALL `_migrate_admin_temporary_password_reset`();
DROP PROCEDURE `_migrate_admin_temporary_password_reset`;
