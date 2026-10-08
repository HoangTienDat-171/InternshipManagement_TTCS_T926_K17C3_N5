-- Migration: US24 – Thực tập sinh đăng ký nghỉ phép
-- Tạo bảng canonical YEU_CAU_NGHI_PHEP gắn với context đơn ứng tuyển UNG_TUYEN_CHUONG_TRINH

CREATE TABLE IF NOT EXISTS YEU_CAU_NGHI_PHEP (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_ung_tuyen INT NOT NULL,
    ma_ho_so INT NOT NULL,
    ma_chuong_trinh INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    ly_do VARCHAR(1000) NOT NULL,
    trang_thai ENUM('ChoDuyet', 'DaDuyet', 'TuChoi', 'DaHuy') NOT NULL DEFAULT 'ChoDuyet',
    reviewed_by INT NULL,
    reviewed_at DATETIME NULL,
    ly_do_tu_choi VARCHAR(1000) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_yeu_cau_nghi_phep_dates CHECK (start_date <= end_date),
    KEY idx_yeu_cau_nghi_ung_tuyen (ma_ung_tuyen, trang_thai),
    KEY idx_yeu_cau_nghi_ho_so (ma_ho_so, trang_thai, start_date),
    KEY idx_yeu_cau_nghi_chuong_trinh (ma_chuong_trinh, trang_thai),
    KEY idx_yeu_cau_nghi_status_created (trang_thai, created_at),
    FOREIGN KEY (ma_ung_tuyen) REFERENCES UNG_TUYEN_CHUONG_TRINH(ma_ung_tuyen) ON DELETE CASCADE,
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
    FOREIGN KEY (ma_chuong_trinh) REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE CASCADE,
    FOREIGN KEY (reviewed_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Store leave evidence metadata separately and cascade it with the leave request.
CREATE TABLE IF NOT EXISTS YEU_CAU_NGHI_PHEP_TEP (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    leave_request_id BIGINT NOT NULL,
    storage_key VARCHAR(64) NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    file_size BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_leave_attachment_request (leave_request_id, id),
    CONSTRAINT fk_leave_attachment_request FOREIGN KEY (leave_request_id)
        REFERENCES YEU_CAU_NGHI_PHEP(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
