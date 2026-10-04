-- US19: Mentor evaluation per intern, approved program, and evaluation period.
-- Apply to a MySQL 8 test schema first; do not run against runtime data for tests.
CREATE TABLE IF NOT EXISTS DANH_GIA_THUC_TAP (
    ma_danh_gia BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL,
    ma_chuong_trinh INT NOT NULL,
    ma_nguoi_dung_mentor INT NOT NULL,
    ky_danh_gia ENUM('MIDTERM', 'FINAL') NOT NULL,
    professional_skill_score TINYINT NOT NULL,
    work_quality_score TINYINT NOT NULL,
    initiative_score TINYINT NOT NULL,
    communication_teamwork_score TINYINT NOT NULL,
    attitude_discipline_score TINYINT NOT NULL,
    overall_comment TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    evaluated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_danh_gia_scores CHECK (
        professional_skill_score BETWEEN 1 AND 5
        AND work_quality_score BETWEEN 1 AND 5
        AND initiative_score BETWEEN 1 AND 5
        AND communication_teamwork_score BETWEEN 1 AND 5
        AND attitude_discipline_score BETWEEN 1 AND 5
    ),
    CONSTRAINT chk_danh_gia_comment CHECK (CHAR_LENGTH(overall_comment) BETWEEN 1 AND 10000),
    UNIQUE KEY uq_danh_gia_context (ma_ho_so, ma_chuong_trinh, ky_danh_gia),
    KEY idx_danh_gia_mentor_time (ma_nguoi_dung_mentor, evaluated_at),
    KEY idx_danh_gia_program_period (ma_chuong_trinh, ky_danh_gia, evaluated_at),
    CONSTRAINT fk_danh_gia_profile FOREIGN KEY (ma_ho_so)
        REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
    CONSTRAINT fk_danh_gia_program FOREIGN KEY (ma_chuong_trinh)
        REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE RESTRICT,
    CONSTRAINT fk_danh_gia_mentor FOREIGN KEY (ma_nguoi_dung_mentor)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
