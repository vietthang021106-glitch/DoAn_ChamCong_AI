<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class EmployeeModel
{
    public const DELETE_DELETED = 'deleted';
    public const DELETE_NOT_FOUND = 'not_found';
    public const DELETE_FACE_REGISTERED = 'face_registered';
    public const DELETE_HAS_RELATED_DATA = 'has_related_data';

    private ?PDO $connection;

    public function __construct(?PDO $connection = null)
    {
        $this->connection = $connection;
    }

    /** Lấy nhân viên thực tế; tài khoản Admin độc lập không xuất hiện trong danh sách này. */
    public function findAll(): array
    {
        $pdo = $this->connection();
        $activeEmployee = Database::activeEmployeePredicate('nv', $pdo);
        $sql = <<<SQL
            SELECT
                nv.MaNV,
                nv.HoTen,
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM FaceEmbedding fe
                    WHERE fe.MaNV = nv.MaNV
                ) THEN 1 ELSE 0 END AS FaceRegistered,
                (
                    SELECT COUNT(*)
                    FROM FaceEmbedding fe
                    WHERE fe.MaNV = nv.MaNV
                ) AS FaceEmbeddingCount
            FROM NhanVien nv
            WHERE {$activeEmployee}
            ORDER BY nv.MaNV
            SQL;

        return $pdo->query($sql)->fetchAll();
    }

    /** Tìm một hồ sơ nhân viên thực tế; tài khoản Web không thuộc hồ sơ này. */
    public function findById(int $employeeId): ?array
    {
        $pdo = $this->connection();
        $activeEmployee = Database::activeEmployeePredicate('nv', $pdo);
        $statement = $pdo->prepare(<<<SQL
            SELECT
                nv.MaNV,
                nv.HoTen
            FROM NhanVien nv
            WHERE nv.MaNV = :employee_id AND {$activeEmployee}
            SQL);
        $statement->execute(['employee_id' => $employeeId]);
        $employee = $statement->fetch();

        return $employee === false ? null : $employee;
    }

    /**
     * Soft-delete one employee without touching linked accounts or historical data.
     * Returns true when deleted, false when already deleted, and null when missing.
     */
    public function softDelete(int $employeeId): ?bool
    {
        $pdo = $this->connection();
        if (!Database::supportsEmployeeSoftDelete($pdo)) {
            throw new LogicException('Employee soft-delete is unavailable because the schema has no DaXoa column.');
        }
        $ownsTransaction = !$pdo->inTransaction();
        if ($ownsTransaction) {
            $pdo->beginTransaction();
        }

        try {
            $lockSuffix = $pdo->getAttribute(PDO::ATTR_DRIVER_NAME) === 'mysql' ? ' FOR UPDATE' : '';
            $employeeRole = Database::employeeRolePredicate('', $pdo);
            $current = $pdo->prepare(
                'SELECT DaXoa FROM NhanVien WHERE MaNV = :employee_id AND ' . $employeeRole . $lockSuffix
            );
            $current->execute(['employee_id' => $employeeId]);
            $deleted = $current->fetchColumn();
            if ($deleted === false) {
                if ($ownsTransaction) {
                    $pdo->rollBack();
                }
                return null;
            }
            if ((int)$deleted === 1) {
                if ($ownsTransaction) {
                    $pdo->commit();
                }
                return false;
            }

            $update = $pdo->prepare(<<<SQL
                UPDATE NhanVien
                SET DaXoa = 1
                WHERE MaNV = :employee_id AND DaXoa = 0 AND {$employeeRole}
                SQL);
            $update->execute(['employee_id' => $employeeId]);
            if ($update->rowCount() !== 1) {
                throw new RuntimeException('Employee soft-delete did not update exactly one row.');
            }

            if ($ownsTransaction) {
                $pdo->commit();
            }
            return true;
        } catch (Throwable $exception) {
            if ($ownsTransaction && $pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    /**
     * Permanently delete an active employee only when no face sample or related
     * record references the employee. Database metadata is inspected at runtime
     * so newly added foreign keys are treated as blockers as well.
     */
    public function deleteIfUnreferenced(int $employeeId): string
    {
        if ($employeeId < 1) {
            throw new InvalidArgumentException('Employee ID must be positive.');
        }

        $pdo = $this->connection();
        $ownsTransaction = !$pdo->inTransaction();
        $savepoint = 'employee_delete_guard';
        if ($ownsTransaction) {
            $pdo->beginTransaction();
        } else {
            $pdo->exec('SAVEPOINT ' . $savepoint);
        }

        $driver = (string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        $lockSuffix = $driver === 'mysql' ? ' FOR UPDATE' : '';
        $activeEmployee = Database::activeEmployeePredicate('', $pdo);

        try {
            $employee = $pdo->prepare(
                'SELECT MaNV FROM NhanVien WHERE MaNV = :employee_id AND ' . $activeEmployee . $lockSuffix
            );
            $employee->execute(['employee_id' => $employeeId]);
            if ($employee->fetchColumn() === false) {
                $this->finishDeleteTransaction($pdo, $ownsTransaction, $savepoint);
                return self::DELETE_NOT_FOUND;
            }

            if ($this->hasReferenceRows($pdo, 'FaceEmbedding', 'MaNV', $employeeId, $lockSuffix)) {
                $this->finishDeleteTransaction($pdo, $ownsTransaction, $savepoint);
                return self::DELETE_FACE_REGISTERED;
            }

            foreach ($this->referenceColumns($pdo, 'NhanVien', 'MaNV', true) as [$table, $column]) {
                if (strcasecmp($table, 'TaiKhoan') === 0 || strcasecmp($table, 'FaceEmbedding') === 0) {
                    continue;
                }
                if ($this->hasReferenceRows($pdo, $table, $column, $employeeId, $lockSuffix)) {
                    $this->finishDeleteTransaction($pdo, $ownsTransaction, $savepoint);
                    return self::DELETE_HAS_RELATED_DATA;
                }
            }

            $accounts = $pdo->prepare(
                'SELECT MaTK FROM TaiKhoan WHERE MaNV = :employee_id' . $lockSuffix
            );
            $accounts->execute(['employee_id' => $employeeId]);
            $accountIds = $accounts->fetchAll(PDO::FETCH_COLUMN);
            $accountReferences = $this->referenceColumns($pdo, 'TaiKhoan', 'MaTK');
            foreach ($accountIds as $accountId) {
                foreach ($accountReferences as [$table, $column]) {
                    if ($this->hasReferenceRows($pdo, $table, $column, (int)$accountId, $lockSuffix)) {
                        $this->finishDeleteTransaction($pdo, $ownsTransaction, $savepoint);
                        return self::DELETE_HAS_RELATED_DATA;
                    }
                }
            }

            $deleteAccounts = $pdo->prepare('DELETE FROM TaiKhoan WHERE MaNV = :employee_id');
            $deleteAccounts->execute(['employee_id' => $employeeId]);

            $deleteEmployee = $pdo->prepare(
                'DELETE FROM NhanVien WHERE MaNV = :employee_id AND ' . $activeEmployee
            );
            $deleteEmployee->execute(['employee_id' => $employeeId]);
            if ($deleteEmployee->rowCount() !== 1) {
                throw new RuntimeException('Employee delete did not remove exactly one row.');
            }

            $this->finishDeleteTransaction($pdo, $ownsTransaction, $savepoint);
            return self::DELETE_DELETED;
        } catch (Throwable $exception) {
            $this->rollbackDeleteTransaction($pdo, $ownsTransaction, $savepoint);
            throw $exception;
        }
    }

    /** @return list<array{0: string, 1: string}> */
    private function referenceColumns(PDO $pdo, string $targetTable, string $targetColumn, bool $includeLooseMaNv = false): array
    {
        $driver = (string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        $references = [];

        if ($driver === 'mysql') {
            $foreignKeys = $pdo->prepare(<<<'SQL'
                SELECT TABLE_NAME, COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                  AND REFERENCED_TABLE_SCHEMA = DATABASE()
                  AND REFERENCED_TABLE_NAME = :target_table
                  AND REFERENCED_COLUMN_NAME = :target_column
                SQL);
            $foreignKeys->execute([
                'target_table' => $targetTable,
                'target_column' => $targetColumn,
            ]);
            foreach ($foreignKeys->fetchAll(PDO::FETCH_ASSOC) as $row) {
                $references[] = [(string)$row['TABLE_NAME'], (string)$row['COLUMN_NAME']];
            }

            if ($includeLooseMaNv && strcasecmp($targetTable, 'NhanVien') === 0 && strcasecmp($targetColumn, 'MaNV') === 0) {
                $columns = $pdo->query(<<<'SQL'
                    SELECT c.TABLE_NAME, c.COLUMN_NAME
                    FROM information_schema.COLUMNS c
                    INNER JOIN information_schema.TABLES t
                        ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
                    WHERE c.TABLE_SCHEMA = DATABASE()
                      AND t.TABLE_TYPE = 'BASE TABLE'
                      AND c.COLUMN_NAME = 'MaNV'
                      AND c.TABLE_NAME <> 'NhanVien'
                    SQL);
                foreach ($columns->fetchAll(PDO::FETCH_ASSOC) as $row) {
                    $references[] = [(string)$row['TABLE_NAME'], (string)$row['COLUMN_NAME']];
                }
            }
        } elseif ($driver === 'sqlite') {
            $tables = $pdo->query("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
                ->fetchAll(PDO::FETCH_COLUMN);
            foreach ($tables as $tableName) {
                $table = (string)$tableName;
                if (strcasecmp($table, $targetTable) === 0) {
                    continue;
                }

                $quotedTable = $this->quoteIdentifier($table);
                $columns = $pdo->query('PRAGMA table_info(' . $quotedTable . ')')->fetchAll(PDO::FETCH_ASSOC);
                foreach ($columns as $columnInfo) {
                    $columnName = (string)$columnInfo['name'];
                    if ($includeLooseMaNv && strcasecmp($targetTable, 'NhanVien') === 0
                        && strcasecmp($targetColumn, 'MaNV') === 0 && strcasecmp($columnName, 'MaNV') === 0) {
                        $references[] = [$table, $columnName];
                    }
                }

                $foreignKeys = $pdo->query('PRAGMA foreign_key_list(' . $quotedTable . ')')->fetchAll(PDO::FETCH_ASSOC);
                foreach ($foreignKeys as $foreignKey) {
                    if (strcasecmp((string)$foreignKey['table'], $targetTable) !== 0) {
                        continue;
                    }
                    $referencedColumn = (string)($foreignKey['to'] ?? '');
                    if ($referencedColumn !== '' && strcasecmp($referencedColumn, $targetColumn) !== 0) {
                        continue;
                    }
                    $references[] = [$table, (string)$foreignKey['from']];
                }
            }
        } else {
            throw new RuntimeException('Unsupported database driver for safe employee deletion.');
        }

        $unique = [];
        foreach ($references as [$table, $column]) {
            $key = strtolower($table . "\0" . $column);
            $unique[$key] = [$table, $column];
        }
        return array_values($unique);
    }

    private function hasReferenceRows(PDO $pdo, string $table, string $column, int $value, string $lockSuffix): bool
    {
        $sql = 'SELECT 1 FROM ' . $this->quoteIdentifier($table)
            . ' WHERE ' . $this->quoteIdentifier($column) . ' = :reference_value LIMIT 1' . $lockSuffix;
        $statement = $pdo->prepare($sql);
        $statement->execute(['reference_value' => $value]);
        return $statement->fetchColumn() !== false;
    }

    private function quoteIdentifier(string $identifier): string
    {
        if (!preg_match('/\A[A-Za-z0-9_$]+\z/', $identifier)) {
            throw new RuntimeException('Unsafe database identifier found in schema metadata.');
        }
        return '`' . $identifier . '`';
    }

    private function finishDeleteTransaction(PDO $pdo, bool $ownsTransaction, string $savepoint): void
    {
        if ($ownsTransaction) {
            $pdo->commit();
        } else {
            $pdo->exec('RELEASE SAVEPOINT ' . $savepoint);
        }
    }

    private function rollbackDeleteTransaction(PDO $pdo, bool $ownsTransaction, string $savepoint): void
    {
        if ($ownsTransaction) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            return;
        }
        try {
            $pdo->exec('ROLLBACK TO SAVEPOINT ' . $savepoint);
            $pdo->exec('RELEASE SAVEPOINT ' . $savepoint);
        } catch (Throwable) {
            // Preserve the original database error if savepoint cleanup also fails.
        }
    }

    /** Tạo hồ sơ nhân viên với vai trò nội bộ "Nhân viên"; không tạo tài khoản Web. */
    public function createEmployee(string $name): int
    {
        $pdo = $this->connection();
        $roleId = $this->employeeRoleId($pdo);
        $pdo->beginTransaction();
        try {
            $statement = $pdo->prepare(
                'INSERT INTO NhanVien (HoTen, MaVaiTro) VALUES (:name, :role_id)'
            );
            $statement->execute(['name' => $name, 'role_id' => $roleId]);
            $employeeId = (int)$pdo->lastInsertId();
            $pdo->commit();

            return $employeeId;
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    /** Cập nhật hồ sơ nhân viên, gán vai trò nội bộ nhân viên và không đụng TaiKhoan. */
    public function updateEmployee(int $employeeId, string $name): void
    {
        $pdo = $this->connection();
        $pdo->beginTransaction();
        try {
            $roleId = $this->employeeRoleId($pdo);
            $activeEmployee = Database::activeEmployeePredicate('', $pdo);
            $lockSuffix = $pdo->getAttribute(PDO::ATTR_DRIVER_NAME) === 'mysql' ? ' FOR UPDATE' : '';
            $lock = $pdo->prepare(
                'SELECT MaNV FROM NhanVien WHERE MaNV = :employee_id AND ' . $activeEmployee . $lockSuffix
            );
            $lock->execute(['employee_id' => $employeeId]);
            if ($lock->fetchColumn() === false) {
                throw new DomainException('Employee is unavailable.');
            }

            $statement = $pdo->prepare(<<<'SQL'
                UPDATE NhanVien
                SET HoTen = :name, MaVaiTro = :role_id
                WHERE MaNV = :employee_id
                SQL);
            $statement->execute([
                'name' => $name,
                'role_id' => $roleId,
                'employee_id' => $employeeId,
            ]);

            $pdo->commit();
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    private function connection(): PDO
    {
        return $this->connection ?? Database::getConnection();
    }

    private function employeeRoleId(PDO $pdo): int
    {
        $statement = $pdo->prepare('SELECT MaVaiTro FROM VaiTro WHERE TenVaiTro = :role_name ORDER BY MaVaiTro');
        $statement->execute(['role_name' => 'Nhân viên']);
        $roleIds = array_map('intval', $statement->fetchAll(PDO::FETCH_COLUMN));
        if (count($roleIds) !== 1 || $roleIds[0] < 1) {
            throw new RuntimeException('VaiTro must contain exactly one Nhân viên role before employee operations.');
        }

        return $roleIds[0];
    }
}
