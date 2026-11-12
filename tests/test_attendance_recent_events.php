<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/AttendanceModel.php';

if (!in_array('sqlite', PDO::getAvailableDrivers(), true)) {
    fwrite(STDERR, "SKIP: PDO SQLite driver is unavailable.\n");
    exit(2);
}

$connection = new PDO('sqlite::memory:', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$connection->exec(<<<'SQL'
    CREATE TABLE NhanVien (MaNV INTEGER PRIMARY KEY, HoTen TEXT NOT NULL);
    CREATE TABLE CaLamViec (MaCa INTEGER PRIMARY KEY, TenCa TEXT NOT NULL);
    CREATE TABLE ChamCong (
        MaCC INTEGER PRIMARY KEY,
        MaNV INTEGER NOT NULL,
        MaCa INTEGER,
        GioVao TEXT,
        GioRa TEXT
    );
    INSERT INTO NhanVien VALUES
        (1, 'An'), (2, 'Bình'), (3, 'Chi'), (4, 'Dũng'), (5, 'Hoa');
    INSERT INTO CaLamViec VALUES (10, 'Ca sáng'), (20, 'Ca chiều');
    INSERT INTO ChamCong VALUES
        (1, 1, 10, '2026-11-12 08:00:00', '2026-11-12 17:00:00'),
        (2, 2, 10, '2026-11-12 08:30:00', NULL),
        (3, 3, 20, '2026-11-12 09:00:00', '2026-11-12 18:00:00'),
        (4, 4, 10, '2026-11-12 07:00:00', NULL),
        (5, 5, 10, '2026-11-12 07:30:00', NULL);
    SQL);

$rows = (new AttendanceModel($connection))->findRecentPunches(6);
$actual = array_map(static fn(array $row): array => [
    (int)$row['MaCC'],
    (int)$row['MaNV'],
    (string)$row['HoTen'],
    (int)$row['MaCa'],
    (string)$row['TenCa'],
    (string)$row['EventTime'],
    (string)$row['PunchType'],
], $rows);
$expected = [
    [3, 3, 'Chi', 20, 'Ca chiều', '2026-11-12 18:00:00', 'OUT'],
    [1, 1, 'An', 10, 'Ca sáng', '2026-11-12 17:00:00', 'OUT'],
    [3, 3, 'Chi', 20, 'Ca chiều', '2026-11-12 09:00:00', 'IN'],
    [2, 2, 'Bình', 10, 'Ca sáng', '2026-11-12 08:30:00', 'IN'],
    [1, 1, 'An', 10, 'Ca sáng', '2026-11-12 08:00:00', 'IN'],
    [5, 5, 'Hoa', 10, 'Ca sáng', '2026-11-12 07:30:00', 'IN'],
];

if ($actual !== $expected) {
    fwrite(STDERR, "FAIL: recent events did not return the newest six distinct punch events.\n");
    fwrite(STDERR, json_encode($actual, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) . "\n");
    exit(1);
}

$employeeOneEvents = array_values(array_filter($rows, static fn(array $row): bool => (int)$row['MaNV'] === 1));
$employeeOneTypes = array_column($employeeOneEvents, 'PunchType');
sort($employeeOneTypes);
if (count($employeeOneEvents) !== 2 || $employeeOneTypes !== ['IN', 'OUT']) {
    fwrite(STDERR, "FAIL: the same attendance record must produce both check-in and check-out events.\n");
    exit(1);
}

echo "PASS: six latest punch events, check-in/out split, employee and shift details.\n";
