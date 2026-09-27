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
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE
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
    FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
);

-- Thông tin chuyên môn riêng của Mentor; tài khoản vẫn dùng NGUOI_DUNG.
CREATE TABLE IF NOT EXISTS MENTOR_PROFILE (
    ma_nguoi_dung INT PRIMARY KEY,
    chuyen_mon VARCHAR(255),
    kinh_nghiem INT UNSIGNED,
    so_tts_toi_da INT UNSIGNED,
    FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
);

-- Mỗi hồ sơ TTS chỉ có một Mentor đang hướng dẫn tại một thời điểm.
CREATE TABLE IF NOT EXISTS PHAN_CONG_MENTOR_TTS (
    ma_phan_cong INT AUTO_INCREMENT PRIMARY KEY,
    ma_nguoi_dung_mentor INT NOT NULL,
    ma_ho_so INT NOT NULL UNIQUE,
    ma_nguoi_phan_cong INT NULL,
    ngay_phan_cong DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_phan_cong_mentor (ma_nguoi_dung_mentor),
    FOREIGN KEY (ma_nguoi_dung_mentor) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE,
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE,
    FOREIGN KEY (ma_nguoi_phan_cong) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
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
