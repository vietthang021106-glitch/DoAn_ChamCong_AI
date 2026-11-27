<?php
declare(strict_types=1);

require_once __DIR__ . '/AiClient.php';
require_once __DIR__ . '/AttendanceService.php';
require_once __DIR__ . '/CameraFrameClient.php';

/** Record attendance only from a completed, server-side AI1 recognition session. */
class KioskAttendanceService
{
    private const SESSION_CACHE_KEY = 'kiosk_attendance_session_results';
    private const IDEMPOTENCY_TTL_SECONDS = 1800;
    private const IDEMPOTENCY_CACHE_LIMIT = 50;

    private \Closure $readRecognitionSession;
    private \Closure $recordAttendance;
    private \Closure $captureEvidence;

    public function __construct(
        ?callable $readRecognitionSession = null,
        ?callable $recordAttendance = null,
        ?callable $captureEvidence = null
    ) {
        $ai = new AiClient();
        $attendance = new AttendanceService();
        $camera = new CameraFrameClient();
        $this->readRecognitionSession = $readRecognitionSession === null
            ? \Closure::fromCallable([$ai, 'recognitionSessionStatus'])
            : \Closure::fromCallable($readRecognitionSession);
        $this->recordAttendance = $recordAttendance === null
            ? \Closure::fromCallable([$attendance, 'process'])
            : \Closure::fromCallable($recordAttendance);
        $this->captureEvidence = $captureEvidence === null
            ? \Closure::fromCallable([$camera, 'captureJpeg'])
            : \Closure::fromCallable($captureEvidence);
    }

    /**
     * Resolve employee identity from AI service state, never from request data.
     * The PHP session cache makes a retry of the same HTTP request idempotent.
     *
     * @param array<string, mixed> $session Current authenticated PHP session.
     * @return array<string, mixed>
     */
    public function recordFromRecognitionSession(
        string $recognitionSessionId,
        int $deviceId,
        array &$session
    ): array {
        if (!preg_match('/^[a-f0-9]{32}$/D', $recognitionSessionId) || $deviceId < 1) {
            return ['state' => 'RETRY', 'message' => 'Yêu cầu chấm công không hợp lệ.'];
        }

        $cached = $this->cachedResult($recognitionSessionId, $session);
        if ($cached !== null) {
            return $cached;
        }

        try {
            $recognition = ($this->readRecognitionSession)($recognitionSessionId);
        } catch (Throwable $exception) {
            error_log('Kiosk recognition status unavailable: ' . $exception->getMessage());
            return ['state' => 'OFFLINE', 'message' => 'Không kết nối được máy chủ.'];
        }

        if (($recognition['success'] ?? false) !== true) {
            return ['state' => 'RETRY', 'message' => 'Không đọc được kết quả nhận diện. Vui lòng quét lại.'];
        }
        $recognitionState = (string)($recognition['state'] ?? '');
        if (!in_array($recognitionState, ['COMPLETED', 'ABORTED'], true)) {
            return ['state' => 'PROCESSING', 'message' => 'Đang nhận diện...'];
        }

        $recognized = $recognition['result'] ?? null;
        if (!is_array($recognized)) {
            return ['state' => 'RETRY', 'message' => 'Phiên nhận diện không có kết quả hợp lệ.'];
        }
        if ($recognitionState === 'ABORTED' || ($recognized['recognized'] ?? false) !== true) {
            if (($recognized['reason'] ?? null) === 'UNKNOWN') {
                return ['state' => 'UNKNOWN', 'message' => 'Không nhận diện được. Vui lòng thử lại.'];
            }
            return [
                'state' => 'RETRY',
                'message' => $this->retryMessage((string)($recognized['retry_reason'] ?? '')),
            ];
        }

        $employeeId = filter_var(
            $recognized['ma_nv'] ?? null,
            FILTER_VALIDATE_INT,
            ['options' => ['min_range' => 1]]
        );
        if (!is_int($employeeId)) {
            return ['state' => 'RETRY', 'message' => 'Kết quả nhận diện không hợp lệ. Vui lòng quét lại.'];
        }

        // Capture evidence from the already-owned camera singleton immediately
        // before recording; this does not open another camera or trust a client image.
        try {
            $evidenceJpeg = ($this->captureEvidence)();
            if (!is_string($evidenceJpeg) || $evidenceJpeg === '') {
                $outcome = [
                    'state' => 'OFFLINE',
                    'code' => 'CAMERA_SOURCE_UNAVAILABLE',
                    'message' => 'Camera offline: không lấy được ảnh bằng chứng nên chưa ghi chấm công.',
                    'employee_id' => $employeeId,
                    'employee_name' => (string)($recognized['ho_ten'] ?? ''),
                ];
                $this->rememberResult($recognitionSessionId, $outcome, $session);
                return $outcome;
            }
            $attendanceResult = ($this->recordAttendance)($employeeId, $deviceId, $evidenceJpeg);
        } catch (Throwable $exception) {
            error_log('Kiosk attendance processing failed: ' . $exception->getMessage());
            $outcome = [
                'state' => 'RETRY',
                'message' => 'Chưa ghi được chấm công. Vui lòng quét lại.',
                'employee_id' => $employeeId,
                'employee_name' => (string)($recognized['ho_ten'] ?? ''),
            ];
            $this->rememberResult($recognitionSessionId, $outcome, $session);
            return $outcome;
        }

        $action = (string)($attendanceResult['action'] ?? 'error');
        if (($attendanceResult['status'] ?? null) === 'success' && $action === 'checkin') {
            $outcome = $this->attendanceOutcome('SUCCESS', 'checkin', $recognized, $attendanceResult);
        } elseif (($attendanceResult['status'] ?? null) === 'success' && $action === 'checkout') {
            $outcome = $this->attendanceOutcome('SUCCESS', 'checkout', $recognized, $attendanceResult);
        } elseif (($attendanceResult['status'] ?? null) === 'success' && $action === 'completed') {
            $outcome = [
                'state' => 'ALREADY_COMPLETED',
                'message' => 'Đã hoàn tất chấm công hôm nay.',
                'employee_id' => $employeeId,
                'employee_name' => (string)($recognized['ho_ten'] ?? ''),
            ];
        } else {
            $outcome = [
                'state' => 'RETRY',
                'message' => $this->safeAttendanceError(
                    (string)($attendanceResult['message'] ?? '')
                ),
                'employee_id' => $employeeId,
                'employee_name' => (string)($recognized['ho_ten'] ?? ''),
            ];
        }

        // Cache every completed attendance attempt, including failures. A retry
        // with this recognition session must never turn a successful check-in
        // into an accidental check-out.
        $this->rememberResult($recognitionSessionId, $outcome, $session);
        return $outcome;
    }

