<?php
declare(strict_types=1);

require_once __DIR__ . '/../Service/ScanHistoryService.php';
require_once __DIR__ . '/../Controller/AttendanceController.php';

// Integration test: use an empty scan history and roll back every test row.
function checkScanHistory(bool $condition, string $message): void
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

set_error_handler(static function (int $severity, string $message, string $file, int $line): bool {
    throw new ErrorException($message, 0, $severity, $file, $line);
});

$db = Database::getConnection();
checkScanHistory((int)$db->query('SELECT COUNT(*) FROM LichSuQuet')->fetchColumn() === 0, 'Refusing to test on populated scan history.');
$model = new ScanHistoryModel();
$service = new ScanHistoryService($model);
$catalog = $db->query('SELECT MaLyDo, MaCode, TenLyDo FROM LoaiLyDoQuet ORDER BY MaLyDo')->fetchAll();
checkScanHistory(count($catalog) === 5, 'Expected five catalog entries.');
$employeeId = (int)$db->query('SELECT MIN(MaNV) FROM NhanVien')->fetchColumn();
$deviceId = (int)$db->query('SELECT MIN(MaTB) FROM ThietBi')->fetchColumn();
$shiftId = (int)$db->query('SELECT MIN(MaCa) FROM CaLamViec')->fetchColumn();
$jpeg = $db->query('SELECT AnhVao FROM ChamCong WHERE AnhVao IS NOT NULL ORDER BY MaCC LIMIT 1')->fetchColumn();
checkScanHistory($employeeId > 0 && $deviceId > 0 && $shiftId > 0 && is_string($jpeg), 'Existing test prerequisites are missing.');
$ids = [];
$db->beginTransaction();

