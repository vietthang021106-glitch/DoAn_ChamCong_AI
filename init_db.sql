-- ==========================================================
-- DoAn_ChamCong_AI — Script khởi tạo bảng bổ sung (Phase 2)
-- Chạy script này trên SQL Server: HEHE\admin
-- Database: DoAn_ChamCong_AI
-- ==========================================================

USE DoAn_ChamCong_AI;
GO

-- ----------------------------------------------------------
-- Bảng lưu trạng thái AI theo từng frame (log chi tiết)
-- ----------------------------------------------------------
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'LichSuTrangThai'
)
BEGIN
    CREATE TABLE LichSuTrangThai (
        MaTrangThai INT IDENTITY(1,1) PRIMARY KEY,
        MaNV        INT            NOT NULL,
        TrangThai   NVARCHAR(50)   NOT NULL,   -- 'buon_ngu', 'guc_dau', 'binh_thuong'
        GiaTri      FLOAT          NULL,        -- EAR value hoặc góc nghiêng
        ThoiGian    DATETIME       DEFAULT GETDATE(),
        CONSTRAINT FK_LichSuTrangThai_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    PRINT 'Da tao bang LichSuTrangThai';
END
ELSE
    PRINT 'Bang LichSuTrangThai da ton tai, bo qua.';
GO

-- ----------------------------------------------------------
-- Bảng lưu cảnh báo vi phạm (chỉ lưu khi phát hiện vấn đề)
-- ----------------------------------------------------------
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'CanhBao'
)
BEGIN
    CREATE TABLE CanhBao (
        MaCanhBao   INT IDENTITY(1,1) PRIMARY KEY,
        MaNV        INT            NOT NULL,
        LoaiCanhBao NVARCHAR(100)  NOT NULL,   -- 'Buon ngu', 'Guc dau'
        MoTa        NVARCHAR(500)  NULL,
        GiaTri      FLOAT          NULL,        -- EAR hoặc góc tại thời điểm phát hiện
        ThoiGian    DATETIME       DEFAULT GETDATE(),
        DaXuLy      BIT            DEFAULT 0,
        CONSTRAINT FK_CanhBao_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    PRINT 'Da tao bang CanhBao';
END
ELSE
    PRINT 'Bang CanhBao da ton tai, bo qua.';
GO

-- ----------------------------------------------------------
-- Dữ liệu mẫu: thêm cột NhietDo vào ThongSoMoiTruong nếu cần
-- (bỏ qua nếu đã có)
-- ----------------------------------------------------------
PRINT 'Hoan tat khoi tao CSDL Phase 2.';
GO
