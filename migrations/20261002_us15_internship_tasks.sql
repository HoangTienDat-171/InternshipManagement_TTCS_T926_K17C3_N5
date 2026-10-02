USE `internship_management`;

CREATE TABLE IF NOT EXISTS NHIEM_VU_THUC_TAP (
    ma_nhiem_vu BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL,
    ma_nguoi_dung_mentor INT NOT NULL,
    tieu_de VARCHAR(200) NOT NULL,
    noi_dung TEXT NULL,
    han_hoan_thanh DATE NOT NULL,
    do_uu_tien ENUM('LOW', 'MEDIUM', 'HIGH', 'URGENT') NOT NULL DEFAULT 'MEDIUM',
    trang_thai ENUM('TODO', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED') NOT NULL DEFAULT 'TODO',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_nhiem_vu_mentor (ma_nguoi_dung_mentor, created_at),
    KEY idx_nhiem_vu_ho_so (ma_ho_so, created_at),
    KEY idx_nhiem_vu_filters (trang_thai, do_uu_tien, han_hoan_thanh),
    CONSTRAINT fk_nhiem_vu_ho_so
        FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
    CONSTRAINT fk_nhiem_vu_mentor
        FOREIGN KEY (ma_nguoi_dung_mentor) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
