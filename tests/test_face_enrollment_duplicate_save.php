<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';

function assertEnrollmentDuplicate(bool $condition, string $message): void
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

if (!in_array('sqlite', PDO::getAvailableDrivers(), true)) {
    echo "Face enrollment duplicate save SKIP: PDO SQLite is unavailable\n";
    exit(0);
}

function enrollmentDuplicateVector(float $angle): string
{
    $values = array_fill(0, 512, 0.0);
    $values[0] = cos($angle);
    $values[1] = sin($angle);
    return pack('g*', ...$values);
}

function enrollmentDuplicateSamples(float $angle): array
{
    $image = base64_decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aPZsAAAAASUVORK5CYII=',
        true
    );
    $samples = [];
    foreach (['frontal', 'left', 'right', 'up', 'down'] as $pose) {
        $samples[] = [
            'pose' => $pose,
            'vector' => enrollmentDuplicateVector($angle),
            'image' => $image,
        ];
    }
    return $samples;
}

function enrollmentEmptyRevision(FaceEmbeddingModel $model, int $employeeId): string
{
    return $model->enrollmentRevision($employeeId)['revision'];
}

$pdo = new PDO('sqlite::memory:', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$pdo->exec('PRAGMA foreign_keys = ON');
$pdo->exec('CREATE TABLE NhanVien (MaNV INTEGER PRIMARY KEY, HoTen TEXT NOT NULL)');
$pdo->exec(<<<'SQL'
    CREATE TABLE FaceEmbedding (
        MaEmbedding INTEGER PRIMARY KEY AUTOINCREMENT,
        MaNV INTEGER NOT NULL,
        VectorData BLOB NOT NULL,
        AnhKhuonMat BLOB NOT NULL,
        SoChieu INTEGER NOT NULL,
        ThoiGianTao TEXT NOT NULL,
        FOREIGN KEY (MaNV) REFERENCES NhanVien(MaNV)
    )
    SQL);
$pdo->exec("INSERT INTO NhanVien (MaNV, HoTen) VALUES (1, 'NV001'), (22, 'NV022')");

$checker = new FaceDuplicateChecker(0.95, true, 'buffalo_l', 'max_5x5_cosine');
$model = new FaceEmbeddingModel($pdo, $checker);
$personA = enrollmentDuplicateSamples(0.0);
$personB = enrollmentDuplicateSamples(M_PI / 2);

// Two enrollment sessions may both precheck an empty gallery. The final save
// must re-read the latest gallery and reject the later duplicate batch.
assertEnrollmentDuplicate($model->checkDuplicate(1, $personA)['status'] === 'CLEAR', 'First empty-gallery precheck should be clear.');
assertEnrollmentDuplicate($model->checkDuplicate(22, $personA)['status'] === 'CLEAR', 'Concurrent precheck may be clear before another save.');
$model->replaceByEmployee(1, $personA, enrollmentEmptyRevision($model, 1));
try {
    $model->replaceByEmployee(22, $personA, enrollmentEmptyRevision($model, 22));
    throw new RuntimeException('The second, stale-prechecked duplicate batch should be rejected.');
} catch (FaceDuplicateCheckException $exception) {
    assertEnrollmentDuplicate(
        $exception->checkResult()['status'] === 'SUSPECTED_DUPLICATE',
        'The final-save decision should report a suspected duplicate.'
    );
}
$countNv001 = (int)$pdo->query('SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV = 1')->fetchColumn();
$countNv022 = (int)$pdo->query('SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV = 22')->fetchColumn();
assertEnrollmentDuplicate($countNv001 === 5 && $countNv022 === 0, 'A duplicate save must add no rows.');

// A failed re-enrollment must leave that employee's old five samples intact.
$model->replaceByEmployee(22, $personB, enrollmentEmptyRevision($model, 22));
$before = $pdo->query('SELECT MaEmbedding, VectorData FROM FaceEmbedding WHERE MaNV = 22 ORDER BY MaEmbedding')->fetchAll();
$currentRevision = $model->enrollmentRevision(22)['revision'];
try {
    $model->replaceByEmployee(22, $personA, $currentRevision);
    throw new RuntimeException('A duplicate re-enrollment should be rejected.');
} catch (FaceDuplicateCheckException $exception) {
    assertEnrollmentDuplicate(
        $exception->checkResult()['status'] === 'SUSPECTED_DUPLICATE',
        'Re-enrollment must report the external duplicate.'
    );
}
$after = $pdo->query('SELECT MaEmbedding, VectorData FROM FaceEmbedding WHERE MaNV = 22 ORDER BY MaEmbedding')->fetchAll();
assertEnrollmentDuplicate(count($before) === 5 && count($after) === 5, 'A rejected replace must preserve five old samples.');
foreach ($before as $index => $row) {
    assertEnrollmentDuplicate(
        (int)$row['MaEmbedding'] === (int)$after[$index]['MaEmbedding']
            && $row['VectorData'] === $after[$index]['VectorData'],
        'A failed duplicate replacement must preserve the old embedding bytes.'
    );
}

$pdo->exec('DROP TABLE FaceEmbedding');
$unavailable = $model->checkDuplicate(22, $personA);
assertEnrollmentDuplicate(
    $unavailable['status'] === 'CHECK_UNAVAILABLE',
    'A database/gallery query failure must not be reported as clear.'
);

echo "Face enrollment duplicate save PASS\n";
