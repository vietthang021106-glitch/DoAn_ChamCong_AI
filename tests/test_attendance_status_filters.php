<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/AttendanceModel.php';

if (!in_array('sqlite', PDO::getAvailableDrivers(), true)) {
    fwrite(STDERR, "SKIP: PDO SQLite driver is unavailable.\n");
    exit(2);
}

function assertAttendanceFilter(bool $condition, string $message): void
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

$pdo = new PDO('sqlite::memory:', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$pdo->sqliteCreateFunction('OCTET_LENGTH', static fn(mixed $value): int => is_string($value) ? strlen($value) : 0, 1);
$pdo->sqliteCreateFunction('DATE_FORMAT', static function (?string $value, string $format): ?string {
    return $value === null ? null : date('Y-m-d', strtotime($value));
}, 2);
$pdo->exec(<<<'SQL'
    CREATE TABLE NhanVien (MaNV INTEGER PRIMARY KEY, HoTen TEXT NOT NULL);
    CREATE TABLE PhanCaNhanVien (MaNV INTEGER NOT NULL, MaCa INTEGER NOT NULL, NgayLamViec TEXT NOT NULL);
    CREATE TABLE CaLamViec (
        MaCa INTEGER PRIMARY KEY,
        TenCa TEXT NOT NULL,
        GioBatDau TEXT NOT NULL,
        GioKetThuc TEXT NOT NULL
    );
    CREATE TABLE ChamCong (
        MaCC INTEGER PRIMARY KEY,
        MaNV INTEGER NOT NULL,
        MaCa INTEGER,
        GioVao TEXT,
        GioRa TEXT,
        AnhVao BLOB,
        AnhRa BLOB
    );
    INSERT INTO NhanVien VALUES (1, 'Chưa chấm'), (2, 'Đang làm'), (3, 'Về sớm'), (4, 'Hoàn tất');
    INSERT INTO CaLamViec VALUES (1, 'Ca ngày', '08:00:00', '17:00:00');
    INSERT INTO PhanCaNhanVien VALUES (1, 1, '2026-11-19'), (2, 1, '2026-11-19'),
        (3, 1, '2026-11-19'), (4, 1, '2026-11-19');
    INSERT INTO ChamCong VALUES
        (2, 2, 1, '2026-11-19 08:30:00', NULL, NULL, NULL),
        (3, 3, 1, '2026-11-19 07:55:00', '2026-11-19 16:30:00', NULL, NULL),
        (4, 4, 1, '2026-11-19 07:50:00', '2026-11-19 17:05:00', NULL, NULL);
    SQL);

$model = new AttendanceModel($pdo);
$date = '2026-11-19';
$cases = [
    'not_checked' => [1],
    'on_time_in' => [3, 4],
    'working' => [2],
    'late' => [2],
    'on_time_out' => [4],
    'early' => [3],
    'completed' => [3, 4],
];

foreach ($cases as $status => $expectedIds) {
    $rows = $model->findDaily($date, null, null, 20, 0, $status);
    $actualIds = array_map(static fn(array $row): int => (int)$row['MaNV'], $rows);
    assertAttendanceFilter($actualIds === $expectedIds, "Daily {$status} filter returned unexpected employees.");
    assertAttendanceFilter($model->countDaily($date, null, null, $status) === count($expectedIds), "Daily {$status} count does not match rows.");
}

$historyRows = $model->findHistory($date, $date, null, null, 20, 0, 'early');
assertAttendanceFilter(array_map(static fn(array $row): int => (int)$row['MaNV'], $historyRows) === [3], 'History early filter failed.');
assertAttendanceFilter($model->countHistory($date, $date, null, null, 'late') === 1, 'History late count failed.');
assertAttendanceFilter($model->countHistory($date, $date, null, null, 'not_checked') === 0, 'History incorrectly includes employees without a punch record.');

$invalidRejected = false;
try {
    $model->countDaily($date, null, null, 'arbitrary-sql');
} catch (InvalidArgumentException) {
    $invalidRejected = true;
}
assertAttendanceFilter($invalidRejected, 'Unknown status values must be rejected.');

echo "PASS: daily and history status filters, count/pagination parity, and invalid status rejection.\n";
