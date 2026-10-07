-- Migration: US12 + US30 - Phân công Mentor theo ngữ cảnh Chương trình thực tập / Đơn ứng tuyển
-- Bỏ ràng buộc UNIQUE(ma_ho_so) toàn đời; liên kết phân công vào ma_chuong_trinh và ma_ung_tuyen.

DELIMITER $$

CREATE PROCEDURE upgrade_mentor_assignment_schema()
BEGIN
    -- 1. Bổ sung cột ma_chuong_trinh nếu chưa có
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHAN_CONG_MENTOR_TTS' AND COLUMN_NAME = 'ma_chuong_trinh'
    ) THEN
        ALTER TABLE PHAN_CONG_MENTOR_TTS ADD COLUMN ma_chuong_trinh INT NULL AFTER ma_ho_so;
    END IF;

    -- 2. Bổ sung cột ma_ung_tuyen nếu chưa có
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHAN_CONG_MENTOR_TTS' AND COLUMN_NAME = 'ma_ung_tuyen'
    ) THEN
        ALTER TABLE PHAN_CONG_MENTOR_TTS ADD COLUMN ma_ung_tuyen INT NULL AFTER ma_chuong_trinh;
    END IF;

    -- 3. Xóa UNIQUE constraint cũ trên ma_ho_so đơn lẻ nếu tồn tại
    IF EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'PHAN_CONG_MENTOR_TTS'
          AND COLUMN_NAME = 'ma_ho_so'
          AND NON_UNIQUE = 0
          AND INDEX_NAME != 'PRIMARY'
    ) THEN
        -- Tìm tên index duy nhất trên ma_ho_so
        SET @uq_index = (
            SELECT INDEX_NAME FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'PHAN_CONG_MENTOR_TTS'
              AND COLUMN_NAME = 'ma_ho_so'
              AND NON_UNIQUE = 0
              AND INDEX_NAME != 'PRIMARY'
            LIMIT 1
        );
        SET @drop_sql = CONCAT('ALTER TABLE PHAN_CONG_MENTOR_TTS DROP INDEX `', @uq_index, '`');
        PREPARE stmt FROM @drop_sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;

    -- 4. Bổ sung INDEX cho ma_ho_so (không unique)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHAN_CONG_MENTOR_TTS' AND INDEX_NAME = 'idx_phan_cong_ho_so'
    ) THEN
        ALTER TABLE PHAN_CONG_MENTOR_TTS ADD KEY idx_phan_cong_ho_so (ma_ho_so);
    END IF;

    -- 5. Bổ sung INDEX cho ma_chuong_trinh
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHAN_CONG_MENTOR_TTS' AND INDEX_NAME = 'idx_phan_cong_chuong_trinh'
    ) THEN
        ALTER TABLE PHAN_CONG_MENTOR_TTS ADD KEY idx_phan_cong_chuong_trinh (ma_chuong_trinh);
    END IF;

    -- 6. Ràng buộc UNIQUE(ma_ho_so, ma_chuong_trinh) để một TTS có tối đa 1 Mentor trong cùng 1 chương trình
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHAN_CONG_MENTOR_TTS' AND INDEX_NAME = 'uq_phan_cong_ho_so_ct'
    ) THEN
        ALTER TABLE PHAN_CONG_MENTOR_TTS ADD UNIQUE KEY uq_phan_cong_ho_so_ct (ma_ho_so, ma_chuong_trinh);
    END IF;

    -- 7. Bổ sung Foreign Keys cho ma_chuong_trinh và ma_ung_tuyen nếu chưa có
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHAN_CONG_MENTOR_TTS' AND CONSTRAINT_NAME = 'fk_phan_cong_chuong_trinh'
    ) THEN
        ALTER TABLE PHAN_CONG_MENTOR_TTS
        ADD CONSTRAINT fk_phan_cong_chuong_trinh
        FOREIGN KEY (ma_chuong_trinh) REFERENCES CHUONG_TRINH_THUC_TAP(ma_chuong_trinh) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHAN_CONG_MENTOR_TTS' AND CONSTRAINT_NAME = 'fk_phan_cong_ung_tuyen'
    ) THEN
        ALTER TABLE PHAN_CONG_MENTOR_TTS
        ADD CONSTRAINT fk_phan_cong_ung_tuyen
        FOREIGN KEY (ma_ung_tuyen) REFERENCES UNG_TUYEN_CHUONG_TRINH(ma_ung_tuyen) ON DELETE SET NULL;
    END IF;

    -- 8. Backfill ma_chuong_trinh và ma_ung_tuyen cho bản ghi phân công cũ nếu hồ sơ có đúng 1 chương trình DaDuyet
    UPDATE PHAN_CONG_MENTOR_TTS p
    JOIN UNG_TUYEN_CHUONG_TRINH u ON u.ma_ho_so = p.ma_ho_so AND u.trang_thai = 'DaDuyet'
    SET p.ma_chuong_trinh = u.ma_chuong_trinh, p.ma_ung_tuyen = u.ma_ung_tuyen
    WHERE p.ma_chuong_trinh IS NULL;
END$$

DELIMITER ;

CALL upgrade_mentor_assignment_schema();
DROP PROCEDURE IF EXISTS upgrade_mentor_assignment_schema;
