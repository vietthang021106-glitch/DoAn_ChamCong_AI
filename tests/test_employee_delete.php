<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Security/CsrfToken.php';

if (!in_array('sqlite', PDO::getAvailableDrivers(), true)) {
    fwrite(STDERR, "SKIP: PDO SQLite driver is unavailable.\n");
    exit(2);
}

$pdo = new PDO('sqlite::memory:', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$pdo->exec('PRAGMA foreign_keys = ON');
$pdo->exec(<<<'SQL'
    CREATE TABLE VaiTro (MaVaiTro INTEGER PRIMARY KEY, TenVaiTro TEXT NOT NULL);
    INSERT INTO VaiTro VALUES (1, 'Quản trị viên'), (2, 'Nhân viên');
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
        FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    CREATE TABLE FaceEmbedding (
        MaEmbedding INTEGER PRIMARY KEY,
        MaNV INTEGER NOT NULL,
        VectorData BLOB NOT NULL,
        FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    );
    CREATE TABLE ChamCong (MaCC INTEGER PRIMARY KEY, MaNV INTEGER, FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV));
    CREATE TABLE PhanCaNhanVien (MaPhanCa INTEGER PRIMARY KEY, MaNV INTEGER, FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV));
    CREATE TABLE LichSuSucKhoe (MaSK INTEGER PRIMARY KEY, MaNV INTEGER, FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV));
    CREATE TABLE LichSuTrangThai (MaTT INTEGER PRIMARY KEY, MaNV INTEGER, FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV));
    CREATE TABLE LichSuQuet (MaQuet INTEGER PRIMARY KEY, MaNV INTEGER, FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV));
    CREATE TABLE CanhBao (MaCB INTEGER PRIMARY KEY, MaNV INTEGER, FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV));
    CREATE TABLE FutureEmployeeAudit (
        AuditId INTEGER PRIMARY KEY,
        EmployeeRef INTEGER NOT NULL,
        FOREIGN KEY (EmployeeRef) REFERENCES NhanVien(MaNV)
    );
    CREATE TABLE AccountAudit (
        AuditId INTEGER PRIMARY KEY,
        AccountRef INTEGER NOT NULL,
        FOREIGN KEY (AccountRef) REFERENCES TaiKhoan(MaTK)
    );
    INSERT INTO NhanVien (MaNV, HoTen, MaVaiTro) VALUES
        (1, 'Admin', 1), (2, 'Clean', 2), (3, 'Attendance', 2),
        (4, 'Shift', 2), (5, 'Face', 2), (6, 'Health', 2),
        (7, 'State', 2), (8, 'Scan', 2), (9, 'Alert', 2),
        (10, 'Future FK', 2), (11, 'Account FK', 2), (12, 'Rollback', 2);
    INSERT INTO TaiKhoan (MaTK, MaNV, TenDangNhap) VALUES
        (101, 1, 'admin'), (102, 2, 'clean'), (103, 3, 'attendance'),
        (104, 4, 'shift'), (105, 5, 'face'), (106, 6, 'health'),
        (107, 7, 'state'), (108, 8, 'scan'), (109, 9, 'alert'),
        (110, 10, 'future'), (111, 11, 'account_ref'), (112, 12, 'rollback');
    INSERT INTO ChamCong VALUES (201, 3);
    INSERT INTO PhanCaNhanVien VALUES (202, 4);
    INSERT INTO FaceEmbedding VALUES (203, 5, zeroblob(2048));
    INSERT INTO LichSuSucKhoe VALUES (204, 6);
    INSERT INTO LichSuTrangThai VALUES (205, 7);
    INSERT INTO LichSuQuet VALUES (206, 8);
    INSERT INTO CanhBao VALUES (207, 9);
    INSERT INTO FutureEmployeeAudit VALUES (208, 10);
    INSERT INTO AccountAudit VALUES (209, 111);
    CREATE TRIGGER fail_employee_delete
    BEFORE DELETE ON NhanVien
    WHEN OLD.MaNV = 12
    BEGIN
        SELECT RAISE(ABORT, 'fixture forced delete failure');
    END;
    SQL);

$employees = new EmployeeModel($pdo);
$assertions = 0;
$assert = static function (bool $condition, string $message) use (&$assertions): void {
    $assertions++;
    if (!$condition) {
        throw new RuntimeException('FAIL: ' . $message);
    }
};
$count = static function (string $sql, array $parameters = []) use ($pdo): int {
    $statement = $pdo->prepare($sql);
    $statement->execute($parameters);
    return (int)$statement->fetchColumn();
};

