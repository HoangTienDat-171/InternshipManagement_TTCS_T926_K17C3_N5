-- MySQL 8 migration for US09 private internship contracts.
-- The application runtime creates the same table in fresh MySQL and SQLite schemas.
USE `internship_management`;

CREATE TABLE IF NOT EXISTS HOP_DONG_THUC_TAP (
    ma_hop_dong BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL UNIQUE,
    original_file_name VARCHAR(255) NOT NULL,
    storage_key VARCHAR(80) NOT NULL UNIQUE,
    mime_type VARCHAR(127) NOT NULL,
    file_size BIGINT UNSIGNED NOT NULL,
    trang_thai VARCHAR(40) NOT NULL DEFAULT 'PENDING_CONFIRMATION',
    uploaded_by INT NULL,
    uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_hop_dong_status CHECK (trang_thai IN ('PENDING_CONFIRMATION','CONFIRMED','REJECTED')),
    KEY idx_hop_dong_uploaded_at (uploaded_at),
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
