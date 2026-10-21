USE `DoAn_ChamCong_AI_MariaDB`;

CREATE TABLE IF NOT EXISTS `LichSuQuet` (
    `MaLanQuet` INT NOT NULL AUTO_INCREMENT,
    `MaNV` INT NULL,
    `MaTB` INT NULL,
    `MaCa` INT NULL,
    `ThoiGianQuet` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `LyDo` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
    `AnhQuet` LONGBLOB NOT NULL,
    `SoKhuonMat` TINYINT UNSIGNED NULL,
    `DoTinCay` DECIMAL(5,4) NULL,
    `ChiTiet` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    PRIMARY KEY (`MaLanQuet`),
    KEY `IX_LichSuQuet_ThoiGian` (`ThoiGianQuet`),
    KEY `IX_LichSuQuet_NhanVien_ThoiGian` (`MaNV`, `ThoiGianQuet`),
    KEY `IX_LichSuQuet_ThietBi_LyDo_ThoiGian` (`MaTB`, `LyDo`, `ThoiGianQuet`),
    CONSTRAINT `FK_LichSuQuet_NhanVien`
        FOREIGN KEY (`MaNV`) REFERENCES `NhanVien` (`MaNV`),
    CONSTRAINT `FK_LichSuQuet_ThietBi`
        FOREIGN KEY (`MaTB`) REFERENCES `ThietBi` (`MaTB`),
    CONSTRAINT `FK_LichSuQuet_CaLamViec`
        FOREIGN KEY (`MaCa`) REFERENCES `CaLamViec` (`MaCa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;
