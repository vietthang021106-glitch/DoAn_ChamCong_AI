-- ==========================================================
-- DoAn_ChamCong_AI — Script khởi tạo / đồng bộ schema
-- ==========================================================
-- Server  : localhost (Trusted_Connection=yes)
-- Database: DoAn_ChamCong_AI
-- Driver  : ODBC Driver 17 for SQL Server
--
-- IDEMPOTENT: Chạy lại an toàn, KHÔNG DROP bảng,
-- KHÔNG DELETE dữ liệu, KHÔNG thay đổi dữ liệu cũ.
--
-- Thứ tự tạo tuân theo phụ thuộc FK:
--   VaiTro → TaiKhoan
--   NhanVien → TaiKhoan, VaiTro
--   ThietBi
--   CaLamViec → PhanCaNhanVien
--   NhanVien  → PhanCaNhanVien
--   DanhMucBieuHien → LichSuTrangThai
--   LoaiCanhBao     → CanhBao
--   ChamCong        → CanhBao (MaTT)
--   NhanVien        → LichSuSucKhoe, ThongSoMoiTruong, CanhBao, ChamCong
-- ==========================================================

USE DoAn_ChamCong_AI;
GO

-- ==========================================================
-- 1. VaiTro
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'VaiTro'
)
BEGIN
    CREATE TABLE VaiTro (
        MaVT    INT            IDENTITY(1,1) PRIMARY KEY,
        TenVT   NVARCHAR(100)  NOT NULL
    );
    PRINT N'[OK] Tao bang VaiTro';
END
ELSE
    PRINT N'[SKIP] VaiTro da ton tai';
GO

-- ==========================================================
-- 2. NhanVien
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'NhanVien'
)
BEGIN
    CREATE TABLE NhanVien (
        MaNV    INT            IDENTITY(1,1) PRIMARY KEY,
        HoTen   NVARCHAR(150)  NOT NULL,
        Email   NVARCHAR(200)  NULL,
        MaVT    INT            NULL,
        CONSTRAINT FK_NhanVien_VaiTro
            FOREIGN KEY (MaVT) REFERENCES VaiTro(MaVT)
    );
    PRINT N'[OK] Tao bang NhanVien';
END
ELSE
    PRINT N'[SKIP] NhanVien da ton tai';
GO

-- ==========================================================
-- 3. TaiKhoan
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'TaiKhoan'
)
BEGIN
    CREATE TABLE TaiKhoan (
        MaTK        INT            IDENTITY(1,1) PRIMARY KEY,
        MaNV        INT            NOT NULL,
        TenDangNhap NVARCHAR(100)  NOT NULL UNIQUE,
        MatKhau     NVARCHAR(255)  NOT NULL,
        CONSTRAINT FK_TaiKhoan_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    PRINT N'[OK] Tao bang TaiKhoan';
END
ELSE
    PRINT N'[SKIP] TaiKhoan da ton tai';
GO

-- ==========================================================
-- 4. ThietBi
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'ThietBi'
)
BEGIN
    CREATE TABLE ThietBi (
        MaTB    INT            IDENTITY(1,1) PRIMARY KEY,
        TenTB   NVARCHAR(200)  NULL,
        ViTri   NVARCHAR(200)  NULL
    );
    -- Thêm thiết bị mặc định MaTB=1 nếu chưa có
    SET IDENTITY_INSERT ThietBi ON;
    INSERT INTO ThietBi (MaTB, TenTB, ViTri)
    VALUES (1, N'Camera chinh', N'Cua ra vao');
    SET IDENTITY_INSERT ThietBi OFF;
    PRINT N'[OK] Tao bang ThietBi + du lieu mac dinh';
END
ELSE
    PRINT N'[SKIP] ThietBi da ton tai';
GO

-- ==========================================================
-- 5. CaLamViec
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'CaLamViec'
)
BEGIN
    CREATE TABLE CaLamViec (
        MaCa        INT            IDENTITY(1,1) PRIMARY KEY,
        TenCa       NVARCHAR(100)  NOT NULL,
        GioBatDau   TIME           NOT NULL,
        GioKetThuc  TIME           NOT NULL
    );
    -- Ca hành chính mặc định
    INSERT INTO CaLamViec (TenCa, GioBatDau, GioKetThuc)
    VALUES (N'Ca hanh chinh', '08:00:00', '17:00:00');
    PRINT N'[OK] Tao bang CaLamViec + Ca hanh chinh';
