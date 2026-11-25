-- Soft-delete flag for existing MariaDB installations.
-- Read-only preflight: verify the column and its default before applying this migration.
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'NhanVien'
  AND COLUMN_NAME = 'DaXoa';

-- Safe to re-run on MariaDB versions supporting ADD COLUMN IF NOT EXISTS.
-- Existing employees receive DaXoa = 0 through the NOT NULL DEFAULT declaration.
ALTER TABLE `NhanVien`
    ADD COLUMN IF NOT EXISTS `DaXoa` TINYINT(1) NOT NULL DEFAULT 0;

-- Verify after migration: this should return the DaXoa metadata row.
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'NhanVien'
  AND COLUMN_NAME = 'DaXoa';
