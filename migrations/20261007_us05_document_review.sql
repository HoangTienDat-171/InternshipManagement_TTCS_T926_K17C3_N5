-- US05: persist reviewer, optional review reason, and server decision time.
-- Existing rows retain NULL metadata; no historical reviewer or time is fabricated.
-- Conditional DDL keeps this safe when init_db() has already applied the additive schema update.

SET @us05_sql = IF(
    EXISTS (SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'TAI_LIEU_HO_SO' AND COLUMN_NAME = 'reviewed_by'),
    'SELECT 1',
    'ALTER TABLE TAI_LIEU_HO_SO ADD COLUMN reviewed_by INT NULL'
);
PREPARE us05_stmt FROM @us05_sql;
EXECUTE us05_stmt;
DEALLOCATE PREPARE us05_stmt;

SET @us05_sql = IF(
    EXISTS (SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'TAI_LIEU_HO_SO' AND COLUMN_NAME = 'review_reason'),
    'SELECT 1',
    'ALTER TABLE TAI_LIEU_HO_SO ADD COLUMN review_reason TEXT NULL'
);
PREPARE us05_stmt FROM @us05_sql;
EXECUTE us05_stmt;
DEALLOCATE PREPARE us05_stmt;

SET @us05_sql = IF(
    EXISTS (SELECT 1 FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'TAI_LIEU_HO_SO' AND COLUMN_NAME = 'reviewed_at'),
    'SELECT 1',
    'ALTER TABLE TAI_LIEU_HO_SO ADD COLUMN reviewed_at DATETIME NULL'
);
PREPARE us05_stmt FROM @us05_sql;
EXECUTE us05_stmt;
DEALLOCATE PREPARE us05_stmt;

SET @us05_sql = IF(
    EXISTS (SELECT 1 FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'TAI_LIEU_HO_SO' AND INDEX_NAME = 'idx_tai_lieu_reviewed_by'),
    'SELECT 1',
    'ALTER TABLE TAI_LIEU_HO_SO ADD KEY idx_tai_lieu_reviewed_by (reviewed_by)'
);
PREPARE us05_stmt FROM @us05_sql;
EXECUTE us05_stmt;
DEALLOCATE PREPARE us05_stmt;

SET @us05_sql = IF(
    EXISTS (SELECT 1 FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'TAI_LIEU_HO_SO'
              AND COLUMN_NAME = 'reviewed_by' AND REFERENCED_TABLE_NAME = 'NGUOI_DUNG'),
    'SELECT 1',
    'ALTER TABLE TAI_LIEU_HO_SO ADD CONSTRAINT fk_tai_lieu_reviewed_by FOREIGN KEY (reviewed_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL'
);
PREPARE us05_stmt FROM @us05_sql;
EXECUTE us05_stmt;
DEALLOCATE PREPARE us05_stmt;
