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

function enrollmentCalibrationReport(): array
{
    return [
        'version' => 1, 'validated' => true, 'model' => 'buffalo_l',
        'aggregation' => 'max_5x5_cosine', 'threshold' => 0.95,
        'targets' => ['max_fmr' => 0.05, 'max_fnmr' => 0.10],
        'sample_counts' => [
            'identity_count' => 10, 'session_count' => 20, 'image_count' => 100,
            'genuine_pair_count' => 30, 'impostor_pair_count' => 100,
        ],
        'metrics' => [
            'fmr' => 0.0, 'fnmr' => 0.0, 'false_match_count' => 0,
            'false_non_match_count' => 0, 'genuine_pair_count' => 30,
            'impostor_pair_count' => 100,
        ],
        'dataset_sha256' => str_repeat('b', 64),
    ];
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

$checker = new FaceDuplicateChecker(
    0.95, true, 'buffalo_l', 'max_5x5_cosine', enrollmentCalibrationReport()
);
$model = new FaceEmbeddingModel($pdo, $checker);
$personA = enrollmentDuplicateSamples(0.0);
$personB = enrollmentDuplicateSamples(M_PI / 2);

// Two enrollment sessions may both precheck an empty gallery. The final save
// must re-read the latest gallery and reject the later duplicate batch.
assertEnrollmentDuplicate($model->checkDuplicate(1, $personA)['status'] === 'CLEAR', 'First empty-gallery precheck should be clear.');
assertEnrollmentDuplicate($model->checkDuplicate(22, $personA)['status'] === 'CLEAR', 'Concurrent precheck may be clear before another save.');
$model->replaceByEmployee(1, $personA, enrollmentEmptyRevision($model, 1));
$assertCount = (int)$pdo->query('SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV = 1')->fetchColumn();
assertEnrollmentDuplicate($assertCount === 5, 'Successful save must persist exactly five rows.');
assertEnrollmentDuplicate($model->verifyBatchByEmployee(1, $personA), 'Read-back must verify all five image/vector pairs.');
assertEnrollmentDuplicate($model->countAllActive() === 5, 'Active gallery count must match the database after save.');
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

// A database error after DELETE but during INSERT must roll back the entire batch.
$pdo->exec(<<<'SQL'
    CREATE TRIGGER fail_nv022_insert BEFORE INSERT ON FaceEmbedding
    WHEN NEW.MaNV = 22
    BEGIN
        SELECT RAISE(ABORT, 'forced test insert failure');
    END
    SQL);
try {
    $model->replaceByEmployee(22, enrollmentDuplicateSamples(M_PI / 3), $currentRevision);
    throw new RuntimeException('The forced mid-batch insert failure should abort the save.');
} catch (PDOException $exception) {
    // Expected: the transaction must restore the prior five rows.
}
$pdo->exec('DROP TRIGGER fail_nv022_insert');
$afterInsertFailure = $pdo->query('SELECT MaEmbedding, VectorData, AnhKhuonMat FROM FaceEmbedding WHERE MaNV = 22 ORDER BY MaEmbedding')->fetchAll();
assertEnrollmentDuplicate(count($afterInsertFailure) === 5, 'Failed mid-batch insert must roll back to the old five rows.');
assertEnrollmentDuplicate($model->verifyBatchByEmployee(22, $personB), 'Rolled-back batch must leave the original five samples intact.');

$pdo->exec('DROP TABLE FaceEmbedding');
$unavailable = $model->checkDuplicate(22, $personA);
assertEnrollmentDuplicate(
    $unavailable['status'] === 'CHECK_UNAVAILABLE',
    'A database/gallery query failure must not be reported as clear.'
);

// Local demo bypass: only calibration-unavailable saves may proceed, and the
// duplicate result remains CHECK_UNAVAILABLE in the returned save context.
$demoPdo = new PDO('sqlite::memory:', null, null, [
    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
]);
$demoPdo->exec('PRAGMA foreign_keys = ON');
$demoPdo->exec('CREATE TABLE NhanVien (MaNV INTEGER PRIMARY KEY, HoTen TEXT NOT NULL)');
$demoPdo->exec(<<<'SQL'
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
$demoPdo->exec("INSERT INTO NhanVien (MaNV, HoTen) VALUES (1, 'NV001'), (23, 'NV023'), (24, 'NV024')");
$uncalibratedChecker = new FaceDuplicateChecker(
    0.95, false, 'buffalo_l', 'max_5x5_cosine', enrollmentCalibrationReport()
);
$demoModel = new FaceEmbeddingModel($demoPdo, $uncalibratedChecker);
$seedContext = [];
$demoModel->replaceByEmployee(1, $personA, enrollmentEmptyRevision($demoModel, 1), $seedContext);

$oldAppEnv = getenv('APP_ENV');
$oldDemoFlag = getenv('AI1_DEMO_ALLOW_UNCHECKED_ENROLLMENT');
$oldServer = $_SERVER;
putenv('APP_ENV=development');
putenv('AI1_DEMO_ALLOW_UNCHECKED_ENROLLMENT=1');
$_SERVER['HTTP_HOST'] = '127.0.0.1:8080';
$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
assertEnrollmentDuplicate(
    FaceDuplicateChecker::isLocalDemoBypassEnabled(),
    'Explicit development mode and loopback request should enable the demo bypass.'
);
$demoContext = [];
$unconfirmedBlocked = false;
try {
    $demoModel->replaceByEmployee(
        23, $personB, enrollmentEmptyRevision($demoModel, 23), $demoContext
    );
} catch (FaceDuplicateCheckException $exception) {
    $unconfirmedBlocked = ($exception->checkResult()['reason'] ?? null) === 'THRESHOLD_NOT_CALIBRATED';
}
assertEnrollmentDuplicate($unconfirmedBlocked, 'Local demo bypass must require an explicit save confirmation.');
assertEnrollmentDuplicate(
    (int)$demoPdo->query('SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV = 23')->fetchColumn() === 0,
    'An unconfirmed demo save must not write any samples.'
);
$demoIds = $demoModel->replaceByEmployee(
    23, $personB, enrollmentEmptyRevision($demoModel, 23), $demoContext, true
);
assertEnrollmentDuplicate(count($demoIds) === 5, 'Demo save must still persist exactly five samples.');
assertEnrollmentDuplicate(
    !empty($demoContext['demo_duplicate_check_skipped'])
        && ($demoContext['duplicate_check']['status'] ?? null) === 'CHECK_UNAVAILABLE'
        && ($demoContext['duplicate_check']['reason'] ?? null) === 'THRESHOLD_NOT_CALIBRATED',
    'The demo save must disclose the unavailable check without reporting a fake CLEAR.'
);
assertEnrollmentDuplicate($demoModel->verifyBatchByEmployee(23, $personB), 'Demo batch read-back must pass.');

$_SERVER['REMOTE_ADDR'] = '192.168.1.20';
assertEnrollmentDuplicate(
    !FaceDuplicateChecker::isLocalDemoBypassEnabled(),
    'A non-loopback client must never receive the demo bypass.'
);
$remoteBlocked = false;
try {
    $demoModel->replaceByEmployee(24, enrollmentDuplicateSamples(M_PI / 4), enrollmentEmptyRevision($demoModel, 24));
} catch (FaceDuplicateCheckException $exception) {
    $remoteBlocked = ($exception->checkResult()['status'] ?? null) === 'CHECK_UNAVAILABLE';
}
assertEnrollmentDuplicate($remoteBlocked, 'A non-loopback save must remain blocked even in development mode.');
$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
putenv('APP_ENV=production');
assertEnrollmentDuplicate(
    !FaceDuplicateChecker::isLocalDemoBypassEnabled(),
    'Production mode must never receive the demo bypass.'
);
$productionBlocked = false;
try {
    $demoModel->replaceByEmployee(24, enrollmentDuplicateSamples(M_PI / 3), enrollmentEmptyRevision($demoModel, 24));
} catch (FaceDuplicateCheckException $exception) {
    $productionBlocked = ($exception->checkResult()['status'] ?? null) === 'CHECK_UNAVAILABLE';
}
assertEnrollmentDuplicate($productionBlocked, 'Production must continue blocking an unavailable duplicate check.');
$countNv024 = (int)$demoPdo->query('SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV = 24')->fetchColumn();
assertEnrollmentDuplicate($countNv024 === 0, 'Blocked production save must leave the target unchanged.');

putenv('APP_ENV=development');
$validatedDemoModel = new FaceEmbeddingModel($demoPdo, $checker);
$duplicateBlocked = false;
try {
    $validatedDemoModel->replaceByEmployee(
        24, $personA, enrollmentEmptyRevision($validatedDemoModel, 24)
    );
} catch (FaceDuplicateCheckException $exception) {
    $duplicateBlocked = ($exception->checkResult()['status'] ?? null) === 'SUSPECTED_DUPLICATE';
}
assertEnrollmentDuplicate($duplicateBlocked, 'Demo mode must still reject a confirmed duplicate.');
assertEnrollmentDuplicate(
    !FaceDuplicateChecker::isDemoBypassableUnavailable([
        'status' => 'CHECK_UNAVAILABLE', 'reason' => 'INVALID_OR_UNREADABLE_EMBEDDING',
    ]),
    'The demo bypass must not ignore invalid gallery embeddings.'
);
$galleryFailureBlocked = false;
$galleryRevision = enrollmentEmptyRevision($demoModel, 24);
$galleryContext = [];
$demoPdo->exec('DROP TABLE FaceEmbedding');
try {
    $demoModel->replaceByEmployee(
        24, enrollmentDuplicateSamples(M_PI / 5), $galleryRevision, $galleryContext, true
    );
} catch (Throwable $exception) {
    $galleryFailureBlocked = true;
}
assertEnrollmentDuplicate($galleryFailureBlocked, 'A database/gallery failure must not be bypassed in local demo mode.');
$controllerSource = file_get_contents(__DIR__ . '/../Controller/FaceEnrollmentController.php');
$completeOffset = strpos((string)$controllerSource, 'public function complete(): void');
$completeBlock = $completeOffset === false ? '' : substr((string)$controllerSource, $completeOffset, 1800);
assertEnrollmentDuplicate(
    str_contains($completeBlock, '$this->requestEmployeeId();')
        && str_contains($completeBlock, '$this->requirePostCsrf()')
        && str_contains($completeBlock, '$_POST[\'confirm_demo_unverified\']')
        && str_contains($completeBlock, '$demoUnverifiedConfirmed'),
    'The save endpoint must retain Admin and POST/CSRF guards.'
);

if ($oldAppEnv === false) {
    putenv('APP_ENV');
} else {
    putenv('APP_ENV=' . $oldAppEnv);
}
if ($oldDemoFlag === false) {
    putenv('AI1_DEMO_ALLOW_UNCHECKED_ENROLLMENT');
} else {
    putenv('AI1_DEMO_ALLOW_UNCHECKED_ENROLLMENT=' . $oldDemoFlag);
}
$_SERVER = $oldServer;

echo "Face enrollment duplicate save PASS\n";
