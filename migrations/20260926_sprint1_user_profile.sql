-- MySQL migration: Sprint 1 account and phone fields.
-- Run with a MySQL user that can ALTER NGUOI_DUNG and CREATE ROUTINE.
USE `Internship_Management`;

DROP PROCEDURE IF EXISTS `_migrate_sprint1_user_profile`;
DELIMITER $$
CREATE PROCEDURE `_migrate_sprint1_user_profile`()
BEGIN
    DECLARE duplicate_count INT DEFAULT 0;
    DECLARE column_definition TEXT DEFAULT '';

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = 'NGUOI_DUNG'
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'NGUOI_DUNG is missing; import intership_management.sql first.';
    END IF;

    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT email FROM NGUOI_DUNG GROUP BY email HAVING COUNT(*) > 1
    ) AS duplicate_emails;
    IF duplicate_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Duplicate emails exist in NGUOI_DUNG; resolve them before adding the unique key.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'NGUOI_DUNG' AND column_name = 'so_dien_thoai'
    ) THEN
        SELECT COUNT(*) INTO duplicate_count
        FROM (
            SELECT so_dien_thoai FROM NGUOI_DUNG
            WHERE so_dien_thoai IS NOT NULL
            GROUP BY so_dien_thoai HAVING COUNT(*) > 1
        ) AS duplicate_phones;
        IF duplicate_count > 0 THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'Duplicate phone numbers exist in NGUOI_DUNG; resolve them before adding the unique key.';
        END IF;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'NGUOI_DUNG' AND column_name = 'so_dien_thoai'
    ) THEN
        ALTER TABLE NGUOI_DUNG ADD COLUMN so_dien_thoai VARCHAR(20) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'NGUOI_DUNG' AND column_name = 'avatar_url'
    ) THEN
        ALTER TABLE NGUOI_DUNG ADD COLUMN avatar_url VARCHAR(500) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'NGUOI_DUNG' AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE NGUOI_DUNG
            ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'NGUOI_DUNG' AND column_name = 'trang_thai'
    ) THEN
        ALTER TABLE NGUOI_DUNG
            ADD COLUMN trang_thai ENUM('HoatDong', 'Khoa', 'ChoDuyet') NOT NULL DEFAULT 'HoatDong';
    ELSE
        SELECT column_type INTO column_definition
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'NGUOI_DUNG' AND column_name = 'trang_thai'
        LIMIT 1;
        IF LOCATE('ChoDuyet', column_definition) = 0 THEN
            ALTER TABLE NGUOI_DUNG
                MODIFY COLUMN trang_thai ENUM('HoatDong', 'Khoa', 'ChoDuyet') NOT NULL DEFAULT 'HoatDong';
        END IF;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = 'NGUOI_DUNG'
          AND column_name = 'email' AND non_unique = 0
    ) THEN
        ALTER TABLE NGUOI_DUNG ADD UNIQUE KEY uq_nguoi_dung_email (email);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = 'NGUOI_DUNG'
          AND column_name = 'so_dien_thoai' AND non_unique = 0
    ) THEN
        ALTER TABLE NGUOI_DUNG ADD UNIQUE KEY uq_nguoi_dung_so_dien_thoai (so_dien_thoai);
    END IF;
END$$
DELIMITER ;

CALL `_migrate_sprint1_user_profile`();
DROP PROCEDURE IF EXISTS `_migrate_sprint1_user_profile`;

-- Idempotent demo accounts; shared demo password is 123456 (bcrypt hash).
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

-- Idempotent internship profiles for list, filter, and detail demonstrations.
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
