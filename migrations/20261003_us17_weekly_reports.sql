-- US17: weekly reports submitted by interns.
-- Week model is Monday through Sunday. The business key prevents duplicate reports.
CREATE TABLE IF NOT EXISTS BAO_CAO_TUAN (
    ma_bao_cao BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL,
    ma_chuong_trinh INT NOT NULL,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    work_content TEXT NOT NULL,
    results TEXT NOT NULL,
    difficulties TEXT NOT NULL,
    trang_thai ENUM('DRAFT','SUBMITTED') NOT NULL DEFAULT 'DRAFT',
    submitted_at DATETIME NULL,
    attachment_storage_key VARCHAR(80) NULL UNIQUE,
    attachment_original_name VARCHAR(255) NULL,
    attachment_mime_type VARCHAR(127) NULL,
    attachment_file_size BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_bao_cao_tuan_context (ma_ho_so, ma_chuong_trinh, week_start),
    KEY idx_bao_cao_tuan_profile_status (ma_ho_so, trang_thai, week_start),
    KEY idx_bao_cao_tuan_program (ma_chuong_trinh, week_start),
    CONSTRAINT fk_bao_cao_tuan_profile FOREIGN KEY (ma_ho_so)
        REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
    CONSTRAINT fk_bao_cao_tuan_program FOREIGN KEY (ma_chuong_trinh)
        REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
