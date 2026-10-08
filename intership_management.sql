CREATE DATABASE IF NOT EXISTS `Internship_Management`;
USE `Internship_Management`;
-- 1. Bảng Danh mục Phòng Ban
CREATE TABLE IF NOT EXISTS PHONG_BAN (
    ma_phong_ban INT AUTO_INCREMENT PRIMARY KEY,
    ten_phong_ban VARCHAR(100) NOT NULL,
    mo_ta TEXT
);

-- 2. Bảng Danh mục Trường Đại Học
CREATE TABLE IF NOT EXISTS TRUONG_DAI_HOC (
    ma_truong INT AUTO_INCREMENT PRIMARY KEY,
    ten_truong VARCHAR(255) NOT NULL,
    dia_chi VARCHAR(255),
    nguoi_lien_he VARCHAR(100),
    email_lien_he VARCHAR(100),
    UNIQUE KEY uq_truong_dai_hoc_ten (ten_truong)
);

-- 3. Bảng Người Dùng (Tài khoản & Phân quyền)
CREATE TABLE IF NOT EXISTS NGUOI_DUNG (
    ma_nguoi_dung INT AUTO_INCREMENT PRIMARY KEY,
    ma_phong_ban INT NULL,
    ho_ten VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    mat_khau VARCHAR(255) NOT NULL, -- Dùng hash bcrypt/argon2
    must_change_password TINYINT(1) NOT NULL DEFAULT 0,
    so_dien_thoai VARCHAR(20),
    avatar_url VARCHAR(500) NULL,
    vai_tro ENUM('Admin', 'HR', 'Mentor', 'ThucTapSinh') NOT NULL,
    trang_thai ENUM('HoatDong', 'Khoa', 'ChoDuyet') NOT NULL DEFAULT 'HoatDong',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_nguoi_dung_email (email),
    UNIQUE KEY uq_nguoi_dung_so_dien_thoai (so_dien_thoai),
    FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE SET NULL
);

-- 4. Bảng Hồ Sơ Thực Tập (Khởi tạo & Xét duyệt)
CREATE TABLE IF NOT EXISTS HO_SO_THUC_TAP (
    ma_ho_so INT AUTO_INCREMENT PRIMARY KEY,
    ma_nguoi_dung INT NOT NULL UNIQUE, -- Liên kết 1-1 với tài khoản Thực tập sinh
    ma_truong INT NULL,
    chuyen_nganh VARCHAR(100),
    trang_thai_xet_duyet ENUM('ChoDuyet', 'DaDuyet', 'TuChoi') DEFAULT 'ChoDuyet',
    trang_thai_thuc_tap ENUM('DangThucTap', 'HoanThanh', 'ThoiHoc') DEFAULT 'DangThucTap',
    ngay_tao DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE,
    FOREIGN KEY (ma_truong) REFERENCES TRUONG_DAI_HOC(ma_truong) ON DELETE SET NULL
);

-- 5. Bảng Tài Liệu Hồ Sơ (Upload CV, Giấy tờ)
CREATE TABLE IF NOT EXISTS TAI_LIEU_HO_SO (
    ma_tai_lieu INT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL,
    loai_tai_lieu ENUM('CV', 'DonXinThucTap', 'GiayGioiThieu') NOT NULL,
    duong_dan_file VARCHAR(500) NOT NULL,
    ten_file VARCHAR(255),
    kich_thuoc BIGINT UNSIGNED,
    trang_thai_duyet ENUM('ChoDuyet', 'DaDuyet', 'TuChoi') DEFAULT 'ChoDuyet',
    ngay_tai_len DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_by INT NULL,
    review_reason TEXT NULL,
    reviewed_at DATETIME NULL,
    KEY idx_tai_lieu_reviewed_by (reviewed_by),
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
    CONSTRAINT fk_tai_lieu_reviewed_by FOREIGN KEY (reviewed_by)
        REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
);

