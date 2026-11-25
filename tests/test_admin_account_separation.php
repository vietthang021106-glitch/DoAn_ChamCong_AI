<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/AccountModel.php';
require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Model/AttendanceModel.php';
require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';

if (!in_array('sqlite', PDO::getAvailableDrivers(), true)) {
    fwrite(STDERR, "SKIP: PDO SQLite driver is unavailable.\n");
    exit(2);
}

$assertions = 0;
$assert = static function (bool $condition, string $message) use (&$assertions): void {
    $assertions++;
    if (!$condition) {
        throw new RuntimeException('FAIL: ' . $message);
    }
};

// This fixture deliberately has no NhanVien/VaiTro tables: migrated Admin auth
// must be independent of employee data.
$adminPdo = new PDO('sqlite::memory:', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$adminPdo->exec(<<<'SQL'
    CREATE TABLE TaiKhoan (
        MaTK INTEGER PRIMARY KEY,
        MaNV INTEGER NULL,
        LoaiTaiKhoan TEXT NOT NULL DEFAULT 'LEGACY' CHECK (LoaiTaiKhoan IN ('ADMIN', 'LEGACY')),
        AdminSingleton INTEGER GENERATED ALWAYS AS (
            CASE WHEN LoaiTaiKhoan = 'ADMIN' THEN 1 ELSE NULL END
        ) STORED UNIQUE,
        TenDangNhap TEXT NOT NULL UNIQUE,
        MatKhau TEXT NOT NULL,
        CHECK (LoaiTaiKhoan <> 'ADMIN' OR MaNV IS NULL)
    )
    SQL);
$adminHash = password_hash('fixture-admin-password', PASSWORD_DEFAULT);
$insertAdmin = $adminPdo->prepare(
    'INSERT INTO TaiKhoan (MaNV, LoaiTaiKhoan, TenDangNhap, MatKhau) VALUES (NULL, :kind, :username, :password)'
);
$insertAdmin->execute([
    'kind' => 'ADMIN',
    'username' => 'admin',
    'password' => $adminHash,
]);

$adminAccounts = new AccountModel($adminPdo);
$admin = $adminAccounts->authenticate('admin', 'fixture-admin-password');
$assert($admin !== null, 'Admin login works without a NhanVien table');
$assert(($admin['is_admin'] ?? false) === true, 'login returns an explicit Admin session identity');
$assert(!array_key_exists('ma_nv', $admin), 'Admin session has no MaNV');
$assert($adminAccounts->isAdminAccountActive(1), 'Admin account remains active independently of employees');

$secondAdminRejected = false;
try {
    $insertAdmin->execute([
        'kind' => 'ADMIN',
        'username' => 'second-admin',
        'password' => password_hash('another-password', PASSWORD_DEFAULT),
    ]);
} catch (PDOException) {
    $secondAdminRejected = true;
}
$assert($secondAdminRejected, 'database unique generated slot rejects a second Admin');
$assert((int)$adminPdo->query("SELECT COUNT(*) FROM TaiKhoan WHERE LoaiTaiKhoan = 'ADMIN'")->fetchColumn() === 1, 'only one Admin row exists');

// Before the migration reaches older installations, the legacy login path also
// refuses ambiguous role-linked Admin accounts.
$legacyPdo = new PDO('sqlite::memory:', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$legacyPdo->exec(<<<'SQL'
    CREATE TABLE VaiTro (MaVaiTro INTEGER PRIMARY KEY, TenVaiTro TEXT NOT NULL);
    CREATE TABLE NhanVien (MaNV INTEGER PRIMARY KEY, HoTen TEXT, MaVaiTro INTEGER);
    CREATE TABLE TaiKhoan (
        MaTK INTEGER PRIMARY KEY,
        MaNV INTEGER NOT NULL,
        TenDangNhap TEXT NOT NULL UNIQUE,
        MatKhau TEXT NOT NULL
    );
    INSERT INTO VaiTro VALUES (1, 'Quản trị viên');
    INSERT INTO NhanVien VALUES (1, 'Legacy Admin A', 1), (2, 'Legacy Admin B', 1);
    INSERT INTO TaiKhoan VALUES
        (1, 1, 'admin-a', 'secret-a'),
        (2, 2, 'admin-b', 'secret-b');
    SQL);
$legacyAccounts = new AccountModel($legacyPdo);
$assert($legacyAccounts->authenticate('admin-a', 'secret-a') === null, 'legacy backend rejects ambiguous Admin accounts');
$assert(!$legacyAccounts->isAdminAccountActive(1), 'ambiguous legacy Admin sessions are rejected');

// A separate employee database exercises creation, employee selectors, gallery
// filtering and a reset of employee rows while keeping the Admin login intact.
$pdo = new PDO('sqlite::memory:', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$pdo->exec('PRAGMA foreign_keys = ON');
$pdo->exec(<<<'SQL'
    CREATE TABLE VaiTro (MaVaiTro INTEGER PRIMARY KEY, TenVaiTro TEXT NOT NULL);
    CREATE TABLE NhanVien (
        MaNV INTEGER PRIMARY KEY AUTOINCREMENT,
        HoTen TEXT NOT NULL,
        MaVaiTro INTEGER,
        DaXoa INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE TaiKhoan (
        MaTK INTEGER PRIMARY KEY AUTOINCREMENT,
        MaNV INTEGER NULL,
        LoaiTaiKhoan TEXT NOT NULL DEFAULT 'LEGACY' CHECK (LoaiTaiKhoan IN ('ADMIN', 'LEGACY')),
        AdminSingleton INTEGER GENERATED ALWAYS AS (
            CASE WHEN LoaiTaiKhoan = 'ADMIN' THEN 1 ELSE NULL END
        ) STORED UNIQUE,
        TenDangNhap TEXT NOT NULL UNIQUE,
        MatKhau TEXT NOT NULL,
        CHECK (LoaiTaiKhoan <> 'ADMIN' OR MaNV IS NULL),
        FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    CREATE TABLE FaceEmbedding (
        MaEmbedding INTEGER PRIMARY KEY,
        MaNV INTEGER NOT NULL,
        SoChieu INTEGER NOT NULL,
        VectorData BLOB NOT NULL,
        FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    INSERT INTO VaiTro VALUES (1, 'Quản trị viên'), (2, 'Nhân viên');
    INSERT INTO NhanVien (MaNV, HoTen, MaVaiTro) VALUES
        (1, 'Legacy Admin profile', 1), (2, 'Employee A', 2);
    INSERT INTO TaiKhoan (MaNV, LoaiTaiKhoan, TenDangNhap, MatKhau) VALUES
        (NULL, 'ADMIN', 'admin', 'preserved-admin-hash'),
        (2, 'LEGACY', 'old.employee', 'legacy-hash');
    INSERT INTO FaceEmbedding (MaEmbedding, MaNV, SoChieu, VectorData) VALUES
        (1, 1, 512, zeroblob(2048)),
        (2, 2, 512, zeroblob(2048));
    SQL);

$employees = new EmployeeModel($pdo);
$attendance = new AttendanceModel($pdo);
$gallery = new FaceEmbeddingModel($pdo);
$employeeIds = array_map('intval', array_column($employees->findAll(), 'MaNV'));
$assert($employeeIds === [2], 'employee list excludes Admin profile');
$assert($employees->findById(1) === null, 'Admin profile cannot be edited as an employee');
$assert(!$attendance->employeeExists(1) && $attendance->employeeExists(2), 'attendance accepts only employee-role profiles');
$assert(array_column($gallery->findAllForInternalGallery(), 'ma_nv') === [2], 'AI1 gallery excludes the legacy Admin face sample');

$accountCountBefore = (int)$pdo->query('SELECT COUNT(*) FROM TaiKhoan')->fetchColumn();
$createdId = $employees->createEmployee('Employee B');
$assert($createdId > 2, 'employee profile is created');
$assert((int)$pdo->query('SELECT MaVaiTro FROM NhanVien WHERE MaNV = ' . $createdId)->fetchColumn() === 2, 'employee role is assigned internally');
$assert((int)$pdo->query('SELECT COUNT(*) FROM TaiKhoan')->fetchColumn() === $accountCountBefore, 'employee creation does not create a Web account');

$pdo->exec('DELETE FROM FaceEmbedding WHERE MaNV = 2');
$pdo->exec("DELETE FROM TaiKhoan WHERE MaNV IS NOT NULL");
$pdo->exec('DELETE FROM NhanVien WHERE MaNV <> 1');
$assert((int)$pdo->query('SELECT COUNT(*) FROM NhanVien WHERE MaVaiTro = 2')->fetchColumn() === 0, 'test reset can remove all employee profiles after dependent rows');
$accountAfterEmployeeReset = (new AccountModel($pdo))->authenticate('admin', 'preserved-admin-hash');
$assert($accountAfterEmployeeReset !== null, 'Admin login still works after all employee rows are removed');
$assert((int)$pdo->query("SELECT COUNT(*) FROM TaiKhoan WHERE LoaiTaiKhoan = 'ADMIN' AND MaNV IS NULL")->fetchColumn() === 1, 'Admin account remains detached after employee reset');

$form = file_get_contents(__DIR__ . '/../View/employee_form.php');
$employeeController = file_get_contents(__DIR__ . '/../Controller/EmployeeController.php');
$authController = file_get_contents(__DIR__ . '/../Controller/AuthController.php');
$assert(is_string($form) && !str_contains($form, 'name="MaVaiTro"') && !str_contains($form, 'name="TenDangNhap"') && !str_contains($form, 'name="MatKhau"'), 'employee form has no role or account fields');
$assert(is_string($form) && str_contains($form, 'data-face-start'), 'AI1 face-enrollment controls remain available');
$assert(is_string($employeeController) && !str_contains($employeeController, 'createForEmployee'), 'employee backend has no account-creation call');
$assert(is_string($authController) && str_contains($authController, 'isAdminAccountActive'), 'route authorization verifies the Admin account by account ID');

echo "PASS: {$assertions} Admin/employee separation assertions.\n";
