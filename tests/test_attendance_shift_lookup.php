<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/AttendanceModel.php';

function shiftAssertSame(mixed $expected, mixed $actual, string $message): void
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true)
            . ', got ' . var_export($actual, true));
    }
}

$pdo = new PDO('sqlite::memory:');
$pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
$pdo->exec('CREATE TABLE CaLamViec (MaCa INTEGER PRIMARY KEY, TenCa TEXT, GioBatDau TEXT, GioKetThuc TEXT)');
$pdo->exec('CREATE TABLE PhanCaNhanVien (MaNV INTEGER, MaCa INTEGER, NgayLamViec TEXT)');
$pdo->exec("INSERT INTO CaLamViec VALUES (5, 'Tăng ca', '19:50:07', '23:50:18')");
$pdo->exec("INSERT INTO PhanCaNhanVien VALUES (22, 5, '2026-11-19')");

$scanTime = new DateTimeImmutable('2026-11-19 20:53:32', new DateTimeZone('Asia/Ho_Chi_Minh'));
$workDate = $scanTime->format('Y-m-d');
$shift = (new AttendanceModel($pdo))->findEmployeeShift(22, $workDate);

shiftAssertSame('2026-11-19', $workDate, 'Vietnam business date at scan time');
shiftAssertSame('Tăng ca', $shift['TenCa'] ?? null, 'NV022 shift is found');
shiftAssertSame('19:50:07', $shift['GioBatDau'] ?? null, 'Shift start matches scenario');
shiftAssertSame('23:50:18', $shift['GioKetThuc'] ?? null, 'Shift end matches scenario');
shiftAssertSame(null, (new AttendanceModel($pdo))->findEmployeeShift(7, $workDate), 'Different employee has no assigned shift');

echo "Attendance shift lookup: 5 checks passed using in-memory SQLite; no production database was used.\n";