-- 6. Bảng Thông Báo (Gửi mail/app về kết quả xét duyệt)
CREATE TABLE IF NOT EXISTS THONG_BAO (
    ma_thong_bao INT AUTO_INCREMENT PRIMARY KEY,
    ma_nguoi_dung INT NOT NULL,
    tieu_de VARCHAR(255) NOT NULL,
    noi_dung TEXT,
    kenh ENUM('Email', 'App') DEFAULT 'Email',
    da_doc BOOLEAN DEFAULT FALSE,
    thoi_gian_gui DATETIME DEFAULT CURRENT_TIMESTAMP,
    loai VARCHAR(80) NOT NULL DEFAULT 'general',
    reference_type VARCHAR(80),
    reference_id VARCHAR(100),
    thoi_gian_doc DATETIME,
    FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS EMAIL_OUTBOX (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    recipient_email VARCHAR(254) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    template_type VARCHAR(80) NOT NULL,
    reference_type VARCHAR(80),
    reference_id VARCHAR(100),
    deduplication_key VARCHAR(190) NOT NULL UNIQUE,
    status ENUM('PENDING','PROCESSING','SENT','FAILED','RETRY') NOT NULL DEFAULT 'PENDING',
    retry_count INT NOT NULL DEFAULT 0,
    max_retry INT NOT NULL DEFAULT 4,
    last_error TEXT,
    next_retry_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_email_outbox_due (status, next_retry_at, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Thông tin chuyên môn riêng của Mentor; tài khoản vẫn dùng NGUOI_DUNG.
CREATE TABLE IF NOT EXISTS MENTOR_PROFILE (
    ma_nguoi_dung INT PRIMARY KEY,
    chuyen_mon VARCHAR(255),
    kinh_nghiem INT UNSIGNED,
    so_tts_toi_da INT UNSIGNED,
    FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
);

-- Chương trình thực tập và thông tin tuyển dụng.
CREATE TABLE IF NOT EXISTS CHUONG_TRINH_THUC_TAP (
    ma_chuong_trinh INT AUTO_INCREMENT PRIMARY KEY,
    ma_ct VARCHAR(40) NOT NULL UNIQUE,
    ten_ct VARCHAR(200) NOT NULL,
    ma_phong_ban INT NULL,
    ngay_bat_dau DATE NULL,
    ngay_ket_thuc DATE NULL,
    chi_tieu INT UNSIGNED NOT NULL,
    mo_ta_cong_viec TEXT,
    yeu_cau TEXT,
    quyen_loi TEXT,
    trang_thai ENUM('DangMo', 'TamDung', 'DaDong') NOT NULL DEFAULT 'DangMo',
    ngay_tao DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE SET NULL
);

-- Đơn ứng tuyển thuộc từng chương trình; trạng thái này độc lập với trạng thái đăng nhập.
CREATE TABLE IF NOT EXISTS UNG_TUYEN_CHUONG_TRINH (
    ma_ung_tuyen INT AUTO_INCREMENT PRIMARY KEY,
    ma_chuong_trinh INT NOT NULL,
    ma_ho_so INT NOT NULL,
    trang_thai ENUM('ChoDuyet', 'DaDuyet', 'TuChoi') NOT NULL DEFAULT 'ChoDuyet',
    ngay_ung_tuyen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ngay_xet_duyet DATETIME NULL,
    nguoi_xet_duyet INT NULL,
    UNIQUE KEY uq_ung_tuyen_chuong_trinh (ma_chuong_trinh, ma_ho_so),
    KEY idx_ung_tuyen_chuong_trinh_trang_thai (ma_chuong_trinh, trang_thai),
    FOREIGN KEY (ma_chuong_trinh) REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE CASCADE,
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
    FOREIGN KEY (nguoi_xet_duyet) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
);

-- Phân công Mentor cho Thực tập sinh gắn với chương trình / đơn ứng tuyển.
CREATE TABLE IF NOT EXISTS PHAN_CONG_MENTOR_TTS (
    ma_phan_cong INT AUTO_INCREMENT PRIMARY KEY,
    ma_nguoi_dung_mentor INT NOT NULL,
    ma_ho_so INT NOT NULL,
    ma_chuong_trinh INT NULL,
    ma_ung_tuyen INT NULL,
    ma_nguoi_phan_cong INT NULL,
    ngay_phan_cong DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_phan_cong_mentor (ma_nguoi_dung_mentor),
    KEY idx_phan_cong_ho_so (ma_ho_so),
    KEY idx_phan_cong_chuong_trinh (ma_chuong_trinh),
    UNIQUE KEY uq_phan_cong_ho_so_ct (ma_ho_so, ma_chuong_trinh),
    FOREIGN KEY (ma_nguoi_dung_mentor) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE,
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
    FOREIGN KEY (ma_chuong_trinh) REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE SET NULL,
    FOREIGN KEY (ma_nguoi_phan_cong) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
);

-- 15. Bảng Yêu Cầu Nghỉ Phép (US24)
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
);

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


-- US25/26: one entry per internship profile/month. Amount is VND * 100, never FLOAT.
-- Back up the configured database before applying. Safe to re-run; no seeds or destructive DDL.
CREATE TABLE IF NOT EXISTS PHU_CAP_THUC_TAP (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL,
    ma_ung_tuyen INT NOT NULL,
    ky CHAR(7) NOT NULL,
    so_tien_minor BIGINT NOT NULL,
    ghi_chu VARCHAR(1000) NOT NULL DEFAULT '',
    trang_thai_nhan VARCHAR(24) NOT NULL DEFAULT 'ChoXacNhan',
    xac_nhan_boi INT NULL,
    xac_nhan_luc DATETIME(6) NULL,
    created_by INT NOT NULL,
    updated_by INT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    UNIQUE KEY uq_phu_cap_ho_so_ky (ma_ho_so, ky),
    KEY idx_phu_cap_ky (ky, id),
    CONSTRAINT chk_phu_cap_amount CHECK (so_tien_minor BETWEEN 0 AND 999999999999999),
    CONSTRAINT chk_phu_cap_period CHECK (ky REGEXP '^[1-9][0-9]{3}-(0[1-9]|1[0-2])$'),
    CONSTRAINT chk_phu_cap_receipt_status CHECK (trang_thai_nhan IN ('ChoXacNhan', 'DaNhan', 'ChuaNhanDuoc')),
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE RESTRICT,
    FOREIGN KEY (ma_ung_tuyen) REFERENCES UNG_TUYEN_CHUONG_TRINH(ma_ung_tuyen) ON DELETE RESTRICT,
    FOREIGN KEY (created_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    FOREIGN KEY (updated_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    FOREIGN KEY (xac_nhan_boi) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS PHU_CAP_PHAN_ANH (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    allowance_id BIGINT NOT NULL,
    reported_by INT NOT NULL,
    noi_dung VARCHAR(2000) NOT NULL,
    trang_thai_xu_ly VARCHAR(24) NOT NULL DEFAULT 'ChoXuLy',
    ghi_chu_xu_ly VARCHAR(1000) NOT NULL DEFAULT '',
    updated_by INT NULL,
    updated_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_phu_cap_phan_anh_allowance (allowance_id, id),
    KEY idx_phu_cap_phan_anh_status (trang_thai_xu_ly, id),
    CONSTRAINT chk_phu_cap_phan_anh_status CHECK (trang_thai_xu_ly IN ('ChoXuLy', 'DangXuLy', 'DaXuLy')),
    FOREIGN KEY (allowance_id) REFERENCES PHU_CAP_THUC_TAP(id) ON DELETE RESTRICT,
    FOREIGN KEY (reported_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT,
    FOREIGN KEY (updated_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS PHU_CAP_LICH_SU_XU_LY (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    allowance_id BIGINT NOT NULL,
    report_id BIGINT NULL,
    event_type VARCHAR(32) NOT NULL,
    noi_dung TEXT NULL,
    actor_id INT NOT NULL,
    actor_name VARCHAR(100) NOT NULL,
    actor_role VARCHAR(30) NOT NULL,
    so_tien_minor_snapshot BIGINT NULL,
    ky_snapshot CHAR(7) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    KEY idx_phu_cap_history_allowance (allowance_id, id),
    FOREIGN KEY (allowance_id) REFERENCES PHU_CAP_THUC_TAP(id) ON DELETE RESTRICT,
    FOREIGN KEY (report_id) REFERENCES PHU_CAP_PHAN_ANH(id) ON DELETE RESTRICT,
    FOREIGN KEY (actor_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- Tài khoản demo dùng chung mật khẩu 123456 (bcrypt).
INSERT IGNORE INTO NGUOI_DUNG
    (ho_ten, email, mat_khau, so_dien_thoai, vai_tro, trang_thai)
VALUES
    ('Tài khoản mẫu Sprint 1', 'sprint1.demo1@example.com', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0912345678', 'ThucTapSinh', 'HoatDong'),
    ('Tài khoản mẫu Sprint 1', 'sprint1.demo2@example.com', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0387654321', 'ThucTapSinh', 'HoatDong'),
    ('Nguyễn Minh Khôi (Thực tập sinh)', 'minh.khoi.nguyen@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0911000001', 'ThucTapSinh', 'HoatDong'),
    ('Trần Thị Ngọc (Thực tập sinh)', 'ngoc.tran@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0381000002', 'ThucTapSinh', 'HoatDong'),
    ('Lê Quang Huy (Thực tập sinh)', 'quang.huy.le@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0971000003', 'ThucTapSinh', 'HoatDong'),
    ('Phạm Gia Hân (Thực tập sinh)', 'gia.han.pham@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0851000004', 'ThucTapSinh', 'HoatDong'),
    ('Võ Đức Long (Thực tập sinh)', 'duc.long.vo@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0831000005', 'ThucTapSinh', 'HoatDong'),
    ('Bùi Thanh Trúc (Thực tập sinh)', 'thanh.truc.bui@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0701000006', 'ThucTapSinh', 'HoatDong'),
    ('Đặng Hoàng Nam (Thực tập sinh)', 'hoang.nam.dang@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0921000007', 'ThucTapSinh', 'HoatDong'),
    ('Đỗ Khánh Linh (Thực tập sinh)', 'khanh.linh.do@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0861000008', 'ThucTapSinh', 'ChoDuyet'),
    ('Hoàng Tuấn Kiệt (Thực tập sinh)', 'tuan.kiet.hoang@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0391000009', 'ThucTapSinh', 'Khoa'),
    ('Mai Phương Anh (Thực tập sinh)', 'phuong.anh.mai@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0561000010', 'ThucTapSinh', 'HoatDong'),
    ('Nguyễn Hải Đăng (Mentor)', 'hai.dang.nguyen@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0905555667', 'Mentor', 'HoatDong'),
    ('Trần Quốc Bảo (Mentor)', 'quoc.bao.tran@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0905555668', 'Mentor', 'HoatDong'),
    ('Lê Thu Trang (HR)', 'thu.trang.le@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0903333445', 'HR', 'HoatDong'),
    ('Quản trị viên dự phòng', 'admin.demo2@internship.vn', '$2b$12$Ci7yMkXXUk7T20/NWrPz/ugLS0yjApO3i799qQBoboLgN02kiumzC', '0901111223', 'Admin', 'HoatDong');

INSERT INTO TRUONG_DAI_HOC (ten_truong, dia_chi, nguoi_lien_he, email_lien_he)
SELECT sample.ten_truong, sample.dia_chi, sample.nguoi_lien_he, sample.email_lien_he
FROM (
    SELECT 'Đại học Bách Khoa Hà Nội' AS ten_truong, 'Số 1 Đại Cồ Việt, Hai Bà Trưng, Hà Nội' AS dia_chi, 'ThS. Nguyễn Văn A' AS nguoi_lien_he, 'contact@hust.edu.vn' AS email_lien_he UNION ALL
    SELECT 'Đại học Quốc gia Hà Nội (UET)', '144 Xuân Thủy, Cầu Giấy, Hà Nội', 'TS. Trần Thị B', 'contact@uet.vnu.edu.vn' UNION ALL
    SELECT 'Học viện Công nghệ Bưu chính Viễn thông (PTIT)', 'Km10 Đường Nguyễn Trãi, Hà Đông, Hà Nội', 'ThS. Lê Hoàng C', 'contact@ptit.edu.vn' UNION ALL
    SELECT 'Đại học FPT', 'Khu CNC Hòa Lạc, Thạch Thất, Hà Nội', 'ThS. Phạm Tuấn D', 'contact@fpt.edu.vn'
) AS sample
WHERE NOT EXISTS (SELECT 1 FROM TRUONG_DAI_HOC existing WHERE existing.ten_truong = sample.ten_truong);

-- Hồ sơ thực tập mẫu để các màn hình quản lý hồ sơ có dữ liệu hiển thị.
INSERT INTO HO_SO_THUC_TAP (ma_nguoi_dung, ma_truong, chuyen_nganh, trang_thai_xet_duyet, trang_thai_thuc_tap)
SELECT u.ma_nguoi_dung, sample.ma_truong, sample.chuyen_nganh, sample.trang_thai_xet_duyet, sample.trang_thai_thuc_tap
FROM (
    SELECT 'minh.khoi.nguyen@internship.vn' AS email, 1 AS ma_truong, 'Kỹ thuật phần mềm' AS chuyen_nganh, 'DaDuyet' AS trang_thai_xet_duyet, 'DangThucTap' AS trang_thai_thuc_tap UNION ALL
    SELECT 'ngoc.tran@internship.vn', 2, 'An toàn thông tin', 'DaDuyet', 'DangThucTap' UNION ALL
    SELECT 'quang.huy.le@internship.vn', 3, 'Hệ thống thông tin', 'ChoDuyet', 'DangThucTap' UNION ALL
    SELECT 'gia.han.pham@internship.vn', 4, 'Trí tuệ nhân tạo', 'DaDuyet', 'DangThucTap' UNION ALL
    SELECT 'duc.long.vo@internship.vn', 1, 'Kỹ thuật phần mềm', 'DaDuyet', 'HoanThanh' UNION ALL
    SELECT 'thanh.truc.bui@internship.vn', 2, 'Khoa học dữ liệu', 'DaDuyet', 'DangThucTap' UNION ALL
    SELECT 'hoang.nam.dang@internship.vn', 3, 'Mạng máy tính', 'DaDuyet', 'DangThucTap' UNION ALL
    SELECT 'khanh.linh.do@internship.vn', 4, 'Thiết kế giao diện', 'ChoDuyet', 'DangThucTap' UNION ALL
    SELECT 'tuan.kiet.hoang@internship.vn', 1, 'Phát triển ứng dụng', 'DaDuyet', 'ThoiHoc' UNION ALL
    SELECT 'phuong.anh.mai@internship.vn', 2, 'Phân tích dữ liệu', 'DaDuyet', 'DangThucTap'
) AS sample
JOIN NGUOI_DUNG u ON u.email = sample.email
WHERE NOT EXISTS (
    SELECT 1 FROM HO_SO_THUC_TAP existing WHERE existing.ma_nguoi_dung = u.ma_nguoi_dung
);

-- Bảng Yêu cầu Hỗ trợ (US27 & US28)
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
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT chk_support_request_type CHECK (loai_yeu_cau IN ('CERTIFICATE', 'DOCUMENT', 'OTHER')),
    CONSTRAINT chk_support_request_status CHECK (trang_thai IN ('PENDING', 'RESOLVED', 'REJECTED')),
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
