-- Keep a snapshot when a live Mentor assignment is replaced or removed.
-- This table intentionally has no cascading foreign keys so the audit record
-- survives changes to the current assignment row and related master records.
CREATE TABLE IF NOT EXISTS PHAN_CONG_MENTOR_TTS_LICH_SU (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_phan_cong_goc BIGINT NOT NULL,
    ma_nguoi_dung_mentor INT NULL,
    ma_ho_so INT NULL,
    ma_chuong_trinh INT NULL,
    ma_ung_tuyen INT NULL,
    ma_nguoi_phan_cong INT NULL,
    ngay_phan_cong DATETIME NOT NULL,
    su_kien VARCHAR(20) NOT NULL,
    nguoi_thuc_hien INT NULL,
    archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_mentor_assignment_history_profile (ma_ho_so, ma_chuong_trinh, archived_at),
    KEY idx_mentor_assignment_history_mentor (ma_nguoi_dung_mentor, archived_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
