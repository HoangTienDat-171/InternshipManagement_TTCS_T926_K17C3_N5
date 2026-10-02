USE `internship_management`;

SET @us16_schema = DATABASE();

SET @us16_sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = @us16_schema
          AND TABLE_NAME = 'NHIEM_VU_THUC_TAP'
          AND COLUMN_NAME = 'progress_percent'
    ),
    'SELECT 1',
    'ALTER TABLE NHIEM_VU_THUC_TAP ADD COLUMN progress_percent TINYINT UNSIGNED NOT NULL DEFAULT 0 AFTER trang_thai'
);
PREPARE us16_stmt FROM @us16_sql;
EXECUTE us16_stmt;
DEALLOCATE PREPARE us16_stmt;

SET @us16_sql = IF(
    EXISTS(
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = @us16_schema
          AND TABLE_NAME = 'NHIEM_VU_THUC_TAP'
          AND COLUMN_NAME = 'progress_note'
    ),
    'SELECT 1',
    'ALTER TABLE NHIEM_VU_THUC_TAP ADD COLUMN progress_note VARCHAR(2000) NULL AFTER progress_percent'
);
PREPARE us16_stmt FROM @us16_sql;
EXECUTE us16_stmt;
DEALLOCATE PREPARE us16_stmt;

CREATE TABLE IF NOT EXISTS LICH_SU_TIEN_DO_CONG_VIEC (
    ma_lich_su BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_nhiem_vu BIGINT NOT NULL,
    updated_by INT NOT NULL,
    old_progress TINYINT UNSIGNED NOT NULL,
    new_progress TINYINT UNSIGNED NOT NULL,
    old_status ENUM('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED') NOT NULL,
    new_status ENUM('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED') NOT NULL,
    note VARCHAR(2000) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_task_progress_history (ma_nhiem_vu, created_at, ma_lich_su),
    KEY idx_task_progress_actor (updated_by),
    CONSTRAINT fk_task_progress_history_task
        FOREIGN KEY (ma_nhiem_vu) REFERENCES NHIEM_VU_THUC_TAP(ma_nhiem_vu) ON DELETE RESTRICT,
    CONSTRAINT fk_task_progress_history_actor
        FOREIGN KEY (updated_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