// Eligible employee: account and employee are both removed atomically.
$assert($employees->deleteIfUnreferenced(2) === EmployeeModel::DELETE_DELETED, 'unreferenced employee is deleted');
$assert($count('SELECT COUNT(*) FROM NhanVien WHERE MaNV = 2') === 0, 'employee row is removed');
$assert($count('SELECT COUNT(*) FROM TaiKhoan WHERE MaNV = 2') === 0, 'linked login is removed');

// Each current history family is a blocker and remains untouched.
foreach ([
    3 => 'ChamCong',
    4 => 'PhanCaNhanVien',
    6 => 'LichSuSucKhoe',
    7 => 'LichSuTrangThai',
    8 => 'LichSuQuet',
    9 => 'CanhBao',
] as $employeeId => $historyTable) {
    $assert($employees->deleteIfUnreferenced($employeeId) === EmployeeModel::DELETE_HAS_RELATED_DATA, $historyTable . ' blocks deletion');
    $assert($count('SELECT COUNT(*) FROM NhanVien WHERE MaNV = :id', ['id' => $employeeId]) === 1, $historyTable . ' employee remains');
    $assert($count('SELECT COUNT(*) FROM TaiKhoan WHERE MaNV = :id', ['id' => $employeeId]) === 1, $historyTable . ' account remains');
}

$assert($employees->deleteIfUnreferenced(5) === EmployeeModel::DELETE_FACE_REGISTERED, 'FaceEmbedding blocks deletion with a specific result');
$assert($count('SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV = 5') === 1, 'face embedding remains untouched');
$assert($employees->deleteIfUnreferenced(10) === EmployeeModel::DELETE_HAS_RELATED_DATA, 'new foreign key column blocks deletion');
$assert($employees->deleteIfUnreferenced(11) === EmployeeModel::DELETE_HAS_RELATED_DATA, 'account dependent record blocks account deletion');
$assert($count('SELECT COUNT(*) FROM AccountAudit WHERE AccountRef = 111') === 1, 'account dependent record remains untouched');
$assert($employees->deleteIfUnreferenced(999) === EmployeeModel::DELETE_NOT_FOUND, 'unknown employee has a distinct result');
$invalidIdRejected = false;
try {
    $employees->deleteIfUnreferenced(0);
} catch (InvalidArgumentException) {
    $invalidIdRejected = true;
}
$assert($invalidIdRejected, 'non-positive employee ID is rejected');

// A failure after deleting the linked account must roll both statements back.
$rollbackFailed = false;
try {
    $employees->deleteIfUnreferenced(12);
} catch (PDOException) {
    $rollbackFailed = true;
}
$assert($rollbackFailed, 'injected employee delete failure is surfaced');
$assert($count('SELECT COUNT(*) FROM NhanVien WHERE MaNV = 12') === 1, 'employee row is restored by rollback');
$assert($count('SELECT COUNT(*) FROM TaiKhoan WHERE MaNV = 12') === 1, 'account deletion is rolled back');

// Guard wiring is checked without a production DB; CSRF primitive is exercised directly.
$controllerSource = file_get_contents(__DIR__ . '/../Controller/EmployeeController.php');
$routeSource = file_get_contents(__DIR__ . '/../index.php');
$authSource = file_get_contents(__DIR__ . '/../Controller/AuthController.php');
$assert(is_string($controllerSource) && str_contains($controllerSource, 'AuthController::requireAdmin();'), 'delete controller requires Admin');
$assert(is_string($controllerSource) && str_contains($controllerSource, 'CsrfToken::isValid()'), 'delete controller checks CSRF');
$assert(is_string($controllerSource) && !str_contains($controllerSource, "\$_SESSION['ma_nv']"), 'Admin deletion flow does not depend on an employee session ID');
$assert(is_string($authSource) && str_contains($authSource, 'isAdminAccountActive'), 'Admin guard validates the independent Admin account');
$assert(is_string($routeSource) && str_contains($routeSource, "\$action === 'delete_employee' && \$method === 'POST'"), 'delete route dispatch is POST-only');
$assert(is_string($routeSource)
    && str_contains($routeSource, "'store', 'update', 'delete_employee', 'logout'")
    && str_contains($routeSource, "=> 'POST'"), 'other delete methods are rejected');

$_SESSION = [];
$token = CsrfToken::token();
$_POST['_csrf_token'] = 'invalid';
$assert(!CsrfToken::isValid(), 'invalid CSRF token is rejected');
$_POST['_csrf_token'] = $token;
$assert(CsrfToken::isValid(), 'valid CSRF token is accepted');

echo "PASS: {$assertions} employee delete fixture assertions.\n";
