<?php
declare(strict_types=1);

function readMessage(): array
{
    $line = fgets(STDIN);
    if ($line === false) {
        throw new RuntimeException('Unexpected end of migration stream.');
    }

    $message = json_decode($line, true, 512, JSON_THROW_ON_ERROR);
    if (!is_array($message)) {
        throw new RuntimeException('Invalid migration message.');
    }

    return $message;
}

function quoteIdentifier(string $identifier): string
{
    if (!preg_match('/^[A-Za-z_][A-Za-z0-9_]*$/', $identifier)) {
        throw new RuntimeException('Unsafe SQL identifier received.');
    }

    return '`' . $identifier . '`';
}

function normalizedForeignKeys(array $foreignKeys): array
{
    $normalized = [];
    foreach ($foreignKeys as $foreignKey) {
        $normalized[] = strtolower(implode('.', [
            $foreignKey['table'],
            $foreignKey['column'],
            $foreignKey['referenced_table'],
            $foreignKey['referenced_column'],
        ]));
    }
    sort($normalized, SORT_STRING);

    return $normalized;
}

function integerOrNull($value): ?int
{
    return $value === null ? null : (int)$value;
}

$allowedTables = [
    'VaiTro', 'ThietBi', 'CaLamViec', 'DanhMucBieuHien', 'LoaiCanhBao',
    'NhanVien', 'TaiKhoan', 'LichSuSucKhoe', 'ThongSoMoiTruong',
    'LichSuTrangThai', 'PhanCaNhanVien', 'ChamCong', 'FaceEmbedding', 'CanhBao',
];
$pdo = null;
$currentTable = 'preflight';
$currentPrimaryKey = null;
$transactionCommitted = false;

