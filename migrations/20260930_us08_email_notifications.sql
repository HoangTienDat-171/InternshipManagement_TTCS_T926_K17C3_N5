-- MySQL 8 migration for US08. Safe to re-run on existing Sprint 1 schemas.
USE `internship_management`;

DROP PROCEDURE IF EXISTS `_migrate_us08_email_notifications`;
DELIMITER $$
CREATE PROCEDURE `_migrate_us08_email_notifications`()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'THONG_BAO' AND column_name = 'loai'
    ) THEN
        ALTER TABLE THONG_BAO ADD COLUMN loai VARCHAR(80) NOT NULL DEFAULT 'general';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'THONG_BAO' AND column_name = 'reference_type'
    ) THEN
        ALTER TABLE THONG_BAO ADD COLUMN reference_type VARCHAR(80) NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'THONG_BAO' AND column_name = 'reference_id'
    ) THEN
        ALTER TABLE THONG_BAO ADD COLUMN reference_id VARCHAR(100) NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'THONG_BAO' AND column_name = 'thoi_gian_doc'
    ) THEN
        ALTER TABLE THONG_BAO ADD COLUMN thoi_gian_doc DATETIME NULL;
    END IF;

    CREATE TABLE IF NOT EXISTS EMAIL_OUTBOX (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        recipient_email VARCHAR(254) NOT NULL,
        subject VARCHAR(255) NOT NULL,
        body TEXT NOT NULL,
        template_type VARCHAR(80) NOT NULL,
        reference_type VARCHAR(80) NULL,
        reference_id VARCHAR(100) NULL,
        deduplication_key VARCHAR(190) NOT NULL UNIQUE,
        status ENUM('PENDING','PROCESSING','SENT','FAILED','RETRY') NOT NULL DEFAULT 'PENDING',
        retry_count INT NOT NULL DEFAULT 0,
        max_retry INT NOT NULL DEFAULT 5,
        last_error TEXT NULL,
        next_retry_at DATETIME NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        sent_at DATETIME NULL,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_email_outbox_due (status, next_retry_at, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
END$$
DELIMITER ;

CALL `_migrate_us08_email_notifications`();
DROP PROCEDURE `_migrate_us08_email_notifications`;