    private function attendanceOutcome(string $state, string $action, array $recognized, array $attendance): array
    {
        $now = new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh'));
        return [
            'state' => $state,
            'action' => $action,
            'message' => $action === 'checkin' ? 'CHẤM CÔNG VÀO THÀNH CÔNG' : 'CHẤM CÔNG RA THÀNH CÔNG',
            'employee_id' => (int)$recognized['ma_nv'],
            'employee_name' => (string)($recognized['ho_ten'] ?? ''),
            'time' => $now->format('H:i:s'),
            'shift_name' => (string)($attendance['TenCa'] ?? ''),
        ];
    }

    private function safeAttendanceError(string $message): string
    {
        $normalized = function_exists('mb_strtolower')
            ? mb_strtolower($message, 'UTF-8')
            : strtolower($message);
        if (str_contains($normalized, 'chưa được phân ca')
            || str_contains($normalized, 'không có ca làm hợp lệ')) {
            return 'Bạn chưa được phân ca hôm nay. Vui lòng liên hệ quản lý.';
        }
        if (str_contains($normalized, 'chưa đến giờ chấm công')) {
            return 'Chưa đến giờ chấm công. Vui lòng chờ đến giờ quy định.';
        }
        if (str_contains($normalized, 'đã chấm công đủ lượt')
            || str_contains($normalized, 'đã hoàn tất chấm công')) {
            return 'Bạn đã chấm công đủ lượt hôm nay.';
        }
        return 'Chấm công chưa được ghi nhận. Vui lòng thử lại hoặc liên hệ quản lý.';
    }

    private function retryMessage(string $reason): string
    {
        return match ($reason) {
            'NO_FACE' => 'Không thấy khuôn mặt. Hãy nhìn vào camera và thử lại.',
            'MULTIPLE_FACES' => 'Chỉ để một người trước camera rồi thử lại.',
            'BLUR' => 'Ảnh chưa rõ. Hãy đứng yên và thử lại.',
            'STALE_FRAME' => 'Camera chưa gửi được khung hình mới. Vui lòng thử lại.',
            'CAMERA_TIMEOUT', 'CAMERA_UNAVAILABLE' => 'Không nhận được hình từ camera. Vui lòng thử lại.',
            'INCONSISTENT_FACES' => 'Ba khung hình chưa nhất quán. Vui lòng thử lại.',
            'MODEL_UNAVAILABLE', 'GALLERY_UNAVAILABLE' => 'Dịch vụ nhận diện chưa sẵn sàng. Vui lòng báo quản lý.',
            default => 'Chưa nhận diện được ổn định. Vui lòng nhìn vào camera và thử lại.',
        };
    }

    private function cachedResult(string $recognitionSessionId, array &$session): ?array
    {
        $cache = $session[self::SESSION_CACHE_KEY] ?? [];
        if (!is_array($cache)) {
            $cache = [];
        }
        $this->pruneCache($cache);
        $session[self::SESSION_CACHE_KEY] = $cache;
        $entry = $cache[$recognitionSessionId] ?? null;
        return is_array($entry['result'] ?? null) ? $entry['result'] : null;
    }

    private function rememberResult(string $recognitionSessionId, array $result, array &$session): void
    {
        $cache = $session[self::SESSION_CACHE_KEY] ?? [];
        if (!is_array($cache)) {
            $cache = [];
        }
        $this->pruneCache($cache);
        $cache[$recognitionSessionId] = ['created_at' => time(), 'result' => $result];
        while (count($cache) > self::IDEMPOTENCY_CACHE_LIMIT) {
            $oldest = array_key_first($cache);
            if ($oldest === null) {
                break;
            }
            unset($cache[$oldest]);
        }
        $session[self::SESSION_CACHE_KEY] = $cache;
    }

    private function pruneCache(array &$cache): void
    {
        $cutoff = time() - self::IDEMPOTENCY_TTL_SECONDS;
        foreach ($cache as $sessionId => $entry) {
            if (!is_array($entry) || (int)($entry['created_at'] ?? 0) < $cutoff) {
                unset($cache[$sessionId]);
            }
        }
    }
}
