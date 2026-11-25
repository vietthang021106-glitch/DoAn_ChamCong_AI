<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class DeviceModel
{
    /** @return array<int, array{MaTB: int|string, LoaiTB: ?string, TrangThai: ?string}> */
    public function findAll(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaTB, LoaiTB, TrangThai
            FROM ThietBi
            ORDER BY MaTB
            SQL)->fetchAll();
    }

    /** Find one configured attendance device by its primary key. */
    public function findById(int $deviceId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT MaTB, LoaiTB, TrangThai
            FROM ThietBi
            WHERE MaTB = :device_id
            LIMIT 1
            SQL);
        $statement->execute(['device_id' => $deviceId]);
        $row = $statement->fetch();

        return is_array($row) ? $row : null;
    }
}
