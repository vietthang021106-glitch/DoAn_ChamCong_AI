<?php
declare(strict_types=1);

final class Database
{
    private static ?PDO $connection = null;
    private static ?WeakMap $employeeSoftDeleteColumnCache = null;
    private static ?WeakMap $employeeRoleColumnCache = null;
    private static ?WeakMap $employeeRoleCatalogCache = null;

    /** Tạo hoặc trả về kết nối PDO dùng chung tới MariaDB của ứng dụng PHP. */
    public static function getConnection(): PDO
    {
        if (self::$connection !== null) {
            return self::$connection;
        }

        if (!in_array('mysql', PDO::getAvailableDrivers(), true)) {
            throw new RuntimeException('The PDO MySQL driver is not enabled.');
        }

        $host = getenv('MARIADB_HOST') ?: '127.0.0.1';
        $port = getenv('MARIADB_PORT') ?: '3306';
        $database = getenv('MARIADB_DATABASE') ?: 'DoAn_ChamCong_AI_MariaDB';
        $username = getenv('MARIADB_USER') ?: 'root';
        $password = getenv('MARIADB_PASSWORD');
        if ($password === false) {
            $password = '';
        }

        $dsn = sprintf(
            'mysql:host=%s;port=%s;dbname=%s;charset=utf8mb4',
            $host,
            $port,
            $database
        );

        self::$connection = new PDO($dsn, $username, $password, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);

        return self::$connection;
    }

    /** Return whether the connected schema has the optional employee soft-delete column. */
    public static function supportsEmployeeSoftDelete(?PDO $connection = null): bool
    {
        $pdo = $connection ?? self::getConnection();
        self::$employeeSoftDeleteColumnCache ??= new WeakMap();
        if (self::$employeeSoftDeleteColumnCache->offsetExists($pdo)) {
            return self::$employeeSoftDeleteColumnCache[$pdo];
        }

        $driver = (string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        if ($driver === 'mysql') {
            $statement = $pdo->prepare(<<<'SQL'
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = :table_name
                  AND COLUMN_NAME = :column_name
                LIMIT 1
                SQL);
            $statement->execute(['table_name' => 'NhanVien', 'column_name' => 'DaXoa']);
            $supported = $statement->fetchColumn() !== false;
        } elseif ($driver === 'sqlite') {
            $columns = $pdo->query('PRAGMA table_info(`NhanVien`)')->fetchAll(PDO::FETCH_ASSOC);
            $supported = false;
            foreach ($columns as $column) {
                if (strcasecmp((string)$column['name'], 'DaXoa') === 0) {
                    $supported = true;
                    break;
                }
            }
        } else {
            throw new RuntimeException('Unsupported database driver for employee schema inspection.');
        }

        self::$employeeSoftDeleteColumnCache[$pdo] = $supported;
        return $supported;
    }

    /** Build a role predicate that includes only rows explicitly classified as employees. */
    public static function employeeRolePredicate(string $alias = '', ?PDO $connection = null): string
    {
        if ($alias !== '' && !preg_match('/\A[A-Za-z_][A-Za-z0-9_]*\z/', $alias)) {
            throw new InvalidArgumentException('Invalid SQL alias for employee status predicate.');
        }

        $pdo = $connection ?? self::getConnection();
        $prefix = $alias === '' ? '' : $alias . '.';
        if (self::supportsEmployeeRoleColumn($pdo)) {
            if (self::hasEmployeeRoleCatalog($pdo)) {
                return $prefix . "MaVaiTro = (SELECT MaVaiTro FROM VaiTro WHERE TenVaiTro = 'Nhân viên' LIMIT 1)";
            }

            // Without the role catalog, the database cannot safely distinguish an
            // employee row from a legacy Admin profile. Fail closed.
            return '1 = 0';
        }

        // Compatibility with older schemas that do not model roles on NhanVien.
        return '1 = 1';
    }

    /** Build a SQL predicate for active employees across old and soft-delete schemas. */
    public static function activeEmployeePredicate(string $alias = '', ?PDO $connection = null): string
    {
        if ($alias !== '' && !preg_match('/\A[A-Za-z_][A-Za-z0-9_]*\z/', $alias)) {
            throw new InvalidArgumentException('Invalid SQL alias for employee status predicate.');
        }

        $pdo = $connection ?? self::getConnection();
        $prefix = $alias === '' ? '' : $alias . '.';
        $predicates = [self::employeeRolePredicate($alias, $pdo)];
        if (self::supportsEmployeeSoftDelete($pdo)) {
            $predicates[] = $prefix . 'DaXoa = 0';
        }

        return implode(' AND ', $predicates);
    }

    private static function supportsEmployeeRoleColumn(PDO $pdo): bool
    {
        self::$employeeRoleColumnCache ??= new WeakMap();
        if (self::$employeeRoleColumnCache->offsetExists($pdo)) {
            return self::$employeeRoleColumnCache[$pdo];
        }

        $driver = (string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        if ($driver === 'mysql') {
            $statement = $pdo->prepare(<<<'SQL'
                SELECT 1
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'NhanVien'
                  AND COLUMN_NAME = 'MaVaiTro'
                LIMIT 1
                SQL);
            $statement->execute();
            $supported = $statement->fetchColumn() !== false;
        } elseif ($driver === 'sqlite') {
            $supported = false;
            foreach ($pdo->query('PRAGMA table_info(`NhanVien`)')->fetchAll(PDO::FETCH_ASSOC) as $column) {
                if (strcasecmp((string)$column['name'], 'MaVaiTro') === 0) {
                    $supported = true;
                    break;
                }
            }
        } else {
            throw new RuntimeException('Unsupported database driver for employee role inspection.');
        }

        self::$employeeRoleColumnCache[$pdo] = $supported;
        return $supported;
    }

    private static function hasEmployeeRoleCatalog(PDO $pdo): bool
    {
        self::$employeeRoleCatalogCache ??= new WeakMap();
        if (self::$employeeRoleCatalogCache->offsetExists($pdo)) {
            return self::$employeeRoleCatalogCache[$pdo];
        }

        $driver = (string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        if ($driver === 'mysql') {
            $statement = $pdo->prepare(<<<'SQL'
                SELECT 1
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'VaiTro'
                LIMIT 1
                SQL);
            $statement->execute();
            $exists = $statement->fetchColumn() !== false;
        } elseif ($driver === 'sqlite') {
            $statement = $pdo->prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'VaiTro' LIMIT 1");
            $statement->execute();
            $exists = $statement->fetchColumn() !== false;
        } else {
            throw new RuntimeException('Unsupported database driver for role catalog inspection.');
        }

        self::$employeeRoleCatalogCache[$pdo] = $exists;
        return $exists;
    }
}
