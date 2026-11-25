<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Model/AccountModel.php';
require_once __DIR__ . '/../Model/AttendanceModel.php';
require_once __DIR__ . '/../Model/ShiftModel.php';
require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';
require_once __DIR__ . '/../Security/CsrfToken.php';

if (!in_array('sqlite', PDO::getAvailableDrivers(), true)) {
    fwrite(STDERR, "SKIP: PDO SQLite driver is unavailable.\n");
    exit(2);
}

$pdo = new PDO('sqlite::memory:', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$pdo->exec(<<<'SQL'
    CREATE TABLE VaiTro (MaVaiTro INTEGER PRIMARY KEY, TenVaiTro TEXT NOT NULL);
    CREATE TABLE NhanVien (
        MaNV INTEGER PRIMARY KEY,
        HoTen TEXT NOT NULL,
        MaVaiTro INTEGER,
        DaXoa INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE TaiKhoan (
        MaTK INTEGER PRIMARY KEY,
        MaNV INTEGER NOT NULL,
        TenDangNhap TEXT NOT NULL UNIQUE,
        MatKhau TEXT NOT NULL
    );
    CREATE TABLE FaceEmbedding (
        MaEmbedding INTEGER PRIMARY KEY,
        MaNV INTEGER NOT NULL,
        SoChieu INTEGER NOT NULL,
        VectorData BLOB NOT NULL
    );
    CREATE TABLE ChamCong (
        MaCC INTEGER PRIMARY KEY,
        MaNV INTEGER NOT NULL,
        GioVao TEXT,
        GioRa TEXT
    );
    CREATE TABLE CaLamViec (
        MaCa INTEGER PRIMARY KEY,
        TenCa TEXT NOT NULL,
        GioBatDau TEXT NOT NULL,
        GioKetThuc TEXT NOT NULL,
        TrangThai INTEGER NOT NULL
    );
    CREATE TABLE PhanCaNhanVien (
        MaPhanCa INTEGER PRIMARY KEY,
        MaNV INTEGER NOT NULL,
        MaCa INTEGER NOT NULL,
        NgayLamViec TEXT NOT NULL,
        UNIQUE (MaNV, NgayLamViec)
    );
    INSERT INTO VaiTro VALUES (1, 'Quản trị viên'), (2, 'Nhân viên');
    INSERT INTO NhanVien VALUES
        (1, 'Quản trị', 1, 0),
        (2, 'Nhân viên hoạt động', 2, 0),
        (3, 'Nhân viên đã xóa', 2, 1);
    INSERT INTO TaiKhoan VALUES
        (11, 1, 'admin', 'unused'),
        (12, 2, 'active.user', 'HASH_ACTIVE'),
        (13, 3, 'deleted.user', 'HASH_DELETED');
    INSERT INTO FaceEmbedding VALUES
        (21, 2, 512, zeroblob(2048)),
        (22, 3, 512, zeroblob(2048));
    INSERT INTO ChamCong VALUES (31, 2, '2026-11-11 08:00:00', '2026-11-11 17:00:00');
    INSERT INTO CaLamViec VALUES (41, 'Ca hành chính', '08:00', '17:00', 1);
    INSERT INTO PhanCaNhanVien VALUES (51, 2, 41, '2026-11-11');
    SQL);

$activePasswordHash = password_hash('secret-active', PASSWORD_DEFAULT);
$deletedPasswordHash = password_hash('secret-deleted', PASSWORD_DEFAULT);
$pdo->prepare('UPDATE TaiKhoan SET MatKhau = :password WHERE MaNV = :employee_id')->execute([
    'password' => $activePasswordHash,
    'employee_id' => 2,
]);
$pdo->prepare('UPDATE TaiKhoan SET MatKhau = :password WHERE MaNV = :employee_id')->execute([
    'password' => $deletedPasswordHash,
    'employee_id' => 3,
]);

$assertions = 0;
$assert = static function (bool $condition, string $message) use (&$assertions): void {
    $assertions++;
    if (!$condition) {
        throw new RuntimeException('FAIL: ' . $message);
    }
};

$employees = new EmployeeModel($pdo);
$accounts = new AccountModel($pdo);
$attendance = new AttendanceModel($pdo);
$shifts = new ShiftModel($pdo);
$faceEmbeddings = new FaceEmbeddingModel($pdo);

$employeeIds = static fn(array $rows): array => array_map('intval', array_column($rows, 'MaNV'));
$assert($employeeIds($employees->findAll()) === [2], 'active employee list excludes the legacy Admin profile and soft-deleted rows');
$assert($employees->softDelete(1) === null, 'legacy Admin profile cannot be soft-deleted as an employee');
$assert((int)$pdo->query('SELECT DaXoa FROM NhanVien WHERE MaNV = 1')->fetchColumn() === 0, 'Admin profile remains unchanged by employee soft-delete');
$assert($employees->findById(3) === null, 'direct edit lookup excludes a soft-deleted employee');
$assert($accounts->authenticate('active.user', 'secret-active') === null, 'legacy employee account cannot authenticate to the Web');
$assert($accounts->authenticate('deleted.user', 'secret-deleted') === null, 'soft-deleted employee account cannot authenticate');
$assert($accounts->isEmployeeActive(2), 'active session identity is accepted');
$assert(!$accounts->isEmployeeActive(3), 'old session identity is rejected by active-state lookup');
$assert($attendance->employeeExists(2), 'active employee passes attendance gate');
$assert(!$attendance->employeeExists(3), 'soft-deleted employee fails attendance gate');
$assert($employeeIds($shifts->findEmployees()) === [2], 'shift selector includes employees only and excludes soft-deleted rows');
$assert(!$shifts->employeeExists(3), 'shift validation rejects soft-deleted employee');
$assert(array_column($faceEmbeddings->findAllForInternalGallery(), 'ma_nv') === [2], 'AI gallery query excludes deleted employee embeddings');

$assert($employees->softDelete(2) === true, 'soft-delete updates an active employee');
$assert((int)$pdo->query('SELECT DaXoa FROM NhanVien WHERE MaNV = 2')->fetchColumn() === 1, 'soft-delete flag is persisted');
$assert($employeeIds($employees->findAll()) === [], 'deleted employee disappears from active list');
$assert($employees->findById(2) === null, 'deleted employee cannot be reopened for editing');
$assert($accounts->authenticate('active.user', 'secret-active') === null, 'soft-deleted employee login is rejected');
$assert(!$attendance->employeeExists(2), 'soft-deleted employee attendance is rejected after deletion');
$assert(array_column($faceEmbeddings->findAllForInternalGallery(), 'ma_nv') === [], 'deleted employee is removed from refreshed gallery source');
$assert((int)$pdo->query('SELECT COUNT(*) FROM TaiKhoan WHERE MaNV = 2')->fetchColumn() === 1, 'linked login account is preserved');
$assert((int)$pdo->query('SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV = 2')->fetchColumn() === 1, 'stored face embedding is preserved');
$assert((int)$pdo->query('SELECT COUNT(*) FROM ChamCong WHERE MaNV = 2')->fetchColumn() === 1, 'attendance history is preserved');
$assert((int)$pdo->query('SELECT COUNT(*) FROM PhanCaNhanVien WHERE MaNV = 2')->fetchColumn() === 1, 'existing shift history is preserved');
$assert($employees->softDelete(2) === false, 'repeated soft-delete is idempotently reported');
$assert($employees->softDelete(999) === null, 'missing employee is distinguished from already deleted');

$assignmentCount = (int)$pdo->query('SELECT COUNT(*) FROM PhanCaNhanVien')->fetchColumn();
$assignmentRejected = false;
try {
    $shifts->saveAssignment(2, 41, '2026-11-12');
} catch (InvalidArgumentException) {
    $assignmentRejected = true;
}
$assert($assignmentRejected, 'new shift assignment for deleted employee is blocked');
$assert((int)$pdo->query('SELECT COUNT(*) FROM PhanCaNhanVien')->fetchColumn() === $assignmentCount, 'blocked assignment writes no row');

$_SESSION = [];
$token = CsrfToken::token();
$_POST['_csrf_token'] = 'invalid';
$assert(!CsrfToken::isValid(), 'invalid CSRF token is rejected');
$_POST['_csrf_token'] = $token;
$assert(CsrfToken::isValid(), 'matching CSRF token is accepted');

echo "PASS: {$assertions} soft-delete fixture assertions.\n";
