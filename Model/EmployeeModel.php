<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class EmployeeModel
{
    public function findAll(): array
    {
        $sql = <<<'SQL'
            SELECT
                nv.MaNV,
                nv.HoTen,
                vt.TenVaiTro,
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM FaceEmbedding fe
                    WHERE fe.MaNV = nv.MaNV
                ) THEN 1 ELSE 0 END AS FaceRegistered
            FROM NhanVien nv
            LEFT JOIN VaiTro vt ON vt.MaVaiTro = nv.MaVaiTro
            ORDER BY nv.MaNV
            SQL;

        return Database::getConnection()->query($sql)->fetchAll();
    }

    public function findById(int $employeeId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT MaNV, HoTen, MaVaiTro
            FROM NhanVien
            WHERE MaNV = :employee_id
            SQL);
        $statement->execute(['employee_id' => $employeeId]);
        $employee = $statement->fetch();

        return $employee === false ? null : $employee;
    }

    public function findRoles(): array
    {
        return Database::getConnection()
            ->query('SELECT MaVaiTro, TenVaiTro FROM VaiTro ORDER BY MaVaiTro')
            ->fetchAll();
    }

    public function roleExists(int $roleId): bool
    {
        $statement = Database::getConnection()->prepare(
            'SELECT 1 FROM VaiTro WHERE MaVaiTro = :role_id LIMIT 1'
        );
        $statement->execute(['role_id' => $roleId]);

        return $statement->fetchColumn() !== false;
    }

    public function create(string $name, int $roleId): int
    {
        $statement = Database::getConnection()->prepare(
            'INSERT INTO NhanVien (HoTen, MaVaiTro) VALUES (:name, :role_id)'
        );
        $statement->execute([
            'name' => $name,
            'role_id' => $roleId,
        ]);

        return (int)Database::getConnection()->lastInsertId();
    }

    public function update(int $employeeId, string $name, int $roleId): void
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            UPDATE NhanVien
            SET HoTen = :name, MaVaiTro = :role_id
            WHERE MaNV = :employee_id
            SQL);
        $statement->execute([
            'name' => $name,
            'role_id' => $roleId,
            'employee_id' => $employeeId,
        ]);
    }
}
