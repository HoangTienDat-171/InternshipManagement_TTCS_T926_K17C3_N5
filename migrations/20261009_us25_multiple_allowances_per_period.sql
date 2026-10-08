-- US25: allow multiple allowance payments for one internship profile in a period.
-- Keeps existing allowance rows and drops only the old one-row-per-profile/period constraint.
-- Safe to re-run; it does not modify or delete data.

SET @allowance_unique_index_count := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_THUC_TAP'
      AND INDEX_NAME = 'uq_phu_cap_ho_so_ky'
);
SET @allowance_support_index_count := (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'PHU_CAP_THUC_TAP'
      AND INDEX_NAME = 'idx_phu_cap_profile_period'
);
SET @allowance_support_ddl := IF(@allowance_support_index_count = 0,
    'CREATE INDEX idx_phu_cap_profile_period ON PHU_CAP_THUC_TAP (ma_ho_so, ky)',
    'SELECT 1');
PREPARE allowance_support_stmt FROM @allowance_support_ddl;
EXECUTE allowance_support_stmt;
DEALLOCATE PREPARE allowance_support_stmt;

SET @allowance_ddl := IF(@allowance_unique_index_count > 0,
    'ALTER TABLE PHU_CAP_THUC_TAP DROP INDEX uq_phu_cap_ho_so_ky',
    'SELECT 1');
PREPARE allowance_multi_period_stmt FROM @allowance_ddl;
EXECUTE allowance_multi_period_stmt;
DEALLOCATE PREPARE allowance_multi_period_stmt;
