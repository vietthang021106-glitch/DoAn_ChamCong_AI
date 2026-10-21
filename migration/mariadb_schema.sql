-- MariaDB application schema; only the fixed scan-reason catalog is seeded.
-- No employee, attendance, or AI data is copied or seeded.
-- MariaDB 10.4 accepts DESC index syntax but does not implement descending indexes.

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS `DoAn_ChamCong_AI_MariaDB`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_general_ci;

USE `DoAn_ChamCong_AI_MariaDB`;

CREATE TABLE `VaiTro` (
    `MaVaiTro` INT NOT NULL AUTO_INCREMENT,
    `TenVaiTro` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    PRIMARY KEY (`MaVaiTro`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `ThietBi` (
    `MaTB` INT NOT NULL AUTO_INCREMENT,
    `LoaiTB` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    `TrangThai` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    PRIMARY KEY (`MaTB`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `CaLamViec` (
    `MaCa` INT NOT NULL AUTO_INCREMENT,
    `TenCa` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
    `GioBatDau` TIME NOT NULL,
    `GioKetThuc` TIME NOT NULL,
    `TrangThai` TINYINT(1) NOT NULL DEFAULT 1,
    PRIMARY KEY (`MaCa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `DanhMucBieuHien` (
    `MaBieuHien` INT NOT NULL AUTO_INCREMENT,
    `TenBieuHien` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    `MoTa` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    PRIMARY KEY (`MaBieuHien`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `LoaiCanhBao` (
    `MaLoaiCB` INT NOT NULL AUTO_INCREMENT,
    `TenLoaiCB` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    PRIMARY KEY (`MaLoaiCB`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `NhanVien` (
    `MaNV` INT NOT NULL AUTO_INCREMENT,
    `HoTen` VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    `AnhKhuonMat` LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    `MaVaiTro` INT NULL,
    PRIMARY KEY (`MaNV`),
    CONSTRAINT `FK__NhanVien__MaVaiT__5812160E`
        FOREIGN KEY (`MaVaiTro`) REFERENCES `VaiTro` (`MaVaiTro`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `TaiKhoan` (
    `MaTK` INT NOT NULL AUTO_INCREMENT,
    `MaNV` INT NULL,
    `TenDangNhap` VARCHAR(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    `MatKhau` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    PRIMARY KEY (`MaTK`),
    CONSTRAINT `UQ__TaiKhoan__55F68FC0A7B628E6` UNIQUE KEY (`TenDangNhap`),
    CONSTRAINT `FK__TaiKhoan__MaNV__59063A47`
        FOREIGN KEY (`MaNV`) REFERENCES `NhanVien` (`MaNV`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `LichSuSucKhoe` (
    `MaSK` INT NOT NULL AUTO_INCREMENT,
    `MaNV` INT NULL,
    `NhipTim` INT NULL,
    `SpO2` DOUBLE NULL,
    `ThoiGian` DATETIME(3) NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (`MaSK`),
    CONSTRAINT `FK__LichSuSucK__MaNV__5535A963`
        FOREIGN KEY (`MaNV`) REFERENCES `NhanVien` (`MaNV`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `LichSuTrangThai` (
    `MaTT` INT NOT NULL AUTO_INCREMENT,
    `MaNV` INT NULL,
    `MaBieuHien` INT NULL,
    `ThoiGian` DATETIME(3) NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (`MaTT`),
    CONSTRAINT `FK__LichSuTra__MaBie__5629CD9C`
        FOREIGN KEY (`MaBieuHien`) REFERENCES `DanhMucBieuHien` (`MaBieuHien`),
    CONSTRAINT `FK__LichSuTran__MaNV__571DF1D5`
        FOREIGN KEY (`MaNV`) REFERENCES `NhanVien` (`MaNV`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `PhanCaNhanVien` (
    `MaPhanCa` INT NOT NULL AUTO_INCREMENT,
    `MaNV` INT NOT NULL,
    `MaCa` INT NOT NULL,
    `NgayLamViec` DATE NOT NULL,
    PRIMARY KEY (`MaPhanCa`),
    CONSTRAINT `UQ_PhanCaNhanVien_MaNV_NgayLamViec` UNIQUE KEY (`MaNV`, `NgayLamViec`),
    KEY `IX_PhanCaNhanVien_NgayLamViec` (`NgayLamViec`, `MaNV`, `MaCa`),
    CONSTRAINT `FK_PhanCaNhanVien_NhanVien`
        FOREIGN KEY (`MaNV`) REFERENCES `NhanVien` (`MaNV`),
    CONSTRAINT `FK_PhanCaNhanVien_CaLamViec`
        FOREIGN KEY (`MaCa`) REFERENCES `CaLamViec` (`MaCa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `ChamCong` (
    `MaCC` INT NOT NULL AUTO_INCREMENT,
    `MaNV` INT NULL,
    `GioVao` DATETIME(3) NULL,
    `GioRa` DATETIME(3) NULL,
    `MaTB` INT NULL,
    `MaCa` INT NULL,
    `AnhVao` LONGBLOB NULL,
    `AnhRa` LONGBLOB NULL,
    PRIMARY KEY (`MaCC`),
    KEY `IX_ChamCong_MaNV_GioVao` (`MaNV`, `GioVao`),
    CONSTRAINT `FK__ChamCong__MaNV__534D60F1`
        FOREIGN KEY (`MaNV`) REFERENCES `NhanVien` (`MaNV`),
    CONSTRAINT `FK__ChamCong__MaTB__5441852A`
        FOREIGN KEY (`MaTB`) REFERENCES `ThietBi` (`MaTB`),
    CONSTRAINT `FK_ChamCong_CaLamViec`
        FOREIGN KEY (`MaCa`) REFERENCES `CaLamViec` (`MaCa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `LoaiLyDoQuet` (
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

CREATE TABLE `LichSuQuet` (
    `MaLanQuet` INT NOT NULL AUTO_INCREMENT,
    `MaNV` INT NULL,
    `MaTB` INT NULL,
    `MaCa` INT NULL,
    `MaLyDo` INT NOT NULL,
    `ThoiGianQuet` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `AnhQuet` LONGBLOB NOT NULL,
    `SoKhuonMat` TINYINT UNSIGNED NULL,
    `DoTinCay` DECIMAL(5,4) NULL,
    `ChiTiet` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    PRIMARY KEY (`MaLanQuet`),
    KEY `IX_LichSuQuet_ThoiGian` (`ThoiGianQuet`),
    KEY `IX_LichSuQuet_NhanVien_ThoiGian` (`MaNV`, `ThoiGianQuet`),
    KEY `IX_LichSuQuet_MaLyDo` (`MaLyDo`),
    KEY `IX_LichSuQuet_ThietBi_MaLyDo_ThoiGian` (`MaTB`, `MaLyDo`, `ThoiGianQuet`),
    CONSTRAINT `FK_LichSuQuet_LoaiLyDoQuet`
        FOREIGN KEY (`MaLyDo`) REFERENCES `LoaiLyDoQuet` (`MaLyDo`)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT `FK_LichSuQuet_NhanVien`
        FOREIGN KEY (`MaNV`) REFERENCES `NhanVien` (`MaNV`),
    CONSTRAINT `FK_LichSuQuet_ThietBi`
        FOREIGN KEY (`MaTB`) REFERENCES `ThietBi` (`MaTB`),
    CONSTRAINT `FK_LichSuQuet_CaLamViec`
        FOREIGN KEY (`MaCa`) REFERENCES `CaLamViec` (`MaCa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `FaceEmbedding` (
    `MaEmbedding` INT NOT NULL AUTO_INCREMENT,
    `MaNV` INT NOT NULL,
    `VectorData` LONGBLOB NOT NULL,
    `AnhKhuonMat` LONGBLOB NULL,
    `SoChieu` INT NOT NULL DEFAULT 512,
    `ThoiGianTao` DATETIME(3) NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (`MaEmbedding`),
    CONSTRAINT `FK_FaceEmbedding_NhanVien`
        FOREIGN KEY (`MaNV`) REFERENCES `NhanVien` (`MaNV`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

CREATE TABLE `CanhBao` (
    `MaCB` INT NOT NULL AUTO_INCREMENT,
    `MaNV` INT NULL,
    `MaLoaiCB` INT NULL,
    `NoiDung` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NULL,
    `ThoiGian` DATETIME(3) NULL DEFAULT CURRENT_TIMESTAMP(3),
    `MaTT` INT NULL,
    `MaTB` INT NULL,
    PRIMARY KEY (`MaCB`),
    CONSTRAINT `FK__CanhBao__MaLoaiC__4F7CD00D`
        FOREIGN KEY (`MaLoaiCB`) REFERENCES `LoaiCanhBao` (`MaLoaiCB`),
    CONSTRAINT `FK__CanhBao__MaNV__5070F446`
        FOREIGN KEY (`MaNV`) REFERENCES `NhanVien` (`MaNV`),
    CONSTRAINT `FK__CanhBao__MaTB__5165187F`
        FOREIGN KEY (`MaTB`) REFERENCES `ThietBi` (`MaTB`),
    CONSTRAINT `FK__CanhBao__MaTT__52593CB8`
        FOREIGN KEY (`MaTT`) REFERENCES `LichSuTrangThai` (`MaTT`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

