-- Migration: US27 & US28 - Yêu cầu hỗ trợ và phản hồi giữa TTS với HR
-- Tạo bảng YEU_CAU_HO_TRO và YEU_CAU_HO_TRO_TEP

CREATE TABLE IF NOT EXISTS YEU_CAU_HO_TRO (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_nguoi_dung INT NOT NULL,
    ma_ho_so INT NULL,
    loai_yeu_cau VARCHAR(32) NOT NULL,
    noi_dung TEXT NOT NULL,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    phan_hoi_hr TEXT NULL,
    nguoi_xu_ly INT NULL,
    thoi_gian_xu_ly DATETIME NULL,
    idempotency_key VARCHAR(128) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_support_request_type CHECK (loai_yeu_cau IN ('CERTIFICATE', 'DOCUMENT', 'OTHER')),
    CONSTRAINT chk_support_request_status CHECK (trang_thai IN ('PENDING', 'RESOLVED', 'REJECTED')),
    UNIQUE KEY uq_support_request_idempotency (ma_nguoi_dung, idempotency_key),
    KEY idx_yeu_cau_ho_tro_user (ma_nguoi_dung, trang_thai, created_at),
    KEY idx_yeu_cau_ho_tro_status (trang_thai, created_at),
    KEY idx_yeu_cau_ho_tro_loai (loai_yeu_cau, trang_thai),
    FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE,
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE SET NULL,
    FOREIGN KEY (nguoi_xu_ly) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS YEU_CAU_HO_TRO_TEP (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    support_request_id BIGINT NOT NULL,
    storage_key VARCHAR(64) NOT NULL UNIQUE,
    original_filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    file_size BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_support_request_file (support_request_id, id),
    CONSTRAINT fk_support_request_file FOREIGN KEY (support_request_id)
        REFERENCES YEU_CAU_HO_TRO(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
