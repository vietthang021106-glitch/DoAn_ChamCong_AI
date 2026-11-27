<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/DeviceModel.php';
require_once __DIR__ . '/../Service/AttendanceCameraBinding.php';
require_once __DIR__ . '/../Security/CsrfToken.php';
require_once __DIR__ . '/../Service/KioskAttendanceService.php';
require_once __DIR__ . '/../Service/CameraFrameClient.php';
require_once __DIR__ . '/AuthController.php';

final class KioskController
{
    private const RECOGNITION_SESSION_KEY = 'kiosk_recognition_sessions';

    private DeviceModel $devices;
    private KioskAttendanceService $attendance;
    private AiClient $ai;

    public function __construct(?DeviceModel $devices = null, ?KioskAttendanceService $attendance = null)
    {
        $this->devices = $devices ?? new DeviceModel();
        $this->attendance = $attendance ?? new KioskAttendanceService();
        $this->ai = new AiClient();
    }

    /** Start a kiosk-owned AI session and bind its opaque ID to this admin session. */
    public function startRecognition(): void
    {
        AuthController::requireAdmin();
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            $this->jsonResponse(['success' => false, 'message' => 'Chỉ chấp nhận POST.'], 405);
        }
        if (!CsrfToken::isValid()) {
            $this->jsonResponse(['success' => false, 'message' => 'Phiên đã hết hạn. Tải lại màn hình chấm công.'], 400);
        }

        // Do not create an attendance session while the shared camera owner has
        // no fresh JPEG. This checks the existing Flask singleton only.
        if ((new CameraFrameClient())->captureSnapshot() === null) {
            $this->jsonResponse([
                'success' => false,
                'code' => 'CAMERA_SOURCE_UNAVAILABLE',
                'message' => 'Camera offline: không nhận được frame từ app.py tại 127.0.0.1:5000. Chấm công đã tạm dừng.',
            ], 503);
        }

        try {
            $result = $this->ai->startRecognitionSession();
        } catch (Throwable $exception) {
            error_log('Attendance terminal could not start recognition: ' . $exception->getMessage());
            $this->jsonResponse([
                'success' => false,
                'code' => 'AI1_UNAVAILABLE',
                'message' => 'Không kết nối được AI1 tại 127.0.0.1:5001. Hãy chạy python ai_service.py.',
            ], 503);
        }
        $sessionId = strtolower((string)($result['session_id'] ?? ''));
        if (($result['success'] ?? false) !== true || !preg_match('/^[a-f0-9]{32}$/D', $sessionId)) {
            $status = !empty($result['busy']) ? 409 : 503;
            $this->jsonResponse([
                'success' => false,
                'code' => 'AI1_UNAVAILABLE',
                'busy' => !empty($result['busy']),
                'message' => !empty($result['busy'])
                    ? 'Đang có một lượt quét khác. Vui lòng chờ.'
                    : 'AI1 chưa sẵn sàng tại 127.0.0.1:5001. Kiểm tra ai_service.py và model buffalo_l.',
            ], $status);
        }

