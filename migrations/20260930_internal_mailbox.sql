-- MySQL 8 migration for the Sprint 2 internal mailbox.
-- Safe to re-run; it reuses NGUOI_DUNG, THONG_BAO and EMAIL_OUTBOX.
USE `internship_management`;

CREATE TABLE IF NOT EXISTS EMAIL_TEMPLATES (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    template_code VARCHAR(100) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body_html TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_by INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at DATETIME NULL,
    KEY idx_email_templates_active (is_active, category),
    CONSTRAINT fk_email_templates_creator
        FOREIGN KEY (created_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS INTERNAL_MESSAGE_THREADS (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    subject VARCHAR(255) NOT NULL,
    created_by INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_internal_threads_creator
        FOREIGN KEY (created_by) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS INTERNAL_MESSAGES (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id BIGINT NOT NULL,
    sender_id INT NULL,
    category VARCHAR(50) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    content_html TEXT NOT NULL,
    parent_id BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at DATETIME NULL,
    KEY idx_internal_messages_thread (thread_id, created_at),
    KEY idx_internal_messages_sender (sender_id, created_at),
    CONSTRAINT fk_internal_messages_thread
        FOREIGN KEY (thread_id) REFERENCES INTERNAL_MESSAGE_THREADS(id) ON DELETE RESTRICT,
    CONSTRAINT fk_internal_messages_sender
        FOREIGN KEY (sender_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL,
    CONSTRAINT fk_internal_messages_parent
        FOREIGN KEY (parent_id) REFERENCES INTERNAL_MESSAGES(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS INTERNAL_MESSAGE_RECIPIENTS (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    message_id BIGINT NOT NULL,
    receiver_id INT NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    read_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_internal_message_receiver (message_id, receiver_id),
    KEY idx_internal_recipient_inbox (receiver_id, is_read, created_at),
    KEY idx_internal_recipient_message (message_id),
    CONSTRAINT fk_internal_recipients_message
        FOREIGN KEY (message_id) REFERENCES INTERNAL_MESSAGES(id) ON DELETE RESTRICT,
    CONSTRAINT fk_internal_recipients_user
        FOREIGN KEY (receiver_id) REFERENCES NGUOI_DUNG(ma_nguoi_dung) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO EMAIL_TEMPLATES
    (template_code, title, subject, body_html, category)
VALUES
    ('MAU_DUYET_HO_SO', 'Duyệt hồ sơ', 'Hồ sơ thực tập của bạn đã được duyệt',
     '<p>Xin chào {ten_tts},</p><p>Hồ sơ đăng ký chương trình <strong>{ten_chuong_trinh}</strong> của bạn đã được duyệt.</p>',
     'KET_QUA_XET_DUYET'),
    ('MAU_TU_CHOI_HO_SO', 'Từ chối hồ sơ', 'Kết quả xét duyệt hồ sơ thực tập',
     '<p>Xin chào {ten_tts},</p><p>Hồ sơ đăng ký chương trình <strong>{ten_chuong_trinh}</strong> hiện chưa đáp ứng yêu cầu.</p>',
     'KET_QUA_XET_DUYET'),
    ('MAU_NHAC_BAO_CAO', 'Nhắc nộp báo cáo', 'Nhắc nộp báo cáo thực tập',
     '<p>Xin chào {ten_tts},</p><p>Vui lòng hoàn thành báo cáo thực tập trước ngày {ngay_het_han}.</p>',
     'THONG_BAO_CHUNG'),
    ('MAU_BO_SUNG_HO_SO', 'Bổ sung hồ sơ', 'Yêu cầu bổ sung hồ sơ thực tập',
     '<p>Xin chào {ten_tts},</p><p>Vui lòng kiểm tra và bổ sung các tài liệu còn thiếu trong hồ sơ.</p>',
     'BO_SUNG_HO_SO'),
    ('MAU_THONG_BAO_LICH', 'Thông báo lịch', 'Thông báo lịch thực tập',
     '<p>Xin chào {ten_tts},</p><p>Lịch thực tập của chương trình {ten_chuong_trinh} bắt đầu từ {ngay_bat_dau} đến {ngay_ket_thuc}.</p>',
     'THONG_BAO_CHUNG');
