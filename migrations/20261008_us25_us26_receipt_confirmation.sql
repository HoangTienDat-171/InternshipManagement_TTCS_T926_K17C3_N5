-- US25/26 receipt acknowledgment and append-only resolution history.
-- Existing rows become ChoXacNhan (never implicitly treated as paid).
-- This migration is additive and safe to re-run after backing up the configured database.

SET @allowance_column_count := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_THUC_TAP' AND COLUMN_NAME = 'trang_thai_nhan'
);
SET @allowance_ddl := IF(@allowance_column_count = 0,
    "ALTER TABLE PHU_CAP_THUC_TAP ADD COLUMN trang_thai_nhan VARCHAR(24) NOT NULL DEFAULT 'ChoXacNhan'",
    'SELECT 1');
PREPARE allowance_stmt FROM @allowance_ddl; EXECUTE allowance_stmt; DEALLOCATE PREPARE allowance_stmt;

SET @allowance_column_count := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_THUC_TAP' AND COLUMN_NAME = 'xac_nhan_boi'
);
SET @allowance_ddl := IF(@allowance_column_count = 0,
    'ALTER TABLE PHU_CAP_THUC_TAP ADD COLUMN xac_nhan_boi INT NULL', 'SELECT 1');
PREPARE allowance_stmt FROM @allowance_ddl; EXECUTE allowance_stmt; DEALLOCATE PREPARE allowance_stmt;

SET @allowance_column_count := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_THUC_TAP' AND COLUMN_NAME = 'xac_nhan_luc'
);
SET @allowance_ddl := IF(@allowance_column_count = 0,
    'ALTER TABLE PHU_CAP_THUC_TAP ADD COLUMN xac_nhan_luc DATETIME(6) NULL', 'SELECT 1');
PREPARE allowance_stmt FROM @allowance_ddl; EXECUTE allowance_stmt; DEALLOCATE PREPARE allowance_stmt;

SET @allowance_check_count := (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_THUC_TAP'
      AND CONSTRAINT_NAME = 'chk_phu_cap_receipt_status' AND CONSTRAINT_TYPE = 'CHECK'
);
SET @allowance_ddl := IF(@allowance_check_count = 0,
    "ALTER TABLE PHU_CAP_THUC_TAP ADD CONSTRAINT chk_phu_cap_receipt_status CHECK (trang_thai_nhan IN ('ChoXacNhan', 'DaNhan', 'ChuaNhanDuoc'))",
    'SELECT 1');
PREPARE allowance_stmt FROM @allowance_ddl; EXECUTE allowance_stmt; DEALLOCATE PREPARE allowance_stmt;

SET @allowance_fk_count := (
    SELECT COUNT(*) FROM information_schema.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_THUC_TAP'
      AND COLUMN_NAME = 'xac_nhan_boi' AND REFERENCED_TABLE_NAME = 'NGUOI_DUNG'
);
SET @allowance_ddl := IF(@allowance_fk_count = 0,
    'ALTER TABLE PHU_CAP_THUC_TAP ADD CONSTRAINT fk_phu_cap_confirmed_by FOREIGN KEY (xac_nhan_boi) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT',
    'SELECT 1');
PREPARE allowance_stmt FROM @allowance_ddl; EXECUTE allowance_stmt; DEALLOCATE PREPARE allowance_stmt;

CREATE TABLE IF NOT EXISTS PHU_CAP_PHAN_ANH (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    allowance_id BIGINT NOT NULL,
    reported_by INT NOT NULL,
    noi_dung VARCHAR(2000) NOT NULL,
    trang_thai_xu_ly VARCHAR(24) NOT NULL DEFAULT 'ChoXuLy',
    ghi_chu_xu_ly VARCHAR(1000) NOT NULL DEFAULT '',
    updated_by INT NULL,
    updated_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_phu_cap_phan_anh_allowance (allowance_id, id),
    KEY idx_phu_cap_phan_anh_status (trang_thai_xu_ly, id),
    CONSTRAINT chk_phu_cap_phan_anh_status CHECK (trang_thai_xu_ly IN ('ChoXuLy', 'DangXuLy', 'DaXuLy')),
    FOREIGN KEY (allowance_id) REFERENCES PHU_CAP_THUC_TAP(id) ON DELETE RESTRICT,
    FOREIGN KEY (reported_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    FOREIGN KEY (updated_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS PHU_CAP_LICH_SU_XU_LY (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    allowance_id BIGINT NOT NULL,
    report_id BIGINT NULL,
    event_type VARCHAR(32) NOT NULL,
    noi_dung TEXT NULL,
    actor_id INT NOT NULL,
    actor_name VARCHAR(100) NOT NULL,
    actor_role VARCHAR(30) NOT NULL,
    so_tien_minor_snapshot BIGINT NULL,
    ky_snapshot CHAR(7) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_phu_cap_history_allowance (allowance_id, id),
    FOREIGN KEY (allowance_id) REFERENCES PHU_CAP_THUC_TAP(id) ON DELETE RESTRICT,
    FOREIGN KEY (report_id) REFERENCES PHU_CAP_PHAN_ANH(id) ON DELETE RESTRICT,
    FOREIGN KEY (actor_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
