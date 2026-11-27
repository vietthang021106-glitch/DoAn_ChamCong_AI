<?php
declare(strict_types=1);

require_once __DIR__ . '/../Service/AiClient.php';
require_once __DIR__ . '/../Model/DeviceIntegrationTestModel.php';

final class DeviceApiController
{
    private const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

    /** Public connectivity probe for devices such as ESP32-CAM. */
    public function ping(): void
    {
        http_response_code(200);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store');
        echo json_encode(
            ['ok' => true, 'message' => 'Server connected'],
            JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE
        );
        exit;
    }

    /** Receive one raw JPEG solely for ESP32-CAM connectivity testing. */
    public function cameraTestUpload(): void
    {
        $image = $this->readValidatedJpeg();

        $directory = dirname(__DIR__) . '/storage/device_test';
        if (!is_dir($directory) && !mkdir($directory, 0775, true) && !is_dir($directory)) {
            $this->jsonResponse(['ok' => false, 'message' => 'Cannot create test-image storage.'], 500);
        }
        $filename = 'esp32cam_' . (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))->format('Ymd_His_v') . '.jpg';
        $imagePath = $directory . '/' . $filename;
        $bytesWritten = file_put_contents($imagePath, $image, LOCK_EX);
        if ($bytesWritten !== strlen($image)) {
            $this->jsonResponse(['ok' => false, 'message' => 'Cannot save JPEG test image.'], 500);
        }

        try {
            // A camera connectivity sample is not attendance evidence and must
            // never be attributed to a real employee.
            $testId = (new DeviceIntegrationTestModel())->saveCameraTest(null, $filename, $image);
        } catch (Throwable $exception) {
            if (is_file($imagePath)) {
                unlink($imagePath);
            }
            error_log('Device camera-test database write failed: ' . $exception->getMessage());
            $this->jsonResponse(['ok' => false, 'message' => 'Cannot save camera test data.', 'db_saved' => false], 503);
        }

