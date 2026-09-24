CREATE DATABASE `Internship_Management`;
-- 1. Bảng Danh mục Phòng Ban
CREATE TABLE PHONG_BAN (
    ma_phong_ban INT AUTO_INCREMENT PRIMARY KEY,
    ten_phong_ban VARCHAR(100) NOT NULL,
    mo_ta TEXT
);

-- 2. Bảng Danh mục Trường Đại Học
CREATE TABLE TRUONG_DAI_HOC (
    ma_truong INT AUTO_INCREMENT PRIMARY KEY,
    ten_truong VARCHAR(255) NOT NULL,
    dia_chi VARCHAR(255),
    nguoi_lien_he VARCHAR(100),
    email_lien_he VARCHAR(100)
);

-- 3. Bảng Người Dùng (Tài khoản & Phân quyền)
CREATE TABLE NGUOI_DUNG (
    ma_nguoi_dung INT AUTO_INCREMENT PRIMARY KEY,
    ma_phong_ban INT NULL,
    ho_ten VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    mat_khau VARCHAR(255) NOT NULL, -- Dùng hash bcrypt/argon2
    so_dien_thoai VARCHAR(20),
    vai_tro ENUM('Admin', 'HR', 'Mentor', 'ThucTapSinh') NOT NULL,
    trang_thai ENUM('HoatDong', 'Khoa') DEFAULT 'HoatDong',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ma_phong_ban) REFERENCES PHONG_BAN(ma_phong_ban) ON DELETE SET NULL
);

-- 4. Bảng Hồ Sơ Thực Tập (Khởi tạo & Xét duyệt)
CREATE TABLE HO_SO_THUC_TAP (
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
CREATE TABLE TAI_LIEU_HO_SO (
    ma_tai_lieu INT AUTO_INCREMENT PRIMARY KEY,
    ma_ho_so INT NOT NULL,
    loai_tai_lieu ENUM('CV', 'DonXinThucTap', 'GiayGioiThieu') NOT NULL,
    duong_dan_file VARCHAR(500) NOT NULL,
    trang_thai_duyet ENUM('ChoDuyet', 'DaDuyet', 'TuChoi') DEFAULT 'ChoDuyet',
    ngay_tai_len DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ma_ho_so) REFERENCES HO_SO_THUC_TAP(ma_ho_so) ON DELETE CASCADE
);

-- 6. Bảng Thông Báo (Gửi mail/app về kết quả xét duyệt)
CREATE TABLE THONG_BAO (
    ma_thong_bao INT AUTO_INCREMENT PRIMARY KEY,
    ma_nguoi_dung INT NOT NULL,
    tieu_de VARCHAR(255) NOT NULL,
    noi_dung TEXT,
    kenh ENUM('Email', 'App') DEFAULT 'Email',
    da_doc BOOLEAN DEFAULT FALSE,
    thoi_gian_gui DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
);