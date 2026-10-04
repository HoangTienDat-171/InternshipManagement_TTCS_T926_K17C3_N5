CREATE TABLE IF NOT EXISTS CHAM_CONG (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL,
    ca_lam_viec_id BIGINT NOT NULL,
    attendance_date DATE NOT NULL,
    check_in_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    check_out_at DATETIME NULL,
    status ENUM('CHECKED_IN','COMPLETED') NOT NULL DEFAULT 'CHECKED_IN',
    note VARCHAR(1000) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_cham_cong_state CHECK (
        (status = 'CHECKED_IN' AND check_out_at IS NULL)
        OR (status = 'COMPLETED' AND check_out_at IS NOT NULL)
    ),
    UNIQUE KEY uq_cham_cong_profile_day_shift (ma_ho_so, attendance_date, ca_lam_viec_id),
    KEY idx_cham_cong_profile_day (ma_ho_so, attendance_date, id),
    KEY idx_cham_cong_shift (ca_lam_viec_id),
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
    FOREIGN KEY (ca_lam_viec_id) REFERENCES CA_LAM_VIEC(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
