-- Run after add_scan_history.sql. Refuse to discard populated legacy history.
-- DDL commits implicitly in MariaDB; each step is safe to rerun after inspection.
SET NAMES utf8mb4;
USE `DoAn_ChamCong_AI_MariaDB`;

DROP PROCEDURE IF EXISTS `migrate_scan_reason_catalog_v1`;
DELIMITER $$
CREATE PROCEDURE `migrate_scan_reason_catalog_v1`()
BEGIN
    DECLARE has_legacy_column INT DEFAULT 0;
    DECLARE has_reason_id INT DEFAULT 0;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'LichSuQuet'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'LichSuQuet does not exist; run add_scan_history.sql first.';
    END IF;

    SELECT COUNT(*) INTO has_legacy_column
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'LichSuQuet' AND COLUMN_NAME = 'LyDo';
    SELECT COUNT(*) INTO has_reason_id
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'LichSuQuet' AND COLUMN_NAME = 'MaLyDo';

    IF has_legacy_column > 0 AND EXISTS (SELECT 1 FROM LichSuQuet LIMIT 1) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Legacy LichSuQuet is not empty; stop and backfill before removing LyDo.';
    END IF;
    IF has_legacy_column = 0 AND has_reason_id = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unexpected LichSuQuet schema: neither LyDo nor MaLyDo exists.';
    END IF;

    CREATE TABLE IF NOT EXISTS `LoaiLyDoQuet` (
        `MaLyDo` INT NOT NULL AUTO_INCREMENT,
        `MaCode` VARCHAR(50) NOT NULL,
        `TenLyDo` VARCHAR(100) NOT NULL,
        `MoTa` VARCHAR(255) NULL,
        `TrangThai` TINYINT(1) NOT NULL DEFAULT 1,
        PRIMARY KEY (`MaLyDo`),
        UNIQUE KEY `UQ_LoaiLyDoQuet_MaCode` (`MaCode`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

    INSERT INTO `LoaiLyDoQuet` (`MaCode`, `TenLyDo`, `MoTa`)
    SELECT seed.MaCode, seed.TenLyDo, seed.MoTa
    FROM (
        SELECT 'KHONG_NHAN_DIEN' AS MaCode, 'Không nhận diện được' AS TenLyDo,
            'Không xác định được nhân viên từ khuôn mặt quét.' AS MoTa
        UNION ALL SELECT 'NHIEU_KHUON_MAT', 'Có nhiều khuôn mặt',
            'Phát hiện nhiều khuôn mặt nên không xác định được một nhân viên duy nhất.'
        UNION ALL SELECT 'KHONG_CO_PHAN_CA', 'Không có phân ca',
            'Nhân viên đã được xác định nhưng không có phân ca trong ngày.'
        UNION ALL SELECT 'CA_DA_KET_THUC', 'Ca đã kết thúc',
            'Lần quét xảy ra khi ca làm việc đã kết thúc.'
        UNION ALL SELECT 'DA_HOAN_THANH', 'Đã hoàn thành chấm công',
            'Nhân viên đã có đủ giờ vào và giờ ra.'
    ) AS seed
    LEFT JOIN LoaiLyDoQuet existing ON existing.MaCode = seed.MaCode
    WHERE existing.MaLyDo IS NULL;

    IF (SELECT COUNT(*) FROM LoaiLyDoQuet) <> 5 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unexpected scan reason catalog; expected exactly five codes.';
    END IF;

    ALTER TABLE `LichSuQuet`
        ADD COLUMN IF NOT EXISTS `MaLyDo` INT NOT NULL AFTER `MaCa`;

    IF EXISTS (
        SELECT 1 FROM LichSuQuet SQ
        LEFT JOIN LoaiLyDoQuet LD ON LD.MaLyDo = SQ.MaLyDo
        WHERE LD.MaLyDo IS NULL
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unmapped MaLyDo exists; LyDo must not be removed.';
    END IF;

    ALTER TABLE `LichSuQuet`
        MODIFY COLUMN `MaLyDo` INT NOT NULL,
        ADD INDEX IF NOT EXISTS `IX_LichSuQuet_MaLyDo` (`MaLyDo`),
        ADD INDEX IF NOT EXISTS `IX_LichSuQuet_ThietBi_MaLyDo_ThoiGian` (`MaTB`, `MaLyDo`, `ThoiGianQuet`);

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'LichSuQuet'
            AND CONSTRAINT_NAME = 'FK_LichSuQuet_LoaiLyDoQuet' AND CONSTRAINT_TYPE = 'FOREIGN KEY'
    ) THEN
        ALTER TABLE `LichSuQuet`
            ADD CONSTRAINT `FK_LichSuQuet_LoaiLyDoQuet`
            FOREIGN KEY (`MaLyDo`) REFERENCES `LoaiLyDoQuet` (`MaLyDo`)
            ON UPDATE RESTRICT ON DELETE RESTRICT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.KEY_COLUMN_USAGE K
        INNER JOIN information_schema.REFERENTIAL_CONSTRAINTS R
            ON R.CONSTRAINT_SCHEMA = K.CONSTRAINT_SCHEMA AND R.CONSTRAINT_NAME = K.CONSTRAINT_NAME
        WHERE K.CONSTRAINT_SCHEMA = DATABASE() AND K.TABLE_NAME = 'LichSuQuet'
            AND K.COLUMN_NAME = 'MaLyDo' AND K.REFERENCED_TABLE_NAME = 'LoaiLyDoQuet'
            AND K.REFERENCED_COLUMN_NAME = 'MaLyDo'
            AND R.UPDATE_RULE = 'RESTRICT' AND R.DELETE_RULE = 'RESTRICT'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Reason foreign key verification failed; LyDo must not be removed.';
    END IF;

    IF has_legacy_column > 0 THEN
        ALTER TABLE `LichSuQuet` DROP INDEX IF EXISTS `IX_LichSuQuet_ThietBi_LyDo_ThoiGian`;
        ALTER TABLE `LichSuQuet` DROP COLUMN `LyDo`;
    END IF;
END$$
CALL `migrate_scan_reason_catalog_v1`()$$
DROP PROCEDURE `migrate_scan_reason_catalog_v1`$$
DELIMITER ;
