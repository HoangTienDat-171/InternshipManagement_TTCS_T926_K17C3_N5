-- MySQL 8 migration for US10 contract decisions and immutable audit history.
-- Run after the US09 contract migrations. Safe to re-run.
USE `internship_management`;

DROP PROCEDURE IF EXISTS `_migrate_us10_contract_confirmation`;
DELIMITER $$
CREATE PROCEDURE `_migrate_us10_contract_confirmation`()
BEGIN
    DECLARE column_exists INT DEFAULT 0;
    DECLARE foreign_key_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO column_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'HOP_DONG_THUC_TAP' AND column_name = 'confirmed_by';
    IF column_exists = 0 THEN
        ALTER TABLE HOP_DONG_THUC_TAP ADD COLUMN confirmed_by INT NULL;
    END IF;

    SELECT COUNT(*) INTO column_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'HOP_DONG_THUC_TAP' AND column_name = 'confirmed_at';
    IF column_exists = 0 THEN
        ALTER TABLE HOP_DONG_THUC_TAP ADD COLUMN confirmed_at DATETIME NULL;
    END IF;

    SELECT COUNT(*) INTO column_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'HOP_DONG_THUC_TAP' AND column_name = 'rejected_by';
    IF column_exists = 0 THEN
        ALTER TABLE HOP_DONG_THUC_TAP ADD COLUMN rejected_by INT NULL;
    END IF;

    SELECT COUNT(*) INTO column_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'HOP_DONG_THUC_TAP' AND column_name = 'rejected_at';
    IF column_exists = 0 THEN
        ALTER TABLE HOP_DONG_THUC_TAP ADD COLUMN rejected_at DATETIME NULL;
    END IF;

    SELECT COUNT(*) INTO column_exists
    FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'HOP_DONG_THUC_TAP' AND column_name = 'rejection_reason';
    IF column_exists = 0 THEN
        ALTER TABLE HOP_DONG_THUC_TAP ADD COLUMN rejection_reason VARCHAR(500) NULL;
    END IF;

    SELECT COUNT(*) INTO foreign_key_exists
    FROM information_schema.key_column_usage
    WHERE table_schema = DATABASE() AND table_name = 'HOP_DONG_THUC_TAP'
      AND column_name = 'confirmed_by' AND referenced_table_name = 'NGUOI_DUNG';
    IF foreign_key_exists = 0 THEN
        ALTER TABLE HOP_DONG_THUC_TAP
            ADD CONSTRAINT fk_contract_confirmed_by FOREIGN KEY (confirmed_by)
            REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL;
    END IF;

    SELECT COUNT(*) INTO foreign_key_exists
    FROM information_schema.key_column_usage
    WHERE table_schema = DATABASE() AND table_name = 'HOP_DONG_THUC_TAP'
      AND column_name = 'rejected_by' AND referenced_table_name = 'NGUOI_DUNG';
    IF foreign_key_exists = 0 THEN
        ALTER TABLE HOP_DONG_THUC_TAP
            ADD CONSTRAINT fk_contract_rejected_by FOREIGN KEY (rejected_by)
            REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL;
    END IF;
END$$
DELIMITER ;

CALL `_migrate_us10_contract_confirmation`();
DROP PROCEDURE `_migrate_us10_contract_confirmation`;

CREATE TABLE IF NOT EXISTS HOP_DONG_THUC_TAP_LICH_SU (
    history_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ma_hop_dong BIGINT NOT NULL,
    action VARCHAR(20) NOT NULL,
    old_status VARCHAR(40) NULL,
    new_status VARCHAR(40) NOT NULL,
    actor_id INT NULL,
    actor_name VARCHAR(120) NOT NULL,
    actor_role VARCHAR(40) NOT NULL,
    reason VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_contract_history_action CHECK (action IN ('UPLOADED','CONFIRMED','REJECTED')),
    UNIQUE KEY uq_contract_history_action (ma_hop_dong, action),
    KEY idx_contract_history_timeline (ma_hop_dong, created_at, history_id),
    FOREIGN KEY (ma_hop_dong) REFERENCES HOP_DONG_THUC_TAP(ma_hop_dong) ON DELETE RESTRICT,
    FOREIGN KEY (actor_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO HOP_DONG_THUC_TAP_LICH_SU
    (ma_hop_dong, action, old_status, new_status, actor_id, actor_name, actor_role, created_at)
SELECT c.ma_hop_dong, 'UPLOADED', NULL, 'PENDING_CONFIRMATION', c.uploaded_by,
       COALESCE(u.ho_ten, 'Nhân sự'), COALESCE(u.vai_tro, 'HR'), c.uploaded_at
FROM HOP_DONG_THUC_TAP c
LEFT JOIN NGUOI_DUNG u ON u.ma_nguoi_dung = c.uploaded_by;
