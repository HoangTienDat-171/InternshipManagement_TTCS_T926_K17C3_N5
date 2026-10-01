-- Enables one-time temporary passwords with a mandatory first-login change.
-- Run this once against the configured MySQL schema before creating new accounts.
USE `internship_management`;

DROP PROCEDURE IF EXISTS `_migrate_temporary_passwords`;
DELIMITER $$
CREATE PROCEDURE `_migrate_temporary_passwords`()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'NGUOI_DUNG'
          AND COLUMN_NAME = 'must_change_password'
    ) THEN
        ALTER TABLE NGUOI_DUNG
            ADD COLUMN must_change_password TINYINT(1) NOT NULL DEFAULT 0 AFTER mat_khau;
    END IF;
END$$
DELIMITER ;

CALL `_migrate_temporary_passwords`();
DROP PROCEDURE `_migrate_temporary_passwords`;
