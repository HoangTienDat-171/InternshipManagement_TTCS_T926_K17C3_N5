-- US18: one Mentor review per submitted weekly report.
CREATE TABLE IF NOT EXISTS NHAN_XET_BAO_CAO_TUAN (
    ma_nhan_xet BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_bao_cao BIGINT NOT NULL,
    reviewed_by INT NOT NULL,
    comment TEXT NOT NULL,
    reviewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_nhan_xet_bao_cao (ma_bao_cao),
    KEY idx_nhan_xet_mentor (reviewed_by, reviewed_at),
    CONSTRAINT fk_nhan_xet_bao_cao FOREIGN KEY (ma_bao_cao)
        REFERENCES BAO_CAO_TUAN(ma_bao_cao) ON DELETE RESTRICT,
    CONSTRAINT fk_nhan_xet_mentor FOREIGN KEY (reviewed_by)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