END
ELSE
    PRINT N'[SKIP] CaLamViec da ton tai';
GO

-- ==========================================================
-- 6. PhanCaNhanVien
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'PhanCaNhanVien'
)
BEGIN
    CREATE TABLE PhanCaNhanVien (
        MaPhanCa    INT  IDENTITY(1,1) PRIMARY KEY,
        MaNV        INT  NOT NULL,
        MaCa        INT  NOT NULL,
        NgayLamViec DATE NOT NULL,
        CONSTRAINT FK_PhanCa_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV),
        CONSTRAINT FK_PhanCa_CaLamViec
            FOREIGN KEY (MaCa) REFERENCES CaLamViec(MaCa),
        CONSTRAINT UQ_PhanCa_NV_Ngay
            UNIQUE (MaNV, NgayLamViec)   -- mỗi NV chỉ 1 ca/ngày
    );
    PRINT N'[OK] Tao bang PhanCaNhanVien';
END
ELSE
    PRINT N'[SKIP] PhanCaNhanVien da ton tai';
GO

-- ==========================================================
-- 7. ChamCong
--    Nếu bảng đã tồn tại, chỉ bổ sung cột MaCa nếu thiếu.
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'ChamCong'
)
BEGIN
    CREATE TABLE ChamCong (
        MaCC    INT       IDENTITY(1,1) PRIMARY KEY,
        MaNV    INT       NOT NULL,
        GioVao  DATETIME  NULL,
        GioRa   DATETIME  NULL,
        MaTB    INT       NULL,
        MaCa    INT       NULL,
        CONSTRAINT FK_ChamCong_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV),
        CONSTRAINT FK_ChamCong_ThietBi
            FOREIGN KEY (MaTB) REFERENCES ThietBi(MaTB),
        CONSTRAINT FK_ChamCong_CaLamViec
            FOREIGN KEY (MaCa) REFERENCES CaLamViec(MaCa)
    );
    PRINT N'[OK] Tao bang ChamCong (voi MaCa)';
END
ELSE
BEGIN
    -- Bổ sung cột MaCa nếu chưa có (idempotent)
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = 'ChamCong' AND COLUMN_NAME = 'MaCa'
    )
    BEGIN
        ALTER TABLE ChamCong ADD MaCa INT NULL;
        ALTER TABLE ChamCong ADD CONSTRAINT FK_ChamCong_CaLamViec
            FOREIGN KEY (MaCa) REFERENCES CaLamViec(MaCa);
        PRINT N'[OK] Them cot MaCa vao ChamCong';
    END
    ELSE
        PRINT N'[SKIP] ChamCong.MaCa da ton tai';
END
GO

-- ==========================================================
-- 8. LichSuSucKhoe
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'LichSuSucKhoe'
)
BEGIN
    CREATE TABLE LichSuSucKhoe (
        MaSK     INT      IDENTITY(1,1) PRIMARY KEY,
        MaNV     INT      NOT NULL,
        NhipTim  INT      NULL,
        SpO2     INT      NULL,
        ThoiGian DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_SucKhoe_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    PRINT N'[OK] Tao bang LichSuSucKhoe';
END
ELSE
    PRINT N'[SKIP] LichSuSucKhoe da ton tai';
GO

-- ==========================================================
-- 9. ThongSoMoiTruong
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'ThongSoMoiTruong'
)
BEGIN
    CREATE TABLE ThongSoMoiTruong (
        MaMT     INT      IDENTITY(1,1) PRIMARY KEY,
        NhietDo  FLOAT    NULL,
        DoAm     FLOAT    NULL,
        ThoiGian DATETIME DEFAULT GETDATE(),
        MaTB     INT      NULL,
        CONSTRAINT FK_MoiTruong_ThietBi
            FOREIGN KEY (MaTB) REFERENCES ThietBi(MaTB)
    );
    PRINT N'[OK] Tao bang ThongSoMoiTruong';
END
ELSE
    PRINT N'[SKIP] ThongSoMoiTruong da ton tai';
GO

-- ==========================================================
-- 10. DanhMucBieuHien  (danh mục trạng thái AI)
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'DanhMucBieuHien'
)
BEGIN
    CREATE TABLE DanhMucBieuHien (
        MaBieuHien  INT            IDENTITY(1,1) PRIMARY KEY,
        TenBieuHien NVARCHAR(100)  NOT NULL
    );
    -- Dữ liệu mặc định khớp với mapping trong database.py
    INSERT INTO DanhMucBieuHien (TenBieuHien)
    VALUES
        (N'binh_thuong'),   -- 1
        (N'buon_ngu'),      -- 2
        (N'guc_dau'),       -- 3
        (N'meo_mieng');     -- 4
    PRINT N'[OK] Tao bang DanhMucBieuHien + du lieu mac dinh';
