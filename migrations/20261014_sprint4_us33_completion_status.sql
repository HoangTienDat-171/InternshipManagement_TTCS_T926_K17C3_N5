-- US33: track completion independently for each approved program participation.
-- Idempotent migration for existing MySQL databases; newly created tables get
-- these columns from backend/app/database.py.
DROP PROCEDURE IF EXISTS `_migrate_sprint4_us33_completion`;
DELIMITER $$
CREATE PROCEDURE `_migrate_sprint4_us33_completion`()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'UNG_TUYEN_CHUONG_TRINH'
          AND COLUMN_NAME = 'completion_status'
    ) THEN
        ALTER TABLE UNG_TUYEN_CHUONG_TRINH
            ADD COLUMN completion_status ENUM('ChuaHoanThanh','HoanThanh')
            NOT NULL DEFAULT 'ChuaHoanThanh' AFTER nguoi_xet_duyet;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'UNG_TUYEN_CHUONG_TRINH'
          AND COLUMN_NAME = 'completion_updated_by'
    ) THEN
        ALTER TABLE UNG_TUYEN_CHUONG_TRINH
            ADD COLUMN completion_updated_by INT NULL AFTER completion_status;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'UNG_TUYEN_CHUONG_TRINH'
          AND COLUMN_NAME = 'completion_updated_at'
    ) THEN
        ALTER TABLE UNG_TUYEN_CHUONG_TRINH
            ADD COLUMN completion_updated_at DATETIME NULL AFTER completion_updated_by;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'UNG_TUYEN_CHUONG_TRINH'
          AND COLUMN_NAME = 'completion_updated_by' AND REFERENCED_TABLE_NAME = 'NGUOI_DUNG'
    ) THEN
        ALTER TABLE UNG_TUYEN_CHUONG_TRINH
            ADD CONSTRAINT fk_application_completion_actor
            FOREIGN KEY (completion_updated_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL;
    END IF;
END$$
DELIMITER ;

CALL `_migrate_sprint4_us33_completion`();
DROP PROCEDURE IF EXISTS `_migrate_sprint4_us33_completion`;
