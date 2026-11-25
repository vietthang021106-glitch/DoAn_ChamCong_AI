<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class AccountModel
{
    private ?PDO $connection;
    private static ?WeakMap $standaloneAdminSchemaCache = null;

    public function __construct(?PDO $connection = null)
    {
        $this->connection = $connection;
    }

    private const WERKZEUG_SCRYPT_VERIFIER = <<<'PYTHON'
import hashlib
import hmac
import json
import sys

try:
    payload = json.load(sys.stdin)
    method, salt, expected_hex = payload["stored"].split("$", 2)
    parts = method.split(":")
    if len(parts) != 4 or parts[0] != "scrypt":
        sys.exit(2)

    n, r, p = (int(value) for value in parts[1:])
    if n < 2 or n > 65536 or n & (n - 1) or r < 1 or r > 8 or p < 1 or p > 4:
        sys.exit(2)

    expected = bytes.fromhex(expected_hex)
    if len(expected) < 16 or len(expected) > 64:
        sys.exit(2)

    actual = hashlib.scrypt(
        payload["password"].encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
        maxmem=134217728,
    )
    sys.stdout.write("1" if hmac.compare_digest(actual, expected) else "0")
except Exception:
    sys.exit(2)
PYTHON;

    /** Authenticate the single Admin account without requiring an employee row. */
    public function authenticate(string $username, string $password): ?array
    {
        $pdo = $this->connection();
        if ($this->supportsStandaloneAdminAccounts($pdo)) {
            $statement = $pdo->prepare(<<<'SQL'
                SELECT MaTK AS UserId, TenDangNhap AS Username, MatKhau AS StoredPassword
                FROM TaiKhoan
                WHERE LoaiTaiKhoan = 'ADMIN' AND MaNV IS NULL AND TenDangNhap = :username
                LIMIT 1
                SQL);
        } else {
            // Temporary compatibility for databases before the explicit account migration.
            $statement = $pdo->prepare(<<<'SQL'
                SELECT tk.MaTK AS UserId, tk.TenDangNhap AS Username, tk.MatKhau AS StoredPassword
                FROM TaiKhoan tk
                INNER JOIN NhanVien nv ON nv.MaNV = tk.MaNV
                INNER JOIN VaiTro vt ON vt.MaVaiTro = nv.MaVaiTro
                WHERE vt.TenVaiTro = 'Quản trị viên' AND tk.TenDangNhap = :username
                  AND (
                    SELECT COUNT(*)
                    FROM TaiKhoan admin_account
                    INNER JOIN NhanVien admin_employee ON admin_employee.MaNV = admin_account.MaNV
                    INNER JOIN VaiTro admin_role ON admin_role.MaVaiTro = admin_employee.MaVaiTro
                    WHERE admin_role.TenVaiTro = 'Quản trị viên'
                  ) = 1
                LIMIT 1
                SQL);
        }
        $statement->execute(['username' => $username]);
        $account = $statement->fetch();

        if ($account === false || !$this->passwordMatches($password, (string)$account['StoredPassword'])) {
            return null;
        }

        return [
            'user_id' => (int)$account['UserId'],
            'username' => (string)$account['Username'],
            'display_name' => 'Quản trị viên',
            'is_admin' => true,
            'role' => 'Quản trị viên',
        ];
    }

    /** Check the Admin account by account ID; standalone mode does not join NhanVien. */
    public function isAdminAccountActive(int $accountId): bool
    {
        if ($accountId < 1) {
            return false;
        }

        $pdo = $this->connection();
        if ($this->supportsStandaloneAdminAccounts($pdo)) {
            $statement = $pdo->prepare(<<<'SQL'
                SELECT 1
                FROM TaiKhoan
                WHERE MaTK = :account_id AND LoaiTaiKhoan = 'ADMIN' AND MaNV IS NULL
                LIMIT 1
                SQL);
        } else {
            $statement = $pdo->prepare(<<<'SQL'
                SELECT 1
                FROM TaiKhoan tk
                INNER JOIN NhanVien nv ON nv.MaNV = tk.MaNV
                INNER JOIN VaiTro vt ON vt.MaVaiTro = nv.MaVaiTro
                WHERE tk.MaTK = :account_id AND vt.TenVaiTro = 'Quản trị viên'
                  AND (
                    SELECT COUNT(*)
                    FROM TaiKhoan admin_account
                    INNER JOIN NhanVien admin_employee ON admin_employee.MaNV = admin_account.MaNV
                    INNER JOIN VaiTro admin_role ON admin_role.MaVaiTro = admin_employee.MaVaiTro
                    WHERE admin_role.TenVaiTro = 'Quản trị viên'
                  ) = 1
                LIMIT 1
                SQL);
        }
        $statement->execute(['account_id' => $accountId]);

        return $statement->fetchColumn() !== false;
    }

    /** Verify the current session employee is still active in the database. */
    public function isEmployeeActive(int $employeeId): bool
    {
        $pdo = $this->connection();
        $activeEmployee = Database::activeEmployeePredicate('', $pdo);
        $statement = $pdo->prepare(
            'SELECT 1 FROM NhanVien WHERE MaNV = :employee_id AND ' . $activeEmployee . ' LIMIT 1'
        );
        $statement->execute(['employee_id' => $employeeId]);

        return $statement->fetchColumn() !== false;
    }

    private function supportsStandaloneAdminAccounts(PDO $pdo): bool
    {
        self::$standaloneAdminSchemaCache ??= new WeakMap();
        if (self::$standaloneAdminSchemaCache->offsetExists($pdo)) {
            return self::$standaloneAdminSchemaCache[$pdo];
        }

        $driver = (string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        if ($driver === 'mysql') {
            $statement = $pdo->prepare(<<<'SQL'
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'TaiKhoan'
                  AND COLUMN_NAME = 'LoaiTaiKhoan'
                SQL);
            $statement->execute();
            $supported = (int)$statement->fetchColumn() === 1;
        } elseif ($driver === 'sqlite') {
            $supported = false;
            foreach ($pdo->query('PRAGMA table_info(`TaiKhoan`)')->fetchAll(PDO::FETCH_ASSOC) as $column) {
                if (strcasecmp((string)$column['name'], 'LoaiTaiKhoan') === 0) {
                    $supported = true;
                    break;
                }
            }
        } else {
            throw new RuntimeException('Unsupported database driver for Admin account schema inspection.');
        }

        self::$standaloneAdminSchemaCache[$pdo] = $supported;
        return $supported;
    }

    private function passwordMatches(string $password, string $storedPassword): bool
    {
        $metadata = password_get_info($storedPassword);
        if (($metadata['algoName'] ?? 'unknown') !== 'unknown') {
            return password_verify($password, $storedPassword);
        }

        if (str_starts_with($storedPassword, 'scrypt:')) {
            return $this->verifyWerkzeugScrypt($password, $storedPassword);
        }

        return hash_equals($storedPassword, $password);
    }

    private function verifyWerkzeugScrypt(string $password, string $storedPassword): bool
    {
        if (!function_exists('proc_open')) {
            return false;
        }

        $input = json_encode([
            'stored' => $storedPassword,
            'password' => $password,
        ]);
        if ($input === false) {
            return false;
        }

        $python = getenv('PYTHON_EXECUTABLE') ?: 'python';
        $process = proc_open(
            [$python, '-c', self::WERKZEUG_SCRYPT_VERIFIER],
            [
                0 => ['pipe', 'r'],
                1 => ['pipe', 'w'],
                2 => ['pipe', 'w'],
            ],
            $pipes,
            null,
            null,
            ['bypass_shell' => true]
        );
        if (!is_resource($process)) {
            return false;
        }

        fwrite($pipes[0], $input);
        fclose($pipes[0]);
        $output = trim(stream_get_contents($pipes[1]));
        fclose($pipes[1]);
        fclose($pipes[2]);
        $exitCode = proc_close($process);

        return $exitCode === 0 && hash_equals('1', $output);
    }

    private function connection(): PDO
    {
        return $this->connection ?? Database::getConnection();
    }
}
