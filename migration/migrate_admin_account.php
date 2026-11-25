<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/Database.php';

/**
 * Separate the single Admin login from NhanVien.
 *
 * Default invocation is read-only. Pass --apply only after reviewing the dry-run.
 * This migration never deletes employees, accounts, face samples, shifts, or history.
 */
if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

$apply = in_array('--apply', $argv, true);
$unknown = array_values(array_diff(array_slice($argv, 1), ['--apply', '--dry-run']));
if ($unknown !== []) {
    fwrite(STDERR, "Usage: php migration/migrate_admin_account.php [--dry-run|--apply]\n");
    exit(2);
}

try {
    $pdo = Database::getConnection();
    if ((string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME) !== 'mysql') {
        throw new RuntimeException('This migration supports MariaDB/MySQL only.');
    }

    $databaseName = (string)$pdo->query('SELECT DATABASE()')->fetchColumn();
    $version = (string)$pdo->query('SELECT VERSION()')->fetchColumn();
    if (!preg_match('/\A(\d+\.\d+\.\d+)/', $version, $versionMatch)
        || version_compare($versionMatch[1], '10.2.0', '<')) {
        throw new RuntimeException('MariaDB 10.2.0 or newer is required for the indexed generated column.');
    }

    $columnNames = [];
    $columnStatement = $pdo->prepare(<<<'SQL'
        SELECT COLUMN_NAME, IS_NULLABLE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'TaiKhoan'
        SQL);
    $columnStatement->execute();
    $accountColumns = $columnStatement->fetchAll(PDO::FETCH_KEY_PAIR);
    foreach ($accountColumns as $columnName => $_) {
        $columnNames[] = (string)$columnName;
    }
    if (!in_array('MaNV', $columnNames, true) || !in_array('TenDangNhap', $columnNames, true)
        || !in_array('MatKhau', $columnNames, true)) {
        throw new RuntimeException('TaiKhoan is missing one or more expected columns.');
    }
    if (strtoupper((string)$accountColumns['MaNV']) !== 'YES') {
        throw new RuntimeException('TaiKhoan.MaNV must be nullable before detaching Admin.');
    }

    $employeeRole = $pdo->prepare(<<<'SQL'
        SELECT MaVaiTro
        FROM VaiTro
        WHERE TenVaiTro = 'Quản trị viên'
        ORDER BY MaVaiTro
        SQL);
    $employeeRole->execute();
    $adminRoleIds = array_map('intval', $employeeRole->fetchAll(PDO::FETCH_COLUMN));
    if (count($adminRoleIds) !== 1) {
        throw new RuntimeException('Expected exactly one "Quản trị viên" role; no migration was applied.');
    }
    $adminRoleId = $adminRoleIds[0];

    $standaloneColumns = array_intersect(['LoaiTaiKhoan', 'AdminSingleton'], $columnNames);
    if ($standaloneColumns !== [] && count($standaloneColumns) !== 2) {
        throw new RuntimeException('TaiKhoan has a partial Admin account migration; inspect it manually.');
    }
    $alreadyMigrated = count($standaloneColumns) === 2;

    if (!$alreadyMigrated) {
        $legacy = $pdo->prepare(<<<'SQL'
            SELECT tk.MaTK, tk.MaNV
            FROM TaiKhoan tk
            INNER JOIN NhanVien nv ON nv.MaNV = tk.MaNV
            WHERE nv.MaVaiTro = :admin_role_id
            ORDER BY tk.MaTK
            SQL);
        $legacy->execute(['admin_role_id' => $adminRoleId]);
        $legacyAdmins = $legacy->fetchAll();
        if (count($legacyAdmins) !== 1 || (int)$legacyAdmins[0]['MaNV'] < 1) {
            throw new RuntimeException('Expected exactly one legacy Admin account linked to an Admin profile.');
        }
        $legacyAdmin = $legacyAdmins[0];
    } else {
        $adminQuery = $pdo->query(<<<'SQL'
            SELECT MaTK, MaNV
            FROM TaiKhoan
            WHERE LoaiTaiKhoan = 'ADMIN'
            ORDER BY MaTK
            SQL);
        $adminRows = $adminQuery->fetchAll();
        if (count($adminRows) > 1) {
            throw new RuntimeException('Multiple Admin accounts exist; the migration will not choose one.');
        }
        if (count($adminRows) === 1) {
            if ($adminRows[0]['MaNV'] !== null) {
                throw new RuntimeException('The ADMIN account still has MaNV; inspect partial migration state.');
            }
            $legacyAdmin = $adminRows[0];
        } else {
            $legacy = $pdo->prepare(<<<'SQL'
                SELECT tk.MaTK, tk.MaNV
                FROM TaiKhoan tk
                INNER JOIN NhanVien nv ON nv.MaNV = tk.MaNV
                WHERE nv.MaVaiTro = :admin_role_id
                ORDER BY tk.MaTK
                SQL);
            $legacy->execute(['admin_role_id' => $adminRoleId]);
            $legacyAdmins = $legacy->fetchAll();
            if (count($legacyAdmins) !== 1 || (int)$legacyAdmins[0]['MaNV'] < 1) {
                throw new RuntimeException('No unique legacy Admin account was found.');
            }
            $legacyAdmin = $legacyAdmins[0];
        }
    }

    $indexStatement = $pdo->prepare(<<<'SQL'
        SELECT 1
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'TaiKhoan'
          AND INDEX_NAME = 'UQ_TaiKhoan_AdminSingleton'
          AND NON_UNIQUE = 0
        LIMIT 1
        SQL);
    $indexStatement->execute();
    $hasSingletonIndex = $indexStatement->fetchColumn() !== false;
    $checkStatement = $pdo->prepare(<<<'SQL'
        SELECT 1
        FROM information_schema.TABLE_CONSTRAINTS
        WHERE CONSTRAINT_SCHEMA = DATABASE()
          AND TABLE_NAME = 'TaiKhoan'
          AND CONSTRAINT_NAME = 'CK_TaiKhoan_AdminDetached'
          AND CONSTRAINT_TYPE = 'CHECK'
        LIMIT 1
        SQL);
    $checkStatement->execute();
    $hasDetachedCheck = $checkStatement->fetchColumn() !== false;
    if ($alreadyMigrated && (!$hasSingletonIndex || !$hasDetachedCheck)) {
        throw new RuntimeException('Admin account columns exist without all expected constraints.');
    }

    if ($alreadyMigrated && $pdo->query("SELECT COUNT(*) FROM TaiKhoan WHERE LoaiTaiKhoan = 'ADMIN' AND MaNV IS NULL")->fetchColumn() == 1) {
        fwrite(STDOUT, "Already migrated: one detached Admin account exists in {$databaseName}; no changes made.\n");
        exit(0);
    }

    fwrite(STDOUT, "Database: {$databaseName}\n");
    fwrite(STDOUT, "MariaDB: {$version}\n");
    fwrite(STDOUT, "Admin account ID to preserve: " . (int)$legacyAdmin['MaTK'] . "\n");
    fwrite(STDOUT, "Password hash: unchanged\n");
    fwrite(STDOUT, "Employee/account/history deletes: 0\n");
    fwrite(STDOUT, "Action: " . ($apply ? 'APPLY requested' : 'DRY RUN; no writes') . "\n");

    if (!$apply) {
        fwrite(STDOUT, "Ready. Review the plan, then run with --apply to make the reversible account-link migration.\n");
        exit(0);
    }

    if (!$alreadyMigrated) {
        $pdo->exec(<<<'SQL'
            ALTER TABLE TaiKhoan
                ADD COLUMN LoaiTaiKhoan ENUM('ADMIN', 'LEGACY') NOT NULL DEFAULT 'LEGACY' AFTER MaNV,
                ADD COLUMN AdminSingleton TINYINT
                    GENERATED ALWAYS AS (IF(LoaiTaiKhoan = 'ADMIN', 1, NULL)) PERSISTENT,
                ADD UNIQUE KEY UQ_TaiKhoan_AdminSingleton (AdminSingleton),
                ADD CONSTRAINT CK_TaiKhoan_AdminDetached
                    CHECK (LoaiTaiKhoan <> 'ADMIN' OR MaNV IS NULL)
            SQL);
    }

    $pdo->beginTransaction();
    try {
        $legacy = $pdo->prepare(<<<'SQL'
            SELECT tk.MaTK, tk.MaNV, tk.TenDangNhap, tk.MatKhau
            FROM TaiKhoan tk
            INNER JOIN NhanVien nv ON nv.MaNV = tk.MaNV
            WHERE nv.MaVaiTro = :admin_role_id
            ORDER BY tk.MaTK
            FOR UPDATE
            SQL);
        $legacy->execute(['admin_role_id' => $adminRoleId]);
        $legacyAdmins = $legacy->fetchAll();
        if (count($legacyAdmins) !== 1) {
            // Idempotent re-entry after an earlier successful data phase.
            $currentAdmin = $pdo->query(<<<'SQL'
                SELECT MaTK, MaNV, TenDangNhap, MatKhau
                FROM TaiKhoan
                WHERE LoaiTaiKhoan = 'ADMIN' AND MaNV IS NULL
                LIMIT 2
                FOR UPDATE
                SQL)->fetchAll();
            if (count($currentAdmin) !== 1) {
                throw new RuntimeException('Admin row changed during migration; transaction rolled back.');
            }
            $pdo->commit();
            fwrite(STDOUT, "Admin already detached; no data row changed.\n");
            exit(0);
        }

        $account = $legacyAdmins[0];
        $update = $pdo->prepare(<<<'SQL'
            UPDATE TaiKhoan
            SET LoaiTaiKhoan = 'ADMIN', MaNV = NULL
            WHERE MaTK = :account_id AND MaNV = :employee_id
            SQL);
        $update->execute([
            'account_id' => (int)$account['MaTK'],
            'employee_id' => (int)$account['MaNV'],
        ]);
        if ($update->rowCount() !== 1) {
            throw new RuntimeException('Admin account was not detached exactly once.');
        }

        $verify = $pdo->prepare(<<<'SQL'
            SELECT TenDangNhap, MatKhau, MaNV
            FROM TaiKhoan
            WHERE MaTK = :account_id AND LoaiTaiKhoan = 'ADMIN'
            LIMIT 1
            SQL);
        $verify->execute(['account_id' => (int)$account['MaTK']]);
        $saved = $verify->fetch();
        if ($saved === false || $saved['MaNV'] !== null
            || !hash_equals((string)$account['TenDangNhap'], (string)$saved['TenDangNhap'])
            || !hash_equals((string)$account['MatKhau'], (string)$saved['MatKhau'])) {
            throw new RuntimeException('Admin credentials changed during migration; transaction rolled back.');
        }
        $pdo->commit();
    } catch (Throwable $exception) {
        if ($pdo->inTransaction()) {
            $pdo->rollBack();
        }
        throw $exception;
    }

    fwrite(STDOUT, "Migration applied. Admin username/password hash preserved; no employee rows or history deleted.\n");
    fwrite(STDOUT, "Rollback plan: reattach the ADMIN account to the unique NhanVien row with the Admin role, then remove CK_TaiKhoan_AdminDetached, UQ_TaiKhoan_AdminSingleton, AdminSingleton, and LoaiTaiKhoan.\n");
} catch (Throwable $exception) {
    fwrite(STDERR, 'Migration stopped: ' . $exception->getMessage() . "\n");
    exit(1);
}
