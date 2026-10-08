-- US25/26: one entry per internship profile/month. Amount is VND * 100, never FLOAT.
-- Back up the configured database before applying. Safe to re-run; no seeds or destructive DDL.
CREATE TABLE IF NOT EXISTS PHU_CAP_THUC_TAP (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL,
    ma_ung_tuyen INT NOT NULL,
    ky CHAR(7) NOT NULL,
    so_tien_minor BIGINT NOT NULL,
    ghi_chu VARCHAR(1000) NOT NULL DEFAULT '',
    created_by INT NOT NULL,
    updated_by INT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_phu_cap_ho_so_ky (ma_ho_so, ky),
    KEY idx_phu_cap_ky (ky, id),
    CONSTRAINT chk_phu_cap_amount CHECK (so_tien_minor BETWEEN 0 AND 999999999999999),
    CONSTRAINT chk_phu_cap_period CHECK (ky REGEXP '^[1-9][0-9]{3}-(0[1-9]|1[0-2])$'),
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
    FOREIGN KEY (ma_ung_tuyen) REFERENCES UNG_TUYEN_CHUONG_TRINH(ma_ung_tuyen) ON DELETE RESTRICT,
    FOREIGN KEY (created_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    FOREIGN KEY (updated_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
