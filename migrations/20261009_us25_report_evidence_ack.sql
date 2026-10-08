-- US25/26: attach image evidence to a receipt report and track TTS review of HR's resolution.
-- Safe to rerun; existing report and allowance records are preserved.

SET @ack_at_count := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_PHAN_ANH'
      AND COLUMN_NAME = 'tts_acknowledged_at'
);
SET @ack_at_ddl := IF(@ack_at_count = 0,
    'ALTER TABLE PHU_CAP_PHAN_ANH ADD COLUMN tts_acknowledged_at DATETIME(6) NULL',
    'SELECT 1');
PREPARE ack_at_stmt FROM @ack_at_ddl;
EXECUTE ack_at_stmt;
DEALLOCATE PREPARE ack_at_stmt;

SET @ack_by_count := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_PHAN_ANH'
      AND COLUMN_NAME = 'tts_acknowledged_by'
);
SET @ack_by_ddl := IF(@ack_by_count = 0,
    'ALTER TABLE PHU_CAP_PHAN_ANH ADD COLUMN tts_acknowledged_by INT NULL',
    'SELECT 1');
PREPARE ack_by_stmt FROM @ack_by_ddl;
EXECUTE ack_by_stmt;
DEALLOCATE PREPARE ack_by_stmt;

SET @ack_fk_count := (
    SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_PHAN_ANH'
      AND COLUMN_NAME = 'tts_acknowledged_by' AND REFERENCED_TABLE_NAME = 'NGUOI_DUNG'
);
SET @ack_fk_ddl := IF(@ack_fk_count = 0,
    'ALTER TABLE PHU_CAP_PHAN_ANH ADD CONSTRAINT fk_phu_cap_report_acknowledged_by FOREIGN KEY (tts_acknowledged_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT',
    'SELECT 1');
PREPARE ack_fk_stmt FROM @ack_fk_ddl;
EXECUTE ack_fk_stmt;
DEALLOCATE PREPARE ack_fk_stmt;

CREATE TABLE IF NOT EXISTS PHU_CAP_PHAN_ANH_TEP (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    report_id BIGINT NOT NULL,
    storage_key VARCHAR(48) NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_phu_cap_report_file_report (report_id, id),
    CONSTRAINT fk_phu_cap_report_file_report
        FOREIGN KEY (report_id) REFERENCES PHU_CAP_PHAN_ANH(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
