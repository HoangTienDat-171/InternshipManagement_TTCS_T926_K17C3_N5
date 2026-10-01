-- MySQL 8 migration: allow multiple contract files for one internship profile.
-- Safe to re-run. Existing contract rows and their statuses are preserved.
USE `internship_management`;

DROP PROCEDURE IF EXISTS `_migrate_us09_multiple_contracts`;
DELIMITER $$
CREATE PROCEDURE `_migrate_us09_multiple_contracts`()
BEGIN
    DECLARE profile_unique_key VARCHAR(64) DEFAULT NULL;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'HOP_DONG_THUC_TAP'
          AND index_name = 'idx_hop_dong_profile'
    ) THEN
        ALTER TABLE HOP_DONG_THUC_TAP ADD INDEX idx_hop_dong_profile (ma_ho_so);
    END IF;

    SELECT MIN(index_name) INTO profile_unique_key
    FROM (
        SELECT index_name
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = 'HOP_DONG_THUC_TAP'
          AND non_unique = 0
        GROUP BY index_name
        HAVING COUNT(*) = 1 AND MAX(column_name) = 'ma_ho_so'
    ) AS profile_unique_keys;

    IF profile_unique_key IS NOT NULL THEN
        SET @migration_sql = CONCAT(
            'ALTER TABLE `HOP_DONG_THUC_TAP` DROP INDEX `',
            REPLACE(profile_unique_key, '`', '``'),
            '`'
        );
        PREPARE migration_statement FROM @migration_sql;
        EXECUTE migration_statement;
        DEALLOCATE PREPARE migration_statement;
    END IF;
END$$
DELIMITER ;

CALL `_migrate_us09_multiple_contracts`();
DROP PROCEDURE `_migrate_us09_multiple_contracts`;