try {
    $host = getenv('MARIADB_HOST') ?: '127.0.0.1';
    $port = getenv('MARIADB_PORT') ?: '3306';
    $database = getenv('MARIADB_DATABASE') ?: 'DoAn_ChamCong_AI_MariaDB';
    $username = getenv('MARIADB_USER') ?: 'root';
    $password = getenv('MARIADB_PASSWORD') ?: '';
    $dsn = sprintf('mysql:host=%s;port=%s;dbname=%s;charset=utf8mb4', $host, $port, $database);

    $pdo = new PDO($dsn, $username, $password, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);

    $header = readMessage();
    if (($header['type'] ?? null) !== 'header' || !isset($header['tables'], $header['foreign_keys'])) {
        throw new RuntimeException('Migration header is missing or invalid.');
    }

    $tables = $header['tables'];
    $receivedNames = array_column($tables, 'name');
    if ($receivedNames !== $allowedTables) {
        throw new RuntimeException('Source table list or dependency order is not the approved 14-table list.');
    }

    $databaseTables = $pdo->query(
        "SELECT TABLE_NAME FROM information_schema.TABLES " .
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
    )->fetchAll(PDO::FETCH_COLUMN);
    $databaseTables = array_map('strtolower', $databaseTables);
    $expectedNames = array_map('strtolower', $allowedTables);
    sort($databaseTables, SORT_STRING);
    sort($expectedNames, SORT_STRING);
    if ($databaseTables !== $expectedNames) {
        throw new RuntimeException('MariaDB destination must contain exactly the 14 business tables and no sysdiagrams.');
    }

    foreach ($tables as $tableInfo) {
        $currentTable = $tableInfo['name'];
        $table = quoteIdentifier($currentTable);
        $columnRows = $pdo->query(
            'SELECT COLUMN_NAME FROM information_schema.COLUMNS ' .
            'WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ' . $pdo->quote($currentTable) .
            ' ORDER BY ORDINAL_POSITION'
        )->fetchAll(PDO::FETCH_COLUMN);
        if (array_map('strtolower', $columnRows) !== array_map('strtolower', $tableInfo['columns'])) {
            throw new RuntimeException("Column mismatch for {$currentTable}.");
        }

        $primaryRows = $pdo->query(
            'SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE ' .
            'WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ' . $pdo->quote($currentTable) .
            " AND CONSTRAINT_NAME = 'PRIMARY' ORDER BY ORDINAL_POSITION"
        )->fetchAll(PDO::FETCH_COLUMN);
        if (array_map('strtolower', $primaryRows) !== [strtolower($tableInfo['primary_key'])]) {
            throw new RuntimeException("Primary key mismatch for {$currentTable}.");
        }

        $count = (int)$pdo->query("SELECT COUNT(*) FROM {$table}")->fetchColumn();
        if ($count !== 0) {
            throw new RuntimeException("Destination table {$currentTable} is not empty; refusing to import or truncate.");
        }
    }

    $destinationForeignKeys = $pdo->query(
        'SELECT TABLE_NAME AS `table`, COLUMN_NAME AS `column`, ' .
        'REFERENCED_TABLE_NAME AS referenced_table, REFERENCED_COLUMN_NAME AS referenced_column ' .
        'FROM information_schema.KEY_COLUMN_USAGE ' .
        'WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL'
    )->fetchAll();
    if (normalizedForeignKeys($destinationForeignKeys) !== normalizedForeignKeys($header['foreign_keys'])) {
        throw new RuntimeException('Foreign key structure differs between SQL Server source and MariaDB destination.');
    }
    if (count($destinationForeignKeys) !== 16) {
        throw new RuntimeException('Expected 16 foreign keys but found a different count.');
    }

    if (!$pdo->beginTransaction()) {
        throw new RuntimeException('Could not start MariaDB transaction.');
    }

    $tableReports = [];
    $binaryReports = [];
    $unicodeSamples = [];

    foreach ($tables as $tableInfo) {
        $currentTable = $tableInfo['name'];
        $currentPrimaryKey = null;
        $table = quoteIdentifier($currentTable);
        $columns = array_map('quoteIdentifier', $tableInfo['columns']);
        $columnNames = $tableInfo['columns'];
        $primaryKey = quoteIdentifier($tableInfo['primary_key']);
        $insert = $pdo->prepare(
            "INSERT INTO {$table} (" . implode(', ', $columns) . ') VALUES (' .
            implode(', ', array_fill(0, count($columns), '?')) . ')'
        );
        $columnIndexes = array_flip($columnNames);
        $rowsReceived = 0;
        $expectedBinaryRows = [];

        while (true) {
            $message = readMessage();
            if (($message['type'] ?? null) === 'table_end') {
                if (($message['name'] ?? null) !== $currentTable) {
                    throw new RuntimeException("Unexpected table end while importing {$currentTable}.");
                }
                break;
            }
            if (($message['type'] ?? null) !== 'row' || !isset($message['values']) ||
                count($message['values']) !== count($columnNames)) {
                throw new RuntimeException("Invalid row message for {$currentTable}.");
            }

            $values = [];
            foreach ($message['values'] as $index => $value) {
                if (is_array($value) && ($value['__migration_type'] ?? null) === 'binary') {
                    $decoded = base64_decode($value['base64'] ?? '', true);
                    if ($decoded === false) {
                        throw new RuntimeException("Invalid binary encoding in {$currentTable}.");
                    }
                    $column = $columnNames[$index];
                    $sourceBinary = $message['binary_checks'][$column] ?? null;
                    if (!is_array($sourceBinary) ||
                        (int)$sourceBinary['length'] !== strlen($decoded) ||
                        !hash_equals((string)$sourceBinary['sha256'], hash('sha256', $decoded))) {
                        throw new RuntimeException("Source binary checksum mismatch at {$currentTable}.{$column}.");
                    }
                    $values[] = $decoded;
                    $expectedBinaryRows[] = [
                        'column' => $column,
                        'primary_key' => null,
                        'length' => strlen($decoded),
                        'sha256' => hash('sha256', $decoded),
                        'employee_id' => $currentTable === 'FaceEmbedding' ? (int)$message['values'][$columnIndexes['MaNV']] : null,
                        'dimensions' => $currentTable === 'FaceEmbedding' ? (int)$message['values'][$columnIndexes['SoChieu']] : null,
                    ];
                } elseif (is_array($value) && isset($value['__migration_type'])) {
                    if (!in_array($value['__migration_type'], ['datetime', 'date', 'time', 'decimal'], true)) {
                        throw new RuntimeException("Unsupported value type at {$currentTable}.{$columnNames[$index]}.");
                    }
                    $values[] = $value['value'];
                } else {
                    $values[] = $value;
                }
            }

            $currentPrimaryKey = $values[$columnIndexes[$tableInfo['primary_key']]];
            foreach ($values as $index => $value) {
                if (in_array($columnNames[$index], $tableInfo['text_columns'], true) &&
                    is_string($value) && preg_match('/[^\x00-\x7F]/', $value) === 1) {
                    $sampleKey = $currentTable . '.' . $columnNames[$index];
                    if (!isset($unicodeSamples[$sampleKey])) {
                        $unicodeSamples[$sampleKey] = [
                            'table' => $currentTable,
                            'column' => $columnNames[$index],
                            'primary_key' => $currentPrimaryKey,
                            'value' => $value,
                        ];
                    }
                }
            }

            foreach ($values as $index => $value) {
                $type = match (true) {
                    $value === null => PDO::PARAM_NULL,
                    is_int($value) => PDO::PARAM_INT,
                    is_bool($value) => PDO::PARAM_BOOL,
                    is_string($value) && in_array($columnNames[$index], $tableInfo['binary_columns'], true) => PDO::PARAM_LOB,
                    default => PDO::PARAM_STR,
                };
                $insert->bindValue($index + 1, $value, $type);
            }
            $insert->execute();

            foreach ($expectedBinaryRows as &$binaryReport) {
                if ($binaryReport['primary_key'] === null) {
                    $binaryReport['primary_key'] = $currentPrimaryKey;
                }
            }
            unset($binaryReport);
            $rowsReceived++;
        }

        if ($rowsReceived !== (int)$tableInfo['source_count']) {
            throw new RuntimeException("Row count mismatch while streaming {$currentTable}: received {$rowsReceived}.");
        }

        $aggregateColumns = ['COUNT(*)'];
        $aggregateColumns[] = "MIN({$primaryKey})";
        $aggregateColumns[] = "MAX({$primaryKey})";
        foreach ($columnNames as $columnName) {
            $aggregateColumns[] = 'SUM(' . quoteIdentifier($columnName) . ' IS NULL)';
        }
        $aggregate = $pdo->query('SELECT ' . implode(', ', $aggregateColumns) . " FROM {$table}")->fetch(PDO::FETCH_NUM);
        $destinationCount = (int)$aggregate[0];
        $destinationMin = integerOrNull($aggregate[1]);
        $destinationMax = integerOrNull($aggregate[2]);
        if ($destinationCount !== (int)$tableInfo['source_count'] ||
            $destinationMin !== integerOrNull($tableInfo['source_min']) ||
            $destinationMax !== integerOrNull($tableInfo['source_max'])) {
            throw new RuntimeException("Row count or primary-key range mismatch for {$currentTable}.");
        }

        $nullCounts = [];
        foreach ($columnNames as $index => $columnName) {
            $sourceNulls = (int)$tableInfo['null_counts'][$columnName];
            $destinationNulls = (int)($aggregate[$index + 3] ?? 0);
            $nullCounts[$columnName] = $destinationNulls;
            if ($sourceNulls !== $destinationNulls) {
                throw new RuntimeException("NULL count mismatch at {$currentTable}.{$columnName}.");
            }
        }

        foreach ($expectedBinaryRows as $binaryRow) {
            $binaryColumn = quoteIdentifier($binaryRow['column']);
            $selectFields = [$primaryKey];
            if ($currentTable === 'FaceEmbedding') {
                $selectFields[] = quoteIdentifier('MaNV');
                $selectFields[] = quoteIdentifier('SoChieu');
            }
            $selectFields[] = 'OCTET_LENGTH(' . $binaryColumn . ')';
            $selectFields[] = $binaryColumn;
            $verify = $pdo->prepare(
                'SELECT ' . implode(', ', $selectFields) . " FROM {$table} WHERE {$primaryKey} = ?"
            );
            $verify->execute([$binaryRow['primary_key']]);
            $stored = $verify->fetch(PDO::FETCH_NUM);
            if ($stored === false) {
                throw new RuntimeException("Missing binary record at {$currentTable}.{$binaryRow['primary_key']}.");
            }
            $lengthIndex = $currentTable === 'FaceEmbedding' ? 3 : 1;
            $blobIndex = $lengthIndex + 1;
            $storedBlob = $stored[$blobIndex];
            $storedLength = $stored[$lengthIndex] === null ? null : (int)$stored[$lengthIndex];
            if ($storedLength !== $binaryRow['length'] || !is_string($storedBlob) ||
                !hash_equals($binaryRow['sha256'], hash('sha256', $storedBlob))) {
                throw new RuntimeException("Stored binary checksum mismatch at {$currentTable}.{$binaryRow['primary_key']}.");
            }
            if ($currentTable === 'FaceEmbedding' &&
                ((int)$stored[1] !== $binaryRow['employee_id'] || (int)$stored[2] !== $binaryRow['dimensions'])) {
                throw new RuntimeException("FaceEmbedding metadata mismatch at ID {$binaryRow['primary_key']}.");
            }
            $binaryReports[] = [
                'table' => $currentTable,
                'primary_key' => (int)$binaryRow['primary_key'],
                'employee_id' => $binaryRow['employee_id'],
                'dimensions' => $binaryRow['dimensions'],
                'column' => $binaryRow['column'],
                'length' => $storedLength,
                'sha256' => hash('sha256', $storedBlob),
            ];
        }

        $autoIncrementRow = $pdo->query(
            'SELECT c.EXTRA, t.AUTO_INCREMENT FROM information_schema.COLUMNS c ' .
            'JOIN information_schema.TABLES t ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME ' .
            'WHERE c.TABLE_SCHEMA = DATABASE() AND c.TABLE_NAME = ' . $pdo->quote($currentTable) .
            ' AND c.COLUMN_NAME = ' . $pdo->quote($tableInfo['primary_key'])
        )->fetch();
        if ($autoIncrementRow === false || stripos($autoIncrementRow['EXTRA'], 'auto_increment') === false) {
            throw new RuntimeException("AUTO_INCREMENT is missing for {$currentTable}.{$tableInfo['primary_key']}.");
        }
        $nextId = (int)($autoIncrementRow['AUTO_INCREMENT'] ?? 1);
        $maximumId = $destinationMax ?? 0;
        if ($nextId <= $maximumId) {
            throw new RuntimeException("AUTO_INCREMENT collision risk in {$currentTable}: next {$nextId}, max {$maximumId}.");
        }

        $tableReports[] = [
            'table' => $currentTable,
            'source_rows' => (int)$tableInfo['source_count'],
            'destination_rows' => $destinationCount,
            'primary_key_min' => $destinationMin,
            'primary_key_max' => $destinationMax,
            'null_counts_match' => true,
            'auto_increment_next' => $nextId,
        ];
        $currentPrimaryKey = null;
    }

    $foreignKeyReport = [];
    foreach ($header['foreign_keys'] as $foreignKey) {
        $childTable = quoteIdentifier($foreignKey['table']);
        $childColumn = quoteIdentifier($foreignKey['column']);
        $parentTable = quoteIdentifier($foreignKey['referenced_table']);
        $parentColumn = quoteIdentifier($foreignKey['referenced_column']);
        $orphans = (int)$pdo->query(
            "SELECT COUNT(*) FROM {$childTable} c LEFT JOIN {$parentTable} p " .
            "ON c.{$childColumn} = p.{$parentColumn} " .
            "WHERE c.{$childColumn} IS NOT NULL AND p.{$parentColumn} IS NULL"
        )->fetchColumn();
        if ($orphans !== 0) {
            throw new RuntimeException("Foreign key orphan check failed for {$foreignKey['table']}.{$foreignKey['column']}.");
        }
        $foreignKeyReport[] = ['table' => $foreignKey['table'], 'column' => $foreignKey['column'], 'orphans' => 0];
    }

    foreach ($unicodeSamples as $sample) {
        $sampleTable = quoteIdentifier($sample['table']);
        $sampleColumn = quoteIdentifier($sample['column']);
        $samplePk = quoteIdentifier($tables[array_search($sample['table'], $receivedNames, true)]['primary_key']);
        $verifySample = $pdo->prepare(
            "SELECT {$sampleColumn} FROM {$sampleTable} WHERE {$samplePk} = ?"
        );
        $verifySample->execute([$sample['primary_key']]);
        $storedValue = $verifySample->fetchColumn();
        if (!is_string($storedValue) || $storedValue !== $sample['value']) {
            throw new RuntimeException("Unicode sample mismatch at {$sample['table']}.{$sample['column']}.");
        }
    }
    if (count($unicodeSamples) === 0) {
        throw new RuntimeException('No non-ASCII source text sample was available to verify Unicode preservation.');
    }

    if (count($foreignKeyReport) !== 16) {
        throw new RuntimeException('Not all 16 foreign keys were checked.');
    }

    $summary = [
        'ok' => true,
        'database' => $database,
        'table_count' => count($tableReports),
        'total_rows' => array_sum(array_column($tableReports, 'destination_rows')),
        'tables' => $tableReports,
        'binary_records' => $binaryReports,
        'binary_hashes_match' => true,
        'foreign_key_count' => count($foreignKeyReport),
        'foreign_keys' => $foreignKeyReport,
        'foreign_keys_pass' => true,
        'auto_increment_pass' => true,
        'unicode_sample_count' => count($unicodeSamples),
        'unicode_samples_pass' => true,
    ];

    $currentTable = 'commit';
    $pdo->commit();
    $transactionCommitted = true;

    echo json_encode($summary, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR), PHP_EOL;
} catch (Throwable $exception) {
    if ($pdo instanceof PDO && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    $commitState = $transactionCommitted ? 'data was committed; post-commit failure needs review' : 'transaction rolled back';
    $record = $currentPrimaryKey === null ? '' : " record={$currentPrimaryKey}";
    fwrite(STDERR, "Migration failed at {$currentTable}{$record}: {$exception->getMessage()} ({$commitState})" . PHP_EOL);
    exit(1);
}