END
ELSE
    PRINT N'[SKIP] DanhMucBieuHien da ton tai';
GO

-- ==========================================================
-- 11. LichSuTrangThai  (log trạng thái AI mỗi 5 giây)
--     Schema THẬT: MaTT, MaNV, MaBieuHien, ThoiGian
--     KHÔNG có: TrangThai (text), GiaTri, MoTa, DaXuLy
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'LichSuTrangThai'
)
BEGIN
    CREATE TABLE LichSuTrangThai (
        MaTT        INT      IDENTITY(1,1) PRIMARY KEY,
        MaNV        INT      NOT NULL,
        MaBieuHien  INT      NOT NULL DEFAULT 1,
        ThoiGian    DATETIME DEFAULT GETDATE(),
        CONSTRAINT FK_TrangThai_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV),
        CONSTRAINT FK_TrangThai_BieuHien
            FOREIGN KEY (MaBieuHien) REFERENCES DanhMucBieuHien(MaBieuHien)
    );
    PRINT N'[OK] Tao bang LichSuTrangThai (MaTT/MaNV/MaBieuHien/ThoiGian)';
END
ELSE
    PRINT N'[SKIP] LichSuTrangThai da ton tai';
GO

-- ==========================================================
-- 12. LoaiCanhBao  (danh mục loại cảnh báo)
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'LoaiCanhBao'
)
BEGIN
    CREATE TABLE LoaiCanhBao (
        MaLoaiCB  INT            IDENTITY(1,1) PRIMARY KEY,
        TenLoaiCB NVARCHAR(100)  NOT NULL
    );
    INSERT INTO LoaiCanhBao (TenLoaiCB)
    VALUES
        (N'Canh bao trang thai AI'),  -- 1
        (N'Canh bao moi truong'),     -- 2
        (N'Canh bao suc khoe');       -- 3
    PRINT N'[OK] Tao bang LoaiCanhBao + du lieu mac dinh';
END
ELSE
    PRINT N'[SKIP] LoaiCanhBao da ton tai';
GO

-- ==========================================================
-- 13. CanhBao  (sự kiện cảnh báo được ghi nhận)
--     Schema THẬT: MaCB, MaNV, MaLoaiCB, NoiDung,
--                  ThoiGian, MaTT, MaTB
--     KHÔNG có: GiaTri (float riêng), MoTa (text riêng), DaXuLy
-- ==========================================================
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'CanhBao'
)
BEGIN
    CREATE TABLE CanhBao (
        MaCB      INT            IDENTITY(1,1) PRIMARY KEY,
        MaNV      INT            NOT NULL,
        MaLoaiCB  INT            NOT NULL DEFAULT 1,
        NoiDung   NVARCHAR(500)  NULL,
        ThoiGian  DATETIME       DEFAULT GETDATE(),
        MaTT      INT            NULL,   -- FK -> LichSuTrangThai
        MaTB      INT            NULL,   -- FK -> ThietBi
        CONSTRAINT FK_CanhBao_NhanVien
            FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV),
        CONSTRAINT FK_CanhBao_LoaiCanhBao
            FOREIGN KEY (MaLoaiCB) REFERENCES LoaiCanhBao(MaLoaiCB),
        CONSTRAINT FK_CanhBao_TrangThai
            FOREIGN KEY (MaTT) REFERENCES LichSuTrangThai(MaTT),
        CONSTRAINT FK_CanhBao_ThietBi
            FOREIGN KEY (MaTB) REFERENCES ThietBi(MaTB)
    );
    PRINT N'[OK] Tao bang CanhBao (MaCB/MaNV/MaLoaiCB/NoiDung/ThoiGian/MaTT/MaTB)';
END
ELSE
    PRINT N'[SKIP] CanhBao da ton tai';
GO

-- ==========================================================
-- Hoàn tất
-- ==========================================================
PRINT N'';
PRINT N'========================================';
PRINT N'Hoan tat dong bo schema DoAn_ChamCong_AI';
PRINT N'Server  : localhost';
PRINT N'Database: DoAn_ChamCong_AI';
PRINT N'========================================';
GO