        $this->jsonResponse([
            'ok' => true,
            'message' => 'Camera test saved',
            'ma_test' => $testId,
            'loai_du_lieu' => 'CAMERA',
            'ma_nv' => null,
            'bytes' => strlen($image),
            'db_saved' => true,
        ]);
    }

    /** Send a device JPEG to the loopback AI recognition service without recording attendance. */
    public function faceTest(): void
    {
        $image = $this->readValidatedJpeg();

        try {
            $result = (new AiClient())->recognizeJpeg($image);
        } catch (Throwable $exception) {
            error_log('Device face-test AI request failed: ' . $exception->getMessage());
            $this->jsonResponse(['ok' => false, 'message' => 'Face recognition service is unavailable.'], 503);
        }

        if (($result['reason'] ?? null) === 'THREE_FRESH_SNAPSHOTS_REQUIRED') {
            $this->jsonResponse([
                'ok' => false,
                'recognized' => false,
                'reason' => 'THREE_FRESH_SNAPSHOTS_REQUIRED',
                'message' => 'Ảnh tĩnh chỉ dùng kiểm tra truyền ảnh; nhận diện cần ba snapshot mới từ camera chung.',
            ], 409);
        }

        if (($result['success'] ?? false) !== true) {
            $this->jsonResponse(['ok' => false, 'message' => 'Face recognition service could not process the image.'], 503);
        }

        if (($result['recognized'] ?? false) === true) {
            $employeeId = filter_var($result['ma_nv'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
            $confidence = $result['confidence'] ?? null;
            if ($employeeId === false || !is_numeric($confidence)) {
                $this->jsonResponse(['ok' => false, 'message' => 'Face recognition service returned an invalid match.'], 503);
            }
            $this->jsonResponse([
                'ok' => true,
                'recognized' => true,
                'ma_nv' => (int)$employeeId,
                'confidence' => (float)$confidence,
            ]);
        }

        $reason = match ($result['reason'] ?? null) {
            'NO_FACE' => 'KHONG_CO_KHUON_MAT',
            'MULTIPLE_FACES' => 'NHIEU_KHUON_MAT',
            default => 'KHONG_NHAN_DIEN',
        };
        $this->jsonResponse(['ok' => true, 'recognized' => false, 'reason' => $reason]);
    }

    /** Store one ESP8266/MAX30102 test reading only in the isolated integration-test table. */
    public function healthTest(): void
    {
        if (!$this->isJsonContentType()) {
            $this->jsonResponse(['ok' => false, 'message' => 'Content-Type must be application/json.'], 415);
        }

        try {
            $payload = json_decode((string)file_get_contents('php://input'), true, 16, JSON_THROW_ON_ERROR);
        } catch (JsonException) {
            $this->jsonResponse(['ok' => false, 'message' => 'Request body must be valid JSON.'], 400);
        }
        if (!is_array($payload)) {
            $this->jsonResponse(['ok' => false, 'message' => 'Request body must be a JSON object.'], 400);
        }
        foreach (['ma_nv', 'nhip_tim', 'spo2'] as $field) {
            if (!array_key_exists($field, $payload)) {
                $this->jsonResponse(['ok' => false, 'message' => "Missing required field: {$field}."], 400);
            }
        }

        $employeeId = $this->positiveInteger($payload['ma_nv']);
        if ($employeeId === null) {
            $this->jsonResponse(['ok' => false, 'message' => 'ma_nv must be a positive integer.'], 422);
        }
        $heartRate = $this->positiveInteger($payload['nhip_tim']);
        if ($heartRate === null || $heartRate < 20 || $heartRate > 250) {
            $this->jsonResponse(['ok' => false, 'message' => 'nhip_tim must be an integer from 20 to 250.'], 422);
        }
        $spo2 = $this->decimalNumber($payload['spo2']);
        if ($spo2 === null || $spo2 < 0 || $spo2 > 100) {
            $this->jsonResponse(['ok' => false, 'message' => 'spo2 must be a number from 0 to 100.'], 422);
        }

        try {
            $testId = (new DeviceIntegrationTestModel())->saveHealthTest($employeeId, $heartRate, $spo2);
        } catch (Throwable $exception) {
            error_log('Device health-test write failed: ' . $exception->getMessage());
            $this->jsonResponse(['ok' => false, 'message' => 'Cannot save health data.'], 503);
        }

        $this->jsonResponse([
            'ok' => true,
            'message' => 'Health test saved',
            'ma_test' => $testId,
            'loai_du_lieu' => 'HEALTH',
            'ma_nv' => $employeeId,
            'nhip_tim' => $heartRate,
            'spo2' => $spo2,
            'db_saved' => true,
        ]);
    }

    /** Send the most recently received ESP32-CAM test image. */
    public function latestCameraTestImage(): void
    {
        $files = glob(dirname(__DIR__) . '/storage/device_test/esp32cam_*.jpg') ?: [];
        $files = array_values(array_filter($files, 'is_file'));
        if ($files === []) {
            $this->jsonResponse(['ok' => false, 'message' => 'No test image has been received.'], 404);
        }

        usort($files, static fn (string $left, string $right): int => filemtime($right) <=> filemtime($left));
        $image = file_get_contents($files[0]);
        if (!is_string($image) || !$this->isValidJpeg($image)) {
            $this->jsonResponse(['ok' => false, 'message' => 'Latest test image is unavailable.'], 500);
        }

        http_response_code(200);
        header('Content-Type: image/jpeg');
        header('Content-Length: ' . strlen($image));
        header('Cache-Control: no-store');
        header('X-Content-Type-Options: nosniff');
        echo $image;
        exit;
    }

    /** Send the newest camera-test JPEG stored in the integration-test database. */
    public function latestCameraTestImageFromDatabase(): void
    {
        try {
            $record = (new DeviceIntegrationTestModel())->getLatestCamera();
        } catch (Throwable $exception) {
            error_log('Device camera-test latest-db read failed: ' . $exception->getMessage());
            $this->jsonResponse(['ok' => false, 'message' => 'Cannot read camera test data.'], 503);
        }
        if ($record === null || !is_string($record['Anh'] ?? null) || !$this->isValidJpeg($record['Anh'])) {
            $this->jsonResponse(['ok' => false, 'message' => 'No valid camera test image has been saved.'], 404);
        }

        $image = $record['Anh'];
        http_response_code(200);
        header('Content-Type: image/jpeg');
        header('Content-Length: ' . strlen($image));
        header('Cache-Control: no-store');
        header('X-Content-Type-Options: nosniff');
        echo $image;
        exit;
    }

    /** Send one camera-test JPEG selected by its DeviceIntegrationTest primary key. */
    public function cameraTestImageById(): void
    {
        $testId = $this->positiveInteger($_GET['id'] ?? null);
        if ($testId === null) {
            $this->jsonResponse(['ok' => false, 'message' => 'Invalid id'], 400);
        }

        try {
            $record = (new DeviceIntegrationTestModel())->getCameraById($testId);
        } catch (Throwable $exception) {
            error_log('Device camera-test image-by-id read failed: ' . $exception->getMessage());
            $this->jsonResponse(['ok' => false, 'message' => 'Camera image not found'], 404);
        }
        if ($record === null || !is_string($record['Anh'] ?? null)) {
            $this->jsonResponse(['ok' => false, 'message' => 'Camera image not found'], 404);
        }

        $image = $record['Anh'];
        http_response_code(200);
        header('Content-Type: image/jpeg');
        header('Content-Length: ' . strlen($image));
        header('Cache-Control: no-store');
        header('X-Content-Type-Options: nosniff');
        echo $image;
        exit;
    }

    /** Return integration-test metadata only; image bytes are never placed in JSON. */
    public function integrationTestIndex(): void
    {
        try {
            $records = (new DeviceIntegrationTestModel())->getLatestRecords();
        } catch (Throwable $exception) {
            error_log('Device integration-test listing failed: ' . $exception->getMessage());
            $this->jsonResponse(['ok' => false, 'message' => 'Cannot read integration test data.'], 503);
        }

        $this->jsonResponse($records);
    }

    private function isJpegContentType(): bool
    {
        $contentType = strtolower(trim(explode(';', (string)($_SERVER['CONTENT_TYPE'] ?? ''))[0]));

        return $contentType === 'image/jpeg';
    }

    private function isJsonContentType(): bool
    {
        $contentType = strtolower(trim(explode(';', (string)($_SERVER['CONTENT_TYPE'] ?? ''))[0]));

        return $contentType === 'application/json';
    }

    private function positiveInteger(mixed $value): ?int
    {
        if (is_int($value)) {
            return $value > 0 ? $value : null;
        }
        if (!is_string($value) || !preg_match('/^[1-9][0-9]*$/', $value)) {
            return null;
        }
        $parsed = filter_var($value, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);

        return is_int($parsed) ? $parsed : null;
    }

    private function decimalNumber(mixed $value): ?float
    {
        if (!is_int($value) && !is_float($value) && !is_string($value)) {
            return null;
        }
        if (is_string($value) && !preg_match('/^[+-]?(?:\d+\.?\d*|\.\d+)$/', $value)) {
            return null;
        }
        $parsed = (float)$value;

        return is_finite($parsed) ? $parsed : null;
    }

    private function readValidatedJpeg(): string
    {
        if (!$this->isJpegContentType()) {
            $this->jsonResponse(['ok' => false, 'message' => 'Content-Type must be image/jpeg.'], 415);
        }

        $image = file_get_contents('php://input', false, null, 0, self::MAX_IMAGE_BYTES + 1);
        if (!is_string($image) || $image === '') {
            $this->jsonResponse(['ok' => false, 'message' => 'JPEG body is required.'], 400);
        }
        if (strlen($image) > self::MAX_IMAGE_BYTES) {
            $this->jsonResponse(['ok' => false, 'message' => 'JPEG must not exceed 2 MB.'], 413);
        }
        if (!$this->isValidJpeg($image)) {
            $this->jsonResponse(['ok' => false, 'message' => 'Request body is not a valid JPEG image.'], 422);
        }

        return $image;
    }

    private function isValidJpeg(string $image): bool
    {
        $info = @getimagesizefromstring($image);

        return (new finfo(FILEINFO_MIME_TYPE))->buffer($image) === 'image/jpeg'
            && is_array($info)
            && ($info['mime'] ?? '') === 'image/jpeg';
    }

    private function jsonResponse(array $payload, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
        exit;
    }
}
