<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class ShiftModel
{
    public function findAll(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaCa, TenCa, GioBatDau, GioKetThuc
            FROM CaLamViec
            ORDER BY GioBatDau, MaCa
            SQL)->fetchAll();
    }

    public function findEmployees(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaNV, HoTen
            FROM NhanVien
            ORDER BY MaNV
            SQL)->fetchAll();
    }

    public function findAssignmentsByDate(string $date): array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT
                PCN.MaPhanCa,
                PCN.MaNV,
                NV.HoTen,
                PCN.MaCa,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc,
                PCN.NgayLamViec
            FROM PhanCaNhanVien PCN
            INNER JOIN NhanVien NV ON NV.MaNV = PCN.MaNV
            INNER JOIN CaLamViec CLV ON CLV.MaCa = PCN.MaCa
            WHERE PCN.NgayLamViec = :work_date
            ORDER BY NV.MaNV
            SQL);
        $statement->execute(['work_date' => $date]);

        return $statement->fetchAll();
    }

    public function employeeExists(int $employeeId): bool
    {
        return $this->exists('NhanVien', 'MaNV', $employeeId);
    }

    public function shiftExists(int $shiftId): bool
    {
        return $this->exists('CaLamViec', 'MaCa', $shiftId);
    }

    public function saveAssignment(int $employeeId, int $shiftId, string $date): void
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            INSERT INTO PhanCaNhanVien (MaNV, MaCa, NgayLamViec)
            VALUES (:employee_id, :shift_id, :work_date)
            ON DUPLICATE KEY UPDATE MaCa = VALUES(MaCa)
            SQL);
        $statement->execute([
            'employee_id' => $employeeId,
            'shift_id' => $shiftId,
            'work_date' => $date,
        ]);
    }

    private function exists(string $table, string $column, int $id): bool
    {
        $statement = Database::getConnection()->prepare(
            "SELECT 1 FROM {$table} WHERE {$column} = :id LIMIT 1"
        );
        $statement->execute(['id' => $id]);

        return $statement->fetchColumn() !== false;
    }
}