        $issued = $_SESSION[self::RECOGNITION_SESSION_KEY] ?? [];
        if (!is_array($issued)) {
            $issued = [];
        }
        $this->pruneIssuedSessions($issued);
        $issued[$sessionId] = time();
        $_SESSION[self::RECOGNITION_SESSION_KEY] = $issued;
        $this->jsonResponse([
            'success' => true,
            'session_id' => $sessionId,
            'state' => $result['state'] ?? 'CAPTURING',
        ], 202);
    }

    /** Render a separate, admin-authorized attendance terminal without admin navigation. */
    public function index(): void
    {
        AuthController::requireAdmin();

        $device = null;
        $deviceError = null;
        try {
            $configured = $this->devices->findAll();
            $boundDeviceId = AttendanceCameraBinding::deviceId($configured);
            $requestedId = trim((string)($_GET['device_id'] ?? ''));
            if ($requestedId !== '') {
                $deviceId = filter_var($requestedId, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
                if (!is_int($deviceId)) {
                    $deviceError = 'Thiết bị chấm công không hợp lệ.';
                } elseif ($boundDeviceId === null) {
                    $deviceError = 'Camera hiện tại chưa được gán duy nhất cho một thiết bị chấm công.';
                } elseif ($deviceId !== $boundDeviceId) {
                    $deviceError = 'Thiết bị này chưa được gán với nguồn camera AI1 hiện tại.';
                } else {
                    $device = $this->devices->findById($deviceId);
                    if ($device === null) {
                        $deviceError = 'Không tìm thấy thiết bị chấm công.';
                    }
                }
            } elseif ($boundDeviceId === null) {
                if ($configured === []) {
                    $deviceError = 'Chưa có thiết bị chấm công được khai báo.';
                } else {
                    $deviceError = 'Camera hiện tại chưa được gán duy nhất cho một thiết bị chấm công.';
                }
            } else {
                $device = $this->devices->findById($boundDeviceId);
            }
        } catch (Throwable $exception) {
            error_log('Attendance terminal device lookup failed: ' . $exception->getMessage());
            $deviceError = 'Không thể kết nối cơ sở dữ liệu để xác định thiết bị.';
        }

        header('Cache-Control: private, no-store');
        header('X-Frame-Options: DENY');
        $pageTitle = 'Màn hình chấm công';
        $deviceId = $device === null ? null : (int)$device['MaTB'];
        $deviceLabel = $device === null
            ? ''
            : 'TB' . str_pad((string)$deviceId, 3, '0', STR_PAD_LEFT);
        $csrfToken = CsrfToken::token();
        require __DIR__ . '/../View/man_hinh_cham_cong.php';
    }

    /** Record only after resolving the employee from a completed internal AI session. */
    public function recordAttendance(): void
    {
        AuthController::requireAdmin();
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            $this->jsonResponse(['state' => 'RETRY', 'message' => 'Chỉ chấp nhận POST.'], 405);
        }
        if (!CsrfToken::isValid()) {
            $this->jsonResponse(['state' => 'RETRY', 'message' => 'Phiên đã hết hạn. Tải lại màn hình chấm công.'], 400);
        }

        $rawSessionId = $_POST['session_id'] ?? null;
        $sessionId = is_string($rawSessionId) ? strtolower(trim($rawSessionId)) : '';
        if (!preg_match('/^[a-f0-9]{32}$/D', $sessionId)) {
            $this->jsonResponse(['state' => 'RETRY', 'message' => 'Phiên nhận diện không hợp lệ. Vui lòng quét lại.'], 400);
        }
        $issued = $_SESSION[self::RECOGNITION_SESSION_KEY] ?? [];
        if (!is_array($issued)) {
            $issued = [];
        }
        $this->pruneIssuedSessions($issued);
        $_SESSION[self::RECOGNITION_SESSION_KEY] = $issued;
        if (!array_key_exists($sessionId, $issued)) {
            $this->jsonResponse(['state' => 'RETRY', 'message' => 'Phiên quét không thuộc màn hình chấm công này. Hãy quét lại.'], 403);
        }

        $rawDeviceId = $_POST['device_id'] ?? null;
        $deviceId = filter_var($rawDeviceId, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if (!is_int($deviceId)) {
            $this->jsonResponse(['state' => 'RETRY', 'message' => 'Thiết bị chấm công không hợp lệ.'], 400);
        }
        try {
            if ($this->devices->findById($deviceId) === null) {
                $this->jsonResponse([
                    'state' => 'RETRY',
                    'message' => 'Không tìm thấy thiết bị chấm công.',
                    ...$this->recognizedEmployeeForSession($sessionId),
                ], 404);
            }
            $result = $this->attendance->recordFromRecognitionSession($sessionId, $deviceId, $_SESSION);
        } catch (Throwable $exception) {
            error_log('Attendance terminal request failed: ' . $exception->getMessage());
            $this->jsonResponse([
                'state' => 'OFFLINE',
                'message' => 'Không kết nối được máy chủ.',
                ...$this->recognizedEmployeeForSession($sessionId),
            ], 503);
        }

        $status = ($result['state'] ?? '') === 'OFFLINE' ? 503
            : (($result['state'] ?? '') === 'PROCESSING' ? 202 : 200);
        $this->jsonResponse($result, $status);
    }

    /** Include a name only when AI1 has already completed and verified this session. */
    private function recognizedEmployeeForSession(string $sessionId): array
    {
        try {
            $session = $this->ai->recognitionSessionStatus($sessionId);
            $result = $session['result'] ?? null;
            if (($session['success'] ?? false) !== true
                || ($session['state'] ?? '') !== 'COMPLETED'
                || !is_array($result)
                || ($result['recognized'] ?? false) !== true) {
                return [];
            }

            $employeeId = filter_var(
                $result['ma_nv'] ?? null,
                FILTER_VALIDATE_INT,
                ['options' => ['min_range' => 1]]
            );
            if (!is_int($employeeId)) {
                return [];
            }

            return [
                'employee_id' => $employeeId,
                'employee_name' => is_string($result['ho_ten'] ?? null) ? $result['ho_ten'] : '',
            ];
        } catch (Throwable) {
            return [];
        }
    }

    private function pruneIssuedSessions(array &$issued): void
    {
        $cutoff = time() - 1800;
        foreach ($issued as $sessionId => $createdAt) {
            if (!is_string($sessionId) || !preg_match('/^[a-f0-9]{32}$/D', $sessionId)
                || !is_numeric($createdAt) || (int)$createdAt < $cutoff) {
                unset($issued[$sessionId]);
            }
        }
        while (count($issued) > 50) {
            $oldest = array_key_first($issued);
            if ($oldest === null) {
                break;
            }
            unset($issued[$oldest]);
        }
    }

    private function jsonResponse(array $payload, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: private, no-store');
        header('X-Content-Type-Options: nosniff');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
        exit;
    }
}
