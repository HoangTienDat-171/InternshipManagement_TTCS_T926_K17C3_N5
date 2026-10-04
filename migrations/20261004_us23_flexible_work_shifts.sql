CREATE TABLE IF NOT EXISTS CA_LAM_VIEC (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    scope_type ENUM('GLOBAL', 'PROGRAM') NOT NULL,
    ma_chuong_trinh INT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE NULL,
    status ENUM('ACTIVE', 'INACTIVE') NOT NULL DEFAULT 'ACTIVE',
    created_by INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_ca_lam_viec_time CHECK (start_time < end_time),
    CONSTRAINT chk_ca_lam_viec_dates CHECK (effective_to IS NULL OR effective_to >= effective_from),
    CONSTRAINT chk_ca_lam_viec_scope CHECK (
        (scope_type = 'GLOBAL' AND ma_chuong_trinh IS NULL)
        OR (scope_type = 'PROGRAM' AND ma_chuong_trinh IS NOT NULL)
    ),
    KEY idx_ca_lam_viec_filter (status, scope_type, ma_chuong_trinh, effective_from),
    KEY idx_ca_lam_viec_creator (created_by),
    FOREIGN KEY (ma_chuong_trinh) REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE RESTRICT,
    FOREIGN KEY (created_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