try {
    foreach ($catalog as $entry) {
        $code = (string)$entry['MaCode'];
        $knownEmployee = !in_array($code, ['KHONG_NHAN_DIEN', 'NHIEU_KHUON_MAT'], true);
        $employee = $knownEmployee ? $employeeId : null;
        $faceCount = $code === 'NHIEU_KHUON_MAT' ? 2 : 1;
        $id = $service->recordFailedScan($employee, $deviceId, $shiftId, $code, $jpeg, $faceCount, null, 'scan catalog integration test');
        checkScanHistory(is_int($id), 'Service did not insert ' . $code);
        $ids[$code] = $id;
        $row = $model->findPaginated(['reason' => $code], 20, 0)[0] ?? [];
        checkScanHistory((int)($row['MaLanQuet'] ?? 0) === $id, 'Reason filter returned the wrong record.');
        checkScanHistory((int)$row['MaLyDo'] === (int)$entry['MaLyDo'], 'Reason ID did not match catalog lookup.');
        checkScanHistory($row['MaCode'] === $code && $row['TenLyDo'] === $entry['TenLyDo'], 'Joined catalog labels do not match.');
        checkScanHistory($model->findReasonIdByCode($code) === (int)$entry['MaLyDo'], 'Lookup returned the wrong ID.');
        checkScanHistory($model->countFiltered(['reason' => $code]) === 1, 'Reason count filter failed.');
        checkScanHistory(hash_equals(hash('sha256', $jpeg), hash('sha256', $model->findImageById($id) ?? '')), 'JPEG bytes changed.');
        checkScanHistory($service->recordFailedScan($employee, $deviceId, $shiftId, $code, $jpeg, $faceCount) === null, 'Cooldown failed for ' . $code);
        echo 'REASON_PASS ' . $code . PHP_EOL;
    }

    $knownId = $ids['DA_HOAN_THANH'];
    $statement = $db->prepare('SELECT ThoiGianQuet FROM LichSuQuet WHERE MaLanQuet = :id');
    $statement->execute(['id' => $knownId]);
    $recordTime = new DateTimeImmutable((string)$statement->fetchColumn());
    checkScanHistory($model->existsRecentDuplicate($deviceId, $employeeId, 'DA_HOAN_THANH', $recordTime->modify('+29 seconds')->format('Y-m-d H:i:s')), '29-second cooldown failed.');
    checkScanHistory(!$model->existsRecentDuplicate($deviceId, $employeeId, 'DA_HOAN_THANH', $recordTime->modify('+30 seconds')->format('Y-m-d H:i:s')), '30-second boundary changed.');
    checkScanHistory(!$model->existsRecentDuplicate($deviceId, $employeeId, 'DA_HOAN_THANH', $recordTime->modify('+31 seconds')->format('Y-m-d H:i:s')), '31-second cooldown failed.');

    $age = $db->prepare('UPDATE LichSuQuet SET ThoiGianQuet = DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 31 SECOND) WHERE MaLanQuet = :id');
    $age->execute(['id' => $ids['KHONG_NHAN_DIEN']]);
    checkScanHistory(is_int($service->recordFailedScan(null, $deviceId, $shiftId, 'KHONG_NHAN_DIEN', $jpeg)), 'Service did not allow a new scan after 30 seconds.');
    checkScanHistory(is_int($service->recordFailedScan(null, null, null, 'KHONG_NHAN_DIEN', $jpeg)), 'Nullable tuple insert failed.');
    checkScanHistory($service->recordFailedScan(null, null, null, 'KHONG_NHAN_DIEN', $jpeg) === null, 'Nullable tuple cooldown failed.');
    echo 'COOLDOWN_PASS before/at/after 30 seconds, NULL employee/device' . PHP_EOL;

    $invalidRejected = false;
    try {
        $service->recordFailedScan(null, null, null, 'INVALID_REASON', $jpeg);
    } catch (InvalidArgumentException) {
        $invalidRejected = true;
    }
    checkScanHistory($invalidRejected, 'Unknown code was accepted.');
    $fkRejected = false;
    try {
        $invalidId = (int)$db->query('SELECT MAX(MaLyDo) + 1000 FROM LoaiLyDoQuet')->fetchColumn();
        $statement = $db->prepare('INSERT INTO LichSuQuet (MaLyDo, AnhQuet) VALUES (:reason_id, :image)');
        $statement->bindValue(':reason_id', $invalidId, PDO::PARAM_INT);
        $statement->bindValue(':image', $jpeg, PDO::PARAM_LOB);
        $statement->execute();
    } catch (PDOException $exception) {
        $fkRejected = ($exception->errorInfo[1] ?? null) === 1452;
    }
    checkScanHistory($fkRejected, 'Invalid reason FK was accepted.');
    echo 'VALIDATION_AND_FK_PASS' . PHP_EOL;

    $scanDate = $recordTime->format('Y-m-d');
    $filters = ['date' => $scanDate, 'reason' => 'DA_HOAN_THANH', 'employee_id' => $employeeId, 'device_id' => $deviceId];
    checkScanHistory($model->countFiltered($filters) === 1, 'Combined filters failed.');
    $firstPage = array_column($model->findPaginated([], 2, 0), 'MaLanQuet');
    $secondPage = array_column($model->findPaginated([], 2, 2), 'MaLanQuet');
    checkScanHistory(count($firstPage) === 2 && count($secondPage) === 2 && array_intersect($firstPage, $secondPage) === [], 'Pagination failed.');
    echo 'FILTER_AND_PAGINATION_PASS' . PHP_EOL;

    $_SESSION = ['user_id' => 1, 'ma_vai_tro' => 1];
    $controller = new AttendanceController();
    $render = static function (array $filters = []) use ($controller): array {
        $_GET = $filters + ['action' => 'attendance', 'tab' => 'scan_history'];
        http_response_code(200);
        ob_start();
        try {
            $controller->index();
            return ['status' => http_response_code(), 'html' => ob_get_contents()];
        } finally {
            ob_end_clean();
        }
    };
    $response = $render();
    checkScanHistory($response['status'] === 200, 'Admin scan history controller failed.');
    $html = $response['html'];
    foreach ($catalog as $entry) {
        checkScanHistory(str_contains($html, '<td>' . htmlspecialchars($entry['TenLyDo'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') . '</td>'), 'UI did not render TenLyDo.');
    }
    checkScanHistory(str_contains($html, 'action=scan_history_image'), 'Protected image URL changed.');
    $response = $render(['reason' => 'DA_HOAN_THANH']);
    checkScanHistory($response['status'] === 200 && str_contains($response['html'], '<td>Đã hoàn thành chấm công</td>'), 'Controller reason filter failed.');
    checkScanHistory(!str_contains($response['html'], '<td>Không nhận diện được</td>'), 'Controller reason filter leaked another reason.');
    checkScanHistory($render(['reason' => 'INVALID_REASON'])['status'] === 422, 'Invalid reason filter was not rejected.');
    echo 'CONTROLLER_VIEW_TENLYDO_AND_IMAGE_PASS' . PHP_EOL;
} finally {
    if ($db->inTransaction()) {
        $db->rollBack();
    }
}

checkScanHistory((int)$db->query('SELECT COUNT(*) FROM LichSuQuet')->fetchColumn() === 0, 'Test scan rows were not cleaned.');
echo 'CLEANUP_PASS rollback; AUTO_INCREMENT not reset' . PHP_EOL;
