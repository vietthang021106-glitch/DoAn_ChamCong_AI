<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/Database.php';
require_once __DIR__ . '/../Model/AccountModel.php';
require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Model/AttendanceModel.php';
require_once __DIR__ . '/../Model/ShiftModel.php';
require_once __DIR__ . '/../Model/HealthModel.php';
require_once __DIR__ . '/../Model/AlertModel.php';
require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';

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
    CREATE TABLE NhanVien (MaNV INTEGER PRIMARY KEY, HoTen TEXT NOT NULL, MaVaiTro INTEGER);
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
    INSERT INTO VaiTro VALUES (1, 'Quản trị viên'), (2, 'Nhân viên');
    INSERT INTO NhanVien VALUES (1, 'Admin legacy profile', 1), (2, 'Employee test', 2);
    SQL);
$passwordHash = password_hash('fixture-secret', PASSWORD_DEFAULT);
$pdo->prepare('INSERT INTO TaiKhoan VALUES (1, 1, :username, :password)')->execute([
    'username' => 'fixture.admin',
    'password' => $passwordHash,
]);

$assertions = 0;
$assert = static function (bool $condition, string $message) use (&$assertions): void {
    $assertions++;
    if (!$condition) {
        throw new RuntimeException('FAIL: ' . $message);
    }
};

$assert(!Database::supportsEmployeeSoftDelete($pdo), 'legacy schema is detected without DaXoa');
$assert(str_contains(Database::activeEmployeePredicate('nv', $pdo), "nv.MaVaiTro = (SELECT MaVaiTro FROM VaiTro WHERE TenVaiTro = 'Nhân viên'"), 'legacy schema still limits employee queries to the employee role');
$accounts = new AccountModel($pdo);
$assert($accounts->authenticate('fixture.admin', 'fixture-secret') !== null, 'legacy Admin login works before migration');
$assert($accounts->isAdminAccountActive(1), 'Admin session verification uses the legacy account link before migration');
$assert(!$accounts->isEmployeeActive(1), 'legacy Admin profile is not accepted as an employee');
$assert($accounts->isEmployeeActive(2), 'real employee remains active without DaXoa');
$employees = new EmployeeModel($pdo);
$assert(array_map('intval', array_column($employees->findAll(), 'MaNV')) === [2], 'employee list excludes the legacy Admin profile');
$assert($employees->findById(1) === null, 'legacy Admin profile cannot be edited as an employee');
$assert($employees->findById(2) !== null, 'real employee lookup works without DaXoa');
$attendance = new AttendanceModel($pdo);
$assert(!$attendance->employeeExists(1), 'attendance guard rejects the legacy Admin profile');
$assert($attendance->employeeExists(2), 'attendance guard accepts a real employee');
$assert(array_map('intval', array_column($attendance->findEmployees(), 'MaNV')) === [2], 'attendance selector contains employees only');
$shifts = new ShiftModel($pdo);
$assert(!$shifts->employeeExists(1), 'shift guard rejects the legacy Admin profile');
$assert($shifts->employeeExists(2), 'shift guard accepts a real employee');
$assert(array_map('intval', array_column($shifts->findEmployees(), 'MaNV')) === [2], 'shift selector contains employees only');
$assert((new FaceEmbeddingModel($pdo))->findAllForInternalGallery() === [], 'AI gallery query works without DaXoa');
$healthSource = file_get_contents(__DIR__ . '/../Model/HealthModel.php');
$alertSource = file_get_contents(__DIR__ . '/../Model/AlertModel.php');
$dashboardSource = file_get_contents(__DIR__ . '/../Model/DashboardModel.php');
$assert(is_string($healthSource) && str_contains($healthSource, 'Database::activeEmployeePredicate'), 'health selector uses schema-aware filter');
$assert(is_string($alertSource) && str_contains($alertSource, 'Database::activeEmployeePredicate'), 'alert selector uses schema-aware filter');
$assert(is_string($dashboardSource) && str_contains($dashboardSource, 'Database::activeEmployeePredicate'), 'dashboard counts use schema-aware filters');

echo "PASS: {$assertions} legacy-schema compatibility assertions.\n";
