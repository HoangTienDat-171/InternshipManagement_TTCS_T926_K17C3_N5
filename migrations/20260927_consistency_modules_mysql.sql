-- MySQL compatibility migration for document metadata and persistent mentor/program records.
-- The configured application runtime uses the internship_management MySQL schema.
USE `internship_management`;

DROP PROCEDURE IF EXISTS `_migrate_consistency_modules`;
DELIMITER $$
CREATE PROCEDURE `_migrate_consistency_modules`()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'TAI_LIEU_HO_SO' AND column_name = 'ten_file'
    ) THEN
        ALTER TABLE TAI_LIEU_HO_SO ADD COLUMN ten_file VARCHAR(255) NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'TAI_LIEU_HO_SO' AND column_name = 'kich_thuoc'
    ) THEN
        ALTER TABLE TAI_LIEU_HO_SO ADD COLUMN kich_thuoc BIGINT UNSIGNED NULL;
    END IF;

    CREATE TABLE IF NOT EXISTS MENTOR_PROFILE (
        ma_nguoi_dung INT PRIMARY KEY,
        chuyen_mon VARCHAR(255),
        kinh_nghiem INT UNSIGNED,
        so_tts_toi_da INT UNSIGNED,
        FOREIGN KEY (ma_nguoi_dung) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE CASCADE
    );

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

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'CHUONG_TRINH_THUC_TAP' AND COLUMN_NAME = 'mo_ta_cong_viec'
    ) THEN
        ALTER TABLE CHUONG_TRINH_THUC_TAP ADD COLUMN mo_ta_cong_viec TEXT NULL;
    END IF;

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
END$$
DELIMITER ;

CALL `_migrate_consistency_modules`();
DROP PROCEDURE IF EXISTS `_migrate_consistency_modules`;
