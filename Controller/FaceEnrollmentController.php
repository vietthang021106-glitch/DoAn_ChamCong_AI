<?php
declare(strict_types=1);

require_once __DIR__ . '/AuthController.php';
require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';
require_once __DIR__ . '/../Security/CsrfToken.php';
require_once __DIR__ . '/../Service/AiClient.php';
require_once __DIR__ . '/../Service/CameraFrameClient.php';
require_once __DIR__ . '/../Service/EnrollmentCaptureState.php';
require_once __DIR__ . '/../Model/DeviceModel.php';
require_once __DIR__ . '/../Service/AttendanceCameraBinding.php';

final class FaceEnrollmentController
{
    private const POSES = ['frontal', 'left', 'right', 'up', 'down'];
    private const SESSION_KEY = 'face_enrollment_batches';
    private const SESSION_TTL = 600;
    private const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

    private EmployeeModel $employees;
    private FaceEmbeddingModel $faceEmbeddings;
    private AiClient $ai;
    private CameraFrameClient $camera;

    public function __construct()
    {
        $this->employees = new EmployeeModel();
        $this->faceEmbeddings = new FaceEmbeddingModel();
        $this->ai = new AiClient();
        $this->camera = new CameraFrameClient();
    }

    /** Chuyển tiếp frame JPEG từ camera singleton hiện có cho giao diện enrollment. */
    public function frame(): void
    {
        AuthController::requireAdmin();
        $jpeg = $this->camera->captureJpeg();
        if (!is_string($jpeg) || strlen($jpeg) > self::MAX_IMAGE_BYTES) {
            $this->jsonResponse([
                'success' => false,
                'code' => 'CAMERA_SOURCE_UNAVAILABLE',
                'message' => 'Không nhận được hình từ camera. Hãy chạy app.py ở cổng 5000 và kiểm tra nguồn camera.',
            ], 503);
        }

        header('Content-Type: image/jpeg');
        header('Content-Length: ' . strlen($jpeg));
        header('Cache-Control: private, no-store');
        header('X-Content-Type-Options: nosniff');
        echo $jpeg;
    }

    /** Tạo batch enrollment 5 pose trong session; chưa ghi dữ liệu xuống MariaDB. */
    public function start(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }

        $mode = strtoupper(trim((string)($_POST['mode'] ?? 'AUTO')));
        if (!in_array($mode, ['AUTO', 'MANUAL'], true)) {
            $this->jsonResponse(['success' => false, 'message' => 'Chế độ đăng ký không hợp lệ.'], 400);
            return;
        }
        try {
            $devices = (new DeviceModel())->findAll();
            $boundDeviceId = AttendanceCameraBinding::deviceId($devices);
        } catch (Throwable $exception) {
            error_log('Face enrollment device lookup failed.');
            $this->jsonResponse(['success' => false, 'message' => 'Không thể xác định thiết bị camera.'], 503);
            return;
        }
        $requestedDeviceId = filter_var($_POST['device_id'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if ($boundDeviceId === null || !is_int($requestedDeviceId) || $requestedDeviceId !== $boundDeviceId) {
            $this->jsonResponse([
                'success' => false,
                'message' => 'Camera AI1 chưa được gán đúng cho một thiết bị chấm công. Không thể bắt đầu đăng ký.',
            ], 409);
            return;
        }

        foreach (($_SESSION[self::SESSION_KEY] ?? []) as $otherEmployeeId => $existingBatch) {
            if (!is_array($existingBatch) || time() - (int)($existingBatch['started_at'] ?? 0) > self::SESSION_TTL) {
                continue;
            }
            if (in_array($existingBatch['state'] ?? '', ['ENROLLING', 'AWAITING_CONFIRMATION'], true)) {
                $this->jsonResponse([
                    'success' => false,
                    'busy' => true,
                    'message' => 'Camera đang được sử dụng bởi một phiên đăng ký khác. Hãy hoàn tất hoặc hủy phiên đó trước.',
                ], 409);
                return;
            }
        }

        try {
            $employee = $this->employees->findById($employeeId);
            if ($employee === null) {
                $this->jsonResponse(['success' => false, 'message' => 'Không tìm thấy nhân viên.'], 404);
                return;
            }
            // Verify the existing camera owner first. This only reads one frame
            // from CameraFrameClient; it never opens a second VideoCapture.
            if ($this->camera->captureSnapshot() === null) {
                $this->jsonResponse([
                    'success' => false,
                    'code' => 'CAMERA_SOURCE_UNAVAILABLE',
                    'message' => 'Không nhận được frame từ camera AI1 tại 127.0.0.1:5000. Hãy chạy app.py và kiểm tra camera.',
                ], 503);
                return;
            }

            try {
                $health = $this->ai->health();
            } catch (Throwable $exception) {
                error_log('Face enrollment AI1 health check failed: ' . $exception->getMessage());
                $this->jsonResponse([
                    'success' => false,
                    'code' => 'AI1_UNAVAILABLE',
                    'message' => 'Không kết nối được AI1 tại 127.0.0.1:5001. Hãy chạy python ai_service.py.',
                ], 503);
                return;
            }
            if (empty($health['model_ready'])) {
                $this->jsonResponse([
                    'success' => false,
                    'code' => 'AI1_MODEL_UNAVAILABLE',
                    'message' => 'Dịch vụ AI1 đang chạy nhưng model buffalo_l chưa sẵn sàng.',
                ], 503);
                return;
            }

            $galleryState = $this->faceEmbeddings->enrollmentRevision($employeeId);
            $existingCount = $galleryState['count'];
            $state = EnrollmentCaptureState::create() + [
                'started_at' => time(),
                'replace_existing' => $existingCount > 0,
                'expected_revision' => $galleryState['revision'],
                'device_id' => $boundDeviceId,
                'mode' => $mode,
                'state' => 'ENROLLING',
                'employee_name' => (string)($employee['HoTen'] ?? ''),
            ];
            if ($mode === 'AUTO') {
                $aiSession = $this->ai->startEnrollmentSession();
                $aiSessionId = strtolower((string)($aiSession['session_id'] ?? ''));
                if (($aiSession['success'] ?? false) !== true
                    || !preg_match('/^[a-f0-9]{32}$/D', $aiSessionId)) {
                    $this->jsonResponse([
                        'success' => false,
                        'busy' => !empty($aiSession['busy']),
                        'message' => (string)($aiSession['message'] ?? 'Không thể khởi động AUTO Enrollment.'),
                    ], !empty($aiSession['busy']) ? 409 : 503);
                    return;
                }
                $state['ai_session_id'] = $aiSessionId;
                $state['state'] = 'ENROLLING';
            } else {
                $aiSession = $this->ai->startManualEnrollmentLock();
                $aiSessionId = strtolower((string)($aiSession['session_id'] ?? ''));
                if (($aiSession['success'] ?? false) !== true
                    || !preg_match('/^[a-f0-9]{32}$/D', $aiSessionId)) {
                    $this->jsonResponse([
                        'success' => false,
                        'busy' => !empty($aiSession['busy']),
                        'message' => (string)($aiSession['message'] ?? 'Không thể khóa camera cho đăng ký MANUAL.'),
                    ], !empty($aiSession['busy']) ? 409 : 503);
                    return;
                }
                $state['ai_session_id'] = $aiSessionId;
            }
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            $this->jsonResponse([
                'success' => true,
                'captured' => 0,
                'total' => count(self::POSES),
                'current_pose_index' => 0,
                'stable_frame_count' => 0,
                'stable_frames_required' => $mode === 'AUTO' ? 5 : EnrollmentCaptureState::STABLE_FRAMES_REQUIRED,
                'progress' => '0/5',
                'replace_existing' => $existingCount > 0,
                'mode' => $mode,
                'device_id' => $boundDeviceId,
                'state' => 'ENROLLING',
            ]);
        } catch (Throwable $exception) {
            error_log('Face enrollment start failed: ' . $exception->getMessage());
            $this->jsonResponse([
                'success' => false,
                'code' => 'ENROLLMENT_START_FAILED',
                'message' => 'Không thể bắt đầu đăng ký. Kiểm tra camera app.py (cổng 5000), AI1 (cổng 5001) và trạng thái nhân viên.',
            ], 503);
        }
    }

    /** Gửi frame hiện tại tới AI service để kiểm tra số mặt và pose mong đợi. */
    public function inspectPose(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        $state = $this->activeBatch($employeeId);
        if ($state === null) {
            return;
        }

        if (($state['mode'] ?? 'MANUAL') === 'AUTO') {
            $this->pollAutoEnrollment($employeeId, $state);
            return;
        }

        $poseIndex = EnrollmentCaptureState::poseIndex($state);
        $pose = self::POSES[$poseIndex] ?? null;
        if ($pose === null) {
            $this->jsonResponse(['success' => false, 'message' => 'Đã đủ 5 mẫu.'], 409);
            return;
        }

        $snapshot = $this->camera->captureSnapshot();
        if ($snapshot === null) {
            EnrollmentCaptureState::reset($state);
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            $this->jsonResponse(array_merge([
                'success' => false,
                'ready' => false,
                'reason' => 'Camera chưa sẵn sàng.',
                'message' => 'Camera chưa sẵn sàng.',
            ], $this->progressPayload($state, $pose)), 503);
            return;
        }
        $jpeg = $snapshot['jpeg'];
        $sequence = $snapshot['sequence'];
        if ($sequence <= (int)($state['last_camera_sequence'] ?? 0)) {
            $stability = EnrollmentCaptureState::observeSnapshot($state, $sequence, false);
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            $this->jsonResponse(array_merge([
                'success' => true,
                'ready' => false,
                'reason' => 'Đang chờ frame camera mới.',
                'message' => 'Đang chờ frame camera mới.',
            ], $this->progressPayload($state, $pose), $stability));
            return;
        }

        try {
            $result = $this->ai->inspectEnrollmentImage($jpeg, $pose);
            $ready = !empty($result['success']) && !empty($result['pose_ok']);
            $stability = EnrollmentCaptureState::observeSnapshot($state, $sequence, $ready);
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            $payload = array_merge($result, $this->progressPayload($state, $pose), $stability, [
                'ready' => $ready,
                'reason' => $ready ? '' : (string)($result['instruction'] ?? $result['message'] ?? 'Frame chưa hợp lệ.'),
                'auto_captured' => false,
            ]);

            if ($stability['capture_due'] && ($state['mode'] ?? 'MANUAL') !== 'MANUAL') {
                $capture = $this->captureSample($employeeId, $state, $pose, $jpeg, true);
                $this->jsonResponse(array_merge($payload, $capture['payload']), $capture['status']);
                return;
            }

            $this->jsonResponse($payload, !empty($result['success']) ? 200 : 503);
        } catch (Throwable $exception) {
            EnrollmentCaptureState::reset($state);
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            $this->jsonResponse(array_merge([
                'success' => false,
                'ready' => false,
                'reason' => 'Không thể kiểm tra hướng khuôn mặt.',
                'message' => 'Không thể kiểm tra hướng khuôn mặt.',
            ], $this->progressPayload($state, $pose)), 503);
        }
    }

    /** Return the AI-owned AUTO session progress to the Admin monitor. */
    private function pollAutoEnrollment(int $employeeId, array &$state): void
    {
        $sessionId = (string)($state['ai_session_id'] ?? '');
        try {
            $aiState = $this->ai->enrollmentSessionStatus($sessionId);
        } catch (Throwable $exception) {
            $this->jsonResponse([
                'success' => false,
                'ready' => false,
                'state' => 'OFFLINE',
                'reason' => 'Mất kết nối với AI1. Phiên cũ vẫn chưa bị thay thế.',
                'message' => 'Mất kết nối với AI1. Phiên cũ vẫn chưa bị thay thế.',
            ], 503);
            return;
        }
        if (($aiState['success'] ?? false) !== true) {
            $this->jsonResponse([
                'success' => false,
                'ready' => false,
                'state' => 'FAILED',
                'reason' => (string)($aiState['message'] ?? 'Không đọc được trạng thái AI1.'),
                'message' => (string)($aiState['message'] ?? 'Không đọc được trạng thái AI1.'),
            ], 503);
            return;
        }

        $captured = max(0, min(count(self::POSES), (int)($aiState['captured'] ?? 0)));
        $state['state'] = (string)($aiState['state'] ?? 'ENROLLING');
        $state['current_pose_index'] = $captured;
        $state['stable_frame_count'] = max(0, (int)($aiState['stable_count'] ?? 0));
        $state['stable_frames_required'] = max(1, (int)($aiState['stable_frames_required'] ?? 5));
        $state['inference_fps'] = $aiState['inference_fps'] ?? null;
        $state['status_reason'] = (string)($aiState['reason'] ?? '');
        $state['last_ai_status_at'] = time();

        if ($state['state'] === 'AWAITING_CONFIRMATION' && !$this->hydrateAutoSamples($employeeId, $state)) {
            $this->jsonResponse([
                'success' => false,
                'ready' => false,
                'state' => 'FAILED',
                'reason' => 'Không thể kiểm tra đủ năm mẫu từ AI1. Bộ dữ liệu cũ vẫn được giữ nguyên.',
                'message' => 'Không thể kiểm tra đủ năm mẫu từ AI1. Bộ dữ liệu cũ vẫn được giữ nguyên.',
            ], 502);
            return;
        }
        $duplicateCheck = $state['duplicate_check'] ?? null;
        $legacyUncalibratedReason = is_array($duplicateCheck)
            && ($duplicateCheck['status'] ?? null) === 'CHECK_UNAVAILABLE'
            && in_array((string)($duplicateCheck['reason'] ?? ''), [
                'THRESHOLD_MISSING', 'THRESHOLD_NOT_VALIDATED',
            ], true);
        if ($state['state'] === 'AWAITING_CONFIRMATION'
            && (!is_array($duplicateCheck) || $legacyUncalibratedReason)) {
            $state['duplicate_check'] = $this->faceEmbeddings->checkDuplicate(
                $employeeId,
                $state['samples']
            );
        }

        $previouslyReported = (int)($state['reported_captured'] ?? 0);
        $state['reported_captured'] = $captured;
        $_SESSION[self::SESSION_KEY][$employeeId] = $state;
        $expectedPose = is_string($aiState['expected_pose'] ?? null) ? $aiState['expected_pose'] : null;
        $poseIndex = max(0, min(count(self::POSES) - 1, $captured));
        if ($captured >= count(self::POSES)) {
            $expectedPose = null;
        }
        $this->jsonResponse([
            'success' => true,
            'ready' => $state['state'] === 'AWAITING_CONFIRMATION',
            'state' => $state['state'],
            'mode' => 'AUTO',
            'captured' => $captured,
            'total' => count(self::POSES),
            'current_pose_index' => $poseIndex,
            'expected_pose' => $expectedPose,
            'current_pose' => (string)($aiState['detected_pose'] ?? 'unknown'),
            'progress' => $captured . '/' . count(self::POSES),
            'stable_frame_count' => (int)($aiState['stable_count'] ?? 0),
            'stable_frames_required' => max(1, (int)($aiState['stable_frames_required'] ?? 5)),
            'inference_fps' => $aiState['inference_fps'] ?? null,
            'reason' => (string)($aiState['reason'] ?? ''),
            'instruction' => (string)($aiState['reason'] ?? ''),
            'auto_captured' => $captured > $previouslyReported,
            'complete' => $state['state'] === 'AWAITING_CONFIRMATION',
            'duplicate_check' => $state['duplicate_check'] ?? null,
            'demo_duplicate_bypass_enabled' => FaceDuplicateChecker::isLocalDemoBypassEnabled(),
        ]);
    }

    /** Move exactly five AI samples into the Admin's temporary session only for review/save. */
    private function hydrateAutoSamples(int $employeeId, array &$state): bool
    {
        if (count($state['samples'] ?? []) === count(self::POSES)) {
            return true;
        }
        try {
            $payload = $this->ai->enrollmentSessionSamples((string)$state['ai_session_id']);
        } catch (Throwable $exception) {
            error_log('Smart Enrollment samples could not be fetched.');
            return false;
        }
        $samples = $payload['samples'] ?? null;
        if (($payload['success'] ?? false) !== true || !is_array($samples) || count($samples) !== count(self::POSES)) {
            return false;
        }

        $decoded = [];
        foreach (self::POSES as $index => $pose) {
            $item = $samples[$index] ?? null;
            if (!is_array($item) || ($item['pose'] ?? null) !== $pose) {
                return false;
            }
            $vector = base64_decode((string)($item['vector'] ?? ''), true);
            $image = base64_decode((string)($item['image_jpeg'] ?? ''), true);
            $sha256 = (string)($item['image_sha256'] ?? '');
            if (!is_string($vector) || strlen($vector) !== 2048
                || !is_string($image) || $image === '' || strlen($image) > self::MAX_IMAGE_BYTES
                || !preg_match('/^[a-f0-9]{64}$/D', $sha256)
                || !hash_equals($sha256, hash('sha256', $image))
                || !$this->isValidImage($image)) {
                return false;
            }
            $floats = unpack('g*', $vector);
            if (!is_array($floats) || count($floats) !== 512) {
                return false;
            }
            $normSquared = 0.0;
            foreach ($floats as $value) {
                if (!is_float($value) && !is_int($value)) {
                    return false;
                }
                if (!is_finite((float)$value)) {
                    return false;
                }
                $normSquared += (float)$value * (float)$value;
            }
            $norm = sqrt($normSquared);
            if (!is_finite($norm) || abs($norm - 1.0) > 0.02) {
                return false;
            }
            $decoded[] = ['pose' => $pose, 'vector' => $vector, 'image' => $image];
        }

        $state['samples'] = $decoded;
        $state['current_pose_index'] = count(self::POSES);
        $state['state'] = 'AWAITING_CONFIRMATION';
        $_SESSION[self::SESSION_KEY][$employeeId] = $state;

        return true;
    }

    /** Thu một mẫu đã được AI xác nhận, giữ ảnh và vector theo cặp trong batch session. */
    public function capture(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        $state = $this->activeBatch($employeeId);
        if ($state === null) {
            return;
        }

        if (($state['mode'] ?? 'MANUAL') === 'AUTO') {
            $this->jsonResponse(['success' => false, 'message' => 'AUTO Enrollment tự chọn mẫu; không nhận lệnh chụp thủ công.'], 409);
            return;
        }

        $poseIndex = EnrollmentCaptureState::poseIndex($state);
        $pose = self::POSES[$poseIndex] ?? null;
        if ($pose === null) {
            $this->jsonResponse(['success' => false, 'message' => 'Đã đủ 5 mẫu.'], 409);
            return;
        }
        if (($state['stable_frame_count'] ?? 0) < EnrollmentCaptureState::STABLE_FRAMES_REQUIRED) {
            $this->jsonResponse(array_merge([
                'success' => false,
                'ready' => false,
                'reason' => 'Cần đủ 8 frame hợp lệ liên tiếp trước khi capture.',
                'message' => 'Cần đủ 8 frame hợp lệ liên tiếp trước khi capture.',
            ], $this->progressPayload($state, $pose)), 409);
            return;
        }
        $snapshot = $this->camera->captureSnapshot();
        if ($snapshot === null) {
            EnrollmentCaptureState::reset($state);
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            $this->jsonResponse(array_merge([
                'success' => false,
                'ready' => false,
                'reason' => 'Camera chưa sẵn sàng.',
                'message' => 'Camera chưa sẵn sàng.',
            ], $this->progressPayload($state, $pose)), 503);
            return;
        }
        $jpeg = $snapshot['jpeg'];
        if ($snapshot['sequence'] <= (int)($state['last_camera_sequence'] ?? 0)) {
            EnrollmentCaptureState::reset($state);
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            $this->jsonResponse(array_merge([
                'success' => false,
                'ready' => false,
                'reason' => 'Frame camera chưa mới. Hãy giữ pose và thử lại.',
                'message' => 'Frame camera chưa mới. Hãy giữ pose và thử lại.',
            ], $this->progressPayload($state, $pose)), 409);
            return;
        }
        $state['last_camera_sequence'] = $snapshot['sequence'];
        $_SESSION[self::SESSION_KEY][$employeeId] = $state;

        $capture = $this->captureSample($employeeId, $state, $pose, $jpeg, false);
        $this->jsonResponse($capture['payload'], $capture['status']);
    }

    /** Xác thực batch đủ 5 pose rồi thay toàn bộ embedding cũ trong một transaction. */
    public function complete(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        $state = $this->activeBatch($employeeId);
        if ($state === null) {
            return;
        }
        if (($state['mode'] ?? 'MANUAL') === 'AUTO'
            && !$this->hydrateAutoSamples($employeeId, $state)) {
            $this->jsonResponse([
                'success' => false,
                'message' => 'AUTO chưa thu đủ năm mẫu hợp lệ để xác nhận lưu.',
            ], 409);
            return;
        }
        if (count($state['samples']) !== count(self::POSES)
            || EnrollmentCaptureState::poseIndex($state) !== count(self::POSES)) {
            $this->jsonResponse(['success' => false, 'message' => 'Cần xác nhận đủ 5 góc trước khi lưu.'], 409);
            return;
        }

        try {
            $saveContext = [];
            $demoUnverifiedConfirmed = ($_POST['confirm_demo_unverified'] ?? null) === '1';
            $ids = $this->faceEmbeddings->replaceByEmployee(
                $employeeId,
                $state['samples'],
                (string)($state['expected_revision'] ?? ''),
                $saveContext,
                $demoUnverifiedConfirmed
            );
            // Independently reload the committed rows before releasing the pending
            // batch. The model also performs this check inside its transaction.
            if (count($ids) !== 5
                || $this->faceEmbeddings->countByEmployee($employeeId) !== 5
                || !$this->faceEmbeddings->verifyBatchByEmployee($employeeId, $state['samples'])) {
                $this->jsonResponse([
                    'success' => false,
                    'code' => 'PERSISTENCE_VERIFY_FAILED',
                    'message' => 'Chưa xác minh được đủ 5 ảnh và embedding trong database. Batch vẫn được giữ để kiểm tra lại.',
                ], 500);
                return;
            }
            $deviceId = (int)($state['device_id'] ?? 0);
            if (is_string($state['ai_session_id'] ?? null)) {
                try {
                    $closed = $this->ai->closeEnrollmentSession((string)$state['ai_session_id']);
                    if (empty($closed['success'])) {
                        error_log('Smart Enrollment AI session did not close cleanly after save.');
                        $cancelled = $this->ai->cancelEnrollmentSession((string)$state['ai_session_id']);
                        if (empty($cancelled['success'])) {
                            error_log('Smart Enrollment AI session release fallback was unsuccessful.');
                        }
                    }
                } catch (Throwable $exception) {
                    error_log('Smart Enrollment AI session close failed after save.');
                    try {
                        $cancelled = $this->ai->cancelEnrollmentSession((string)$state['ai_session_id']);
                        if (empty($cancelled['success'])) {
                            error_log('Smart Enrollment AI session release fallback was unsuccessful.');
                        }
                    } catch (Throwable $releaseException) {
                        error_log('Smart Enrollment AI session release fallback failed after save.');
                    }
                }
            }
            unset($_SESSION[self::SESSION_KEY][$employeeId]);
            $galleryUpdated = false;
            try {
                // Push the committed PHP gallery to AI. A pull here would make
                // ai_service.py call back into this still-running PHP request.
                $gallery = $this->ai->syncGallery($this->faceEmbeddings->findAllForInternalGallery());
                $galleryUpdated = !empty($gallery['success'])
                    && (int)($gallery['embedding_count'] ?? -1) === $this->faceEmbeddings->countAllActive()
                    && (int)($gallery['invalid_count'] ?? -1) === 0;
            } catch (Throwable $exception) {
                error_log('Face enrollment gallery push failed after save: ' . $exception->getMessage());
                $galleryUpdated = false;
            }
            $this->rememberDeviceEnrollmentNotice(
                $deviceId,
                'COMPLETED',
                !empty($saveContext['demo_duplicate_check_skipped'])
                    ? 'Đã lưu trong DEMO LOCAL; kiểm tra trùng chưa được thực hiện.'
                    : ($galleryUpdated
                        ? 'Đăng ký khuôn mặt thành công.'
                        : 'Đã lưu đăng ký. Hệ thống đang đồng bộ AI1; vui lòng thử lại sau.'),
                $employeeId,
                (string)($state['employee_name'] ?? '')
            );
            $demoUnchecked = !empty($saveContext['demo_duplicate_check_skipped']);
            $duplicateResult = $saveContext['duplicate_check'] ?? null;
            $demoReason = is_array($duplicateResult)
                ? (string)($duplicateResult['reason'] ?? 'UNKNOWN')
                : 'UNKNOWN';
            $this->jsonResponse([
                'success' => true,
                'saved' => count($ids),
                'gallery_updated' => $galleryUpdated,
                'demo_duplicate_check_skipped' => $demoUnchecked,
                'duplicate_check_status' => $duplicateResult['status'] ?? null,
                'duplicate_check_reason' => $demoUnchecked ? $demoReason : null,
                'message' => $demoUnchecked
                    ? ($galleryUpdated
                        ? 'Đã lưu đủ 5 mẫu trong DEMO LOCAL. Chống trùng chưa được kiểm tra ('
                            . ($duplicateResult['status'] ?? 'CHECK_UNAVAILABLE') . ': '
                            . $demoReason . ').'
                        : 'Đã lưu đủ 5 mẫu trong DEMO LOCAL nhưng gallery AI1 chưa đồng bộ. '
                            . 'Chống trùng chưa được kiểm tra (' . $demoReason . ').')
                    : ($galleryUpdated
                        ? 'Đã lưu đủ 5 mẫu khuôn mặt.'
                        : 'Đã lưu đủ 5 mẫu, nhưng gallery AI1 chưa đồng bộ. Nhận diện sẽ bị tạm chặn cho đến khi đồng bộ thành công.'),
            ]);
        } catch (FaceDuplicateCheckException $exception) {
            $check = $exception->checkResult();
            $_SESSION[self::SESSION_KEY][$employeeId]['duplicate_check'] = $check;
            $deviceId = (int)($state['device_id'] ?? 0);
            $this->rememberDeviceEnrollmentNotice(
                $deviceId,
                'FAILED',
                'Không thể hoàn tất đăng ký. Vui lòng liên hệ quản trị viên.'
            );
            $candidateId = (int)($check['candidate_id'] ?? 0);
            $candidateCode = $candidateId > 0 ? 'NV' . str_pad((string)$candidateId, 3, '0', STR_PAD_LEFT) : '';
            $message = ($check['status'] ?? '') === 'SUSPECTED_DUPLICATE' && $candidateCode !== ''
                ? 'Phát hiện khuôn mặt có khả năng trùng với nhân viên ' . $candidateCode
                    . '. Vui lòng kiểm tra trước khi đăng ký.'
                : 'Chưa thể kiểm tra trùng khuôn mặt. Vui lòng thử lại.';
            $this->jsonResponse([
                'success' => false,
                'code' => 'DUPLICATE_FACE_CHECK',
                'duplicate_check' => $check,
                'demo_duplicate_bypass_enabled' => FaceDuplicateChecker::isLocalDemoBypassEnabled(),
                'message' => $message,
            ], ($check['status'] ?? '') === 'SUSPECTED_DUPLICATE' ? 409 : 503);
        } catch (FaceEnrollmentConflict $exception) {
            $deviceId = (int)($state['device_id'] ?? 0);
            $this->cancelAiSession($state);
            unset($_SESSION[self::SESSION_KEY][$employeeId]);
            $this->rememberDeviceEnrollmentNotice($deviceId, 'FAILED', 'Dữ liệu khuôn mặt đã thay đổi. Hãy làm mới và đăng ký lại.');
            $this->jsonResponse([
                'success' => false,
                'conflict' => true,
                'message' => $exception->getMessage(),
            ], 409);
        } catch (Throwable $exception) {
            error_log('Face enrollment batch save failed: ' . $exception->getMessage());
            $this->jsonResponse(['success' => false, 'message' => 'Không thể lưu batch. Dữ liệu khuôn mặt cũ vẫn được giữ nguyên.'], 500);
        }
    }

    /** Hủy batch chưa hoàn tất mà không tác động tới các embedding đang lưu. */
    public function cancel(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        $state = $_SESSION[self::SESSION_KEY][$employeeId] ?? null;
        if (is_array($state)) {
            $this->cancelAiSession($state);
            $this->rememberDeviceEnrollmentNotice(
                (int)($state['device_id'] ?? 0),
                'CANCELLED',
                'Phiên đăng ký đã được hủy.'
            );
        }
        unset($_SESSION[self::SESSION_KEY][$employeeId]);
        $this->jsonResponse(['success' => true]);
    }

    /** Xóa toàn bộ embedding của nhân viên sau khi xác minh Admin và CSRF. */
    public function deleteRegistration(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        try {
            if ($this->employees->findById($employeeId) === null) {
                $this->jsonResponse(['success' => false, 'message' => 'Không tìm thấy nhân viên.'], 404);
                return;
            }
            $deleted = $this->faceEmbeddings->deleteByEmployee($employeeId);
            unset($_SESSION[self::SESSION_KEY][$employeeId]);
            $galleryUpdated = false;
            try {
                $galleryUpdated = !empty($this->ai->refreshGallery()['success']);
            } catch (Throwable $exception) {
                $galleryUpdated = false;
            }
            $this->jsonResponse([
                'success' => true,
                'deleted' => $deleted,
                'gallery_updated' => $galleryUpdated,
                'message' => 'Đã xóa toàn bộ mẫu khuôn mặt của nhân viên.',
            ]);
        } catch (Throwable $exception) {
            error_log('Face registration delete failed: ' . $exception->getMessage());
            $this->jsonResponse(['success' => false, 'message' => 'Không thể xóa đăng ký khuôn mặt.'], 500);
        }
    }

    /** Trả ảnh mẫu khuôn mặt qua route bảo vệ, không nhúng binary/base64 vào HTML. */
    public function image(): void
    {
        AuthController::requireAdmin();
        $embeddingId = filter_var($_GET['id'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if ($embeddingId === false) {
            http_response_code(404);
            exit;
        }

        try {
            $row = $this->faceEmbeddings->findImageById((int)$embeddingId);
            $image = is_array($row) ? $row['AnhKhuonMat'] : null;
            if (is_resource($image)) {
                $image = stream_get_contents($image);
            }
            if (!is_string($image) || $image === '' || !$this->isValidImage($image)) {
                http_response_code(404);
                exit;
            }
            $mime = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);
            header('Content-Type: ' . $mime);
            header('Content-Length: ' . strlen($image));
            header('Cache-Control: private, no-store');
            header('X-Content-Type-Options: nosniff');
            echo $image;
        } catch (Throwable $exception) {
            http_response_code(404);
        }
    }

    /** Serve one uncommitted capture thumbnail from the authenticated PHP session. */
    public function sessionPreview(): void
    {
        $employeeId = $this->requestEmployeeId();
        $index = filter_var($_GET['index'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0, 'max_range' => 4]]);
        $sample = is_int($index)
            ? ($_SESSION[self::SESSION_KEY][$employeeId]['samples'][$index] ?? null)
            : null;
        $image = is_array($sample) ? ($sample['image'] ?? null) : null;
        if (!is_string($image) || !$this->isValidImage($image)) {
            http_response_code(404);
            header('Cache-Control: private, no-store');
            exit;
        }

        $mime = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);
        header('Content-Type: ' . $mime);
        header('Content-Length: ' . strlen($image));
        header('Cache-Control: private, no-store');
        header('X-Content-Type-Options: nosniff');
        echo $image;
    }

    /** Safe, read-only enrollment state for the authenticated attendance display. */
    public function deviceStatus(): void
    {
        AuthController::requireAdmin();
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'GET') {
            $this->jsonResponse(['success' => false, 'message' => 'Chỉ chấp nhận GET.'], 405);
        }
        $deviceId = filter_var($_GET['device_id'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if (!is_int($deviceId)) {
            $this->jsonResponse(['success' => false, 'message' => 'Thiết bị không hợp lệ.'], 400);
        }
        try {
            $devices = (new DeviceModel())->findAll();
            if (AttendanceCameraBinding::deviceId($devices) !== $deviceId) {
                $this->jsonResponse(['success' => false, 'message' => 'Thiết bị chưa được gán nguồn camera AI1.'], 403);
            }
        } catch (Throwable $exception) {
            $this->jsonResponse(['success' => false, 'message' => 'Không thể xác minh thiết bị.'], 503);
        }

        foreach (($_SESSION[self::SESSION_KEY] ?? []) as $employeeId => $state) {
            if (!is_array($state) || (int)($state['device_id'] ?? 0) !== $deviceId) {
                continue;
            }
            if (time() - (int)($state['started_at'] ?? 0) > self::SESSION_TTL) {
                $this->cancelAiSession($state);
                unset($_SESSION[self::SESSION_KEY][$employeeId]);
                $this->rememberDeviceEnrollmentNotice($deviceId, 'EXPIRED', 'Phiên đăng ký đã hết hạn.');
                break;
            }
            $captured = count($state['samples'] ?? []);
            $stateName = (string)($state['state'] ?? 'ENROLLING');
            $reason = (string)($state['status_reason'] ?? '');
            $expectedPose = self::POSES[min($captured, count(self::POSES) - 1)] ?? null;
            $aiState = [];
            if (($state['mode'] ?? '') === 'AUTO') {
                try {
                    $aiState = $this->ai->enrollmentSessionStatus((string)($state['ai_session_id'] ?? ''));
                    if (($aiState['success'] ?? false) === true) {
                        $captured = (int)($aiState['captured'] ?? $captured);
                        $stateName = (string)($aiState['state'] ?? $stateName);
                        $expectedPose = $aiState['expected_pose'] ?? $expectedPose;
                        $reason = (string)($aiState['reason'] ?? $reason);
                    } else {
                        $stateName = 'OFFLINE';
                        $reason = 'Mất kết nối với AI1. Dữ liệu cũ vẫn được giữ nguyên.';
                    }
                } catch (Throwable $exception) {
                    $stateName = 'OFFLINE';
                    $reason = 'Mất kết nối với AI1. Dữ liệu cũ vẫn được giữ nguyên.';
                }
            }
            $employee = $this->employees->findById((int)$employeeId);
            $primaryFaceSafe = ($aiState['primary_face_safe'] ?? false) === true;
            $faceBox = $aiState['face_bbox'] ?? null;
            $frameWidth = filter_var($aiState['frame_width'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 8192]]);
            $frameHeight = filter_var($aiState['frame_height'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 8192]]);
            if (!is_array($faceBox) || count($faceBox) !== 4 || !is_int($frameWidth) || !is_int($frameHeight)
                || !$primaryFaceSafe) {
                $faceBox = null;
                $frameWidth = 0;
                $frameHeight = 0;
            } else {
                foreach ($faceBox as $coordinate) {
                    if (!is_numeric($coordinate) || !is_finite((float)$coordinate)) {
                        $faceBox = null;
                        $frameWidth = 0;
                        $frameHeight = 0;
                        break;
                    }
                }
                if (is_array($faceBox)) {
                    $faceBox = array_map('floatval', array_values($faceBox));
                }
            }
            $feedbackCode = strtoupper(trim((string)($aiState['feedback_code'] ?? '')));
            $qualityCode = strtoupper(trim((string)($aiState['quality_code'] ?? '')));
            if (!preg_match('/^[A-Z0-9_ ]{0,40}$/D', $feedbackCode)) {
                $feedbackCode = '';
            }
            if (!preg_match('/^[A-Z0-9_ ]{0,40}$/D', $qualityCode)) {
                $qualityCode = '';
            }
            $detectedPose = strtolower((string)($aiState['detected_pose'] ?? 'unknown'));
            if (!in_array($detectedPose, ['frontal', 'left', 'right', 'up', 'down', 'between', 'no_face', 'unknown', 'multiple_faces'], true)) {
                $detectedPose = 'unknown';
            }
            $faceCount = filter_var($aiState['face_count'] ?? null, FILTER_VALIDATE_INT, [
                'options' => ['min_range' => 0, 'max_range' => 100],
            ]);
            $totalFaceCount = filter_var($aiState['total_face_count'] ?? $aiState['face_count'] ?? null, FILTER_VALIDATE_INT, [
                'options' => ['min_range' => 0, 'max_range' => 100],
            ]);
            $faceCountLowerBound = false;
            if (!is_int($faceCount) && is_int($totalFaceCount)) {
                $faceCount = $totalFaceCount;
            }
            if (!is_int($totalFaceCount) && is_int($faceCount)) {
                $totalFaceCount = $faceCount;
            }
            if (!is_int($faceCount) && $qualityCode === 'MULTIPLE FACES') {
                // MULTIPLE FACES proves at least two detections even if an old
                // AI1 worker omitted the newly-added count fields.
                $faceCount = 2;
                $totalFaceCount = 2;
                $faceCountLowerBound = true;
            }
            $primaryFaceAreaRatio = $aiState['primary_face_area_ratio'] ?? null;
            if (!is_numeric($primaryFaceAreaRatio) || !is_finite((float)$primaryFaceAreaRatio)
                || (float)$primaryFaceAreaRatio < 1.0 || (float)$primaryFaceAreaRatio > 10000.0) {
                $primaryFaceAreaRatio = null;
            } else {
                $primaryFaceAreaRatio = (float)$primaryFaceAreaRatio;
            }
            $primaryFaceAreaRatioRequired = $aiState['primary_face_area_ratio_required'] ?? null;
            if (!is_numeric($primaryFaceAreaRatioRequired) || !is_finite((float)$primaryFaceAreaRatioRequired)
                || (float)$primaryFaceAreaRatioRequired < 1.0 || (float)$primaryFaceAreaRatioRequired > 100.0) {
                $primaryFaceAreaRatioRequired = null;
            } else {
                $primaryFaceAreaRatioRequired = (float)$primaryFaceAreaRatioRequired;
            }
            $detectionScore = $aiState['detection_score'] ?? null;
            if (!is_numeric($detectionScore) || !is_finite((float)$detectionScore)
                || (float)$detectionScore < 0.0 || (float)$detectionScore > 1.0) {
                $detectionScore = null;
            } else {
                $detectionScore = (float)$detectionScore;
            }
            $inferenceFps = $aiState['inference_fps'] ?? null;
            if (!is_numeric($inferenceFps) || !is_finite((float)$inferenceFps)
                || (float)$inferenceFps < 0.0 || (float)$inferenceFps > 1000.0) {
                $inferenceFps = null;
            } else {
                $inferenceFps = (float)$inferenceFps;
            }
            $frameSequence = filter_var($aiState['frame_sequence'] ?? null, FILTER_VALIDATE_INT, [
                'options' => ['min_range' => 0],
            ]);
            $frameTimestamp = $aiState['frame_timestamp'] ?? null;
            if (!is_numeric($frameTimestamp) || !is_finite((float)$frameTimestamp)) {
                $frameTimestamp = null;
            } else {
                $frameTimestamp = (float)$frameTimestamp;
            }
            $frameAgeMs = $aiState['frame_age_ms'] ?? null;
            if (!is_numeric($frameAgeMs) || !is_finite((float)$frameAgeMs)
                || (float)$frameAgeMs < 0.0 || (float)$frameAgeMs > 600000.0) {
                $frameAgeMs = null;
            } else {
                $frameAgeMs = (float)$frameAgeMs;
            }
            $this->jsonResponse([
                'success' => true,
                'state' => $stateName,
                'mode' => (string)($state['mode'] ?? 'MANUAL'),
                'employee_id' => (int)$employeeId,
                'employee_name' => (string)($employee['HoTen'] ?? ''),
                'expected_pose' => is_string($expectedPose) ? $expectedPose : null,
                'captured' => max(0, min(count(self::POSES), $captured)),
                'total' => count(self::POSES),
                'stable_frame_count' => max(0, (int)($aiState['stable_count'] ?? $state['stable_frame_count'] ?? 0)),
                'stable_frames_required' => max(1, (int)($aiState['stable_frames_required'] ?? $state['stable_frames_required'] ?? 5)),
                'detected_pose' => $detectedPose,
                'observation_status' => (string)($aiState['observation_status'] ?? ''),
                'feedback_code' => $feedbackCode,
                'quality_code' => $qualityCode,
                'face_count' => is_int($faceCount) ? $faceCount : null,
                'total_face_count' => is_int($totalFaceCount) ? $totalFaceCount : null,
                'face_count_lower_bound' => $faceCountLowerBound,
                'primary_face_safe' => $primaryFaceSafe,
                'primary_face_area_ratio' => $primaryFaceAreaRatio,
                'primary_face_area_ratio_required' => $primaryFaceAreaRatioRequired,
                'detection_score' => $detectionScore,
                'inference_fps' => $inferenceFps,
                'frame_sequence' => is_int($frameSequence) ? $frameSequence : null,
                'frame_timestamp' => $frameTimestamp,
                'frame_age_ms' => $frameAgeMs,
                'face_bbox' => $faceBox,
                'frame_width' => $frameWidth,
                'frame_height' => $frameHeight,
                'reason' => $reason,
            ]);
        }

        $notice = $_SESSION['kiosk_enrollment_notices'][$deviceId] ?? null;
        if (is_array($notice) && (int)($notice['expires_at'] ?? 0) >= time()) {
            $this->jsonResponse([
                'success' => true,
                'state' => (string)($notice['state'] ?? 'IDLE'),
                'captured' => 5,
                'total' => count(self::POSES),
                'reason' => (string)($notice['message'] ?? ''),
                'employee_id' => (int)($notice['employee_id'] ?? 0),
                'employee_name' => (string)($notice['employee_name'] ?? ''),
            ]);
        }
        unset($_SESSION['kiosk_enrollment_notices'][$deviceId]);
        $this->jsonResponse(['success' => true, 'state' => 'IDLE', 'captured' => 0, 'total' => count(self::POSES)]);
    }

    /** Capture one paired JPEG/vector into the uncommitted PHP session batch. */
    private function captureSample(int $employeeId, array &$state, string $pose, string $jpeg, bool $automatic): array
    {
        try {
            $reference = $state['samples'][0]['vector'] ?? null;
            $result = $this->ai->captureEnrollmentSample($jpeg, $pose, $reference);
            if (empty($result['success']) || empty($result['pose_ok'])) {
                EnrollmentCaptureState::reset($state);
                $_SESSION[self::SESSION_KEY][$employeeId] = $state;
                $fields = array_intersect_key($result, array_flip([
                    'current_pose', 'expected_pose', 'yaw', 'pitch', 'instruction',
                ]));
                $reason = (string)($result['instruction'] ?? 'Frame không còn đạt điều kiện capture.');
                return [
                    'status' => 409,
                    'payload' => array_merge($fields, $this->progressPayload($state, $pose), [
                        'success' => false,
                        'ready' => false,
                        'reason' => $reason,
                        'message' => $reason,
                        'auto_captured' => false,
                    ]),
                ];
            }

            $vector = base64_decode((string)($result['vector'] ?? ''), true);
            $image = base64_decode((string)($result['image_jpeg'] ?? ''), true);
            if (!is_string($vector) || strlen($vector) !== 2048 || !is_string($image)
                || $image === '' || strlen($image) > self::MAX_IMAGE_BYTES
                || !hash_equals((string)($result['image_sha256'] ?? ''), hash('sha256', $image))
                || !$this->isValidImage($image)) {
                EnrollmentCaptureState::reset($state);
                $_SESSION[self::SESSION_KEY][$employeeId] = $state;
                return [
                    'status' => 502,
                    'payload' => array_merge($this->progressPayload($state, $pose), [
                        'success' => false,
                        'ready' => false,
                        'reason' => 'Mẫu AI trả về không hợp lệ.',
                        'message' => 'Mẫu AI trả về không hợp lệ.',
                        'auto_captured' => false,
                    ]),
                ];
            }

            $captured = EnrollmentCaptureState::recordSample(
                $state,
                self::POSES,
                $pose,
                ['vector' => $vector, 'image' => $image],
            );
            $state['state'] = $captured === count(self::POSES) ? 'AWAITING_CONFIRMATION' : 'ENROLLING';
            if ($captured === count(self::POSES)) {
                $state['duplicate_check'] = $this->faceEmbeddings->checkDuplicate(
                    $employeeId,
                    $state['samples']
                );
            }
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            $nextPose = self::POSES[$state['current_pose_index']] ?? null;
            $progress = $this->progressPayload($state, $nextPose);
            return [
                'status' => 200,
                'payload' => array_merge(
                    array_intersect_key($result, array_flip(['current_pose', 'yaw', 'pitch'])),
                    $progress,
                    [
                        'success' => true,
                        'ready' => true,
                        'reason' => '',
                        'pose' => $pose,
                        'captured' => $captured,
                        'next_pose' => $nextPose,
                        'complete' => $captured === count(self::POSES),
                        'duplicate_check' => $state['duplicate_check'] ?? null,
                        'demo_duplicate_bypass_enabled' => FaceDuplicateChecker::isLocalDemoBypassEnabled(),
                        'auto_captured' => $automatic,
                        'stable_frame_count' => 0,
                        'stable_frames_required' => EnrollmentCaptureState::STABLE_FRAMES_REQUIRED,
                        'instruction' => $automatic
                            ? ($nextPose === null ? 'Đã tự động chụp đủ 5 góc.' : 'Đã tự động chụp. Đang chuyển sang pose tiếp theo.')
                            : 'Mẫu đã được ghi nhận.',
                    ],
                ),
            ];
        } catch (Throwable $exception) {
            EnrollmentCaptureState::reset($state);
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            error_log('Face enrollment sample capture failed: ' . $exception->getMessage());
            return [
                'status' => 503,
                'payload' => array_merge($this->progressPayload($state, $pose), [
                    'success' => false,
                    'ready' => false,
                    'reason' => 'Không thể ghi nhận mẫu khuôn mặt.',
                    'message' => 'Không thể ghi nhận mẫu khuôn mặt.',
                    'auto_captured' => false,
                ]),
            ];
        }
    }

    private function progressPayload(array $state, ?string $expectedPose): array
    {
        $captured = count($state['samples'] ?? []);
        $index = EnrollmentCaptureState::poseIndex($state);

        return [
            'captured' => $captured,
            'total' => count(self::POSES),
            'current_pose_index' => $index,
            'expected_pose' => $expectedPose,
            'progress' => $captured . '/' . count(self::POSES),
            'stable_frame_count' => (int)($state['stable_frame_count'] ?? 0),
            'stable_frames_required' => EnrollmentCaptureState::STABLE_FRAMES_REQUIRED,
            'demo_duplicate_bypass_enabled' => FaceDuplicateChecker::isLocalDemoBypassEnabled(),
        ];
    }

    private function cancelAiSession(array $state): void
    {
        if (!is_string($state['ai_session_id'] ?? null)) {
            return;
        }
        try {
            $this->ai->cancelEnrollmentSession($state['ai_session_id']);
        } catch (Throwable $exception) {
            error_log('Smart Enrollment AI session cancellation failed.');
        }
    }

    private function rememberDeviceEnrollmentNotice(
        int $deviceId,
        string $state,
        string $message,
        int $employeeId = 0,
        string $employeeName = ''
    ): void
    {
        if ($deviceId < 1) {
            return;
        }
        if (!isset($_SESSION['kiosk_enrollment_notices']) || !is_array($_SESSION['kiosk_enrollment_notices'])) {
            $_SESSION['kiosk_enrollment_notices'] = [];
        }
        $_SESSION['kiosk_enrollment_notices'][$deviceId] = [
            'state' => $state,
            'message' => $message,
            'employee_id' => $employeeId,
            'employee_name' => $employeeName,
            'expires_at' => time() + 6,
        ];
    }

    private function activeBatch(int $employeeId): ?array
    {
        $state = $_SESSION[self::SESSION_KEY][$employeeId] ?? null;
        if (!is_array($state) || time() - (int)($state['started_at'] ?? 0) > self::SESSION_TTL) {
            if (is_array($state)) {
                $deviceId = (int)($state['device_id'] ?? 0);
                $this->cancelAiSession($state);
                $this->rememberDeviceEnrollmentNotice($deviceId, 'EXPIRED', 'Phiên đăng ký đã hết hạn.');
            }
            unset($_SESSION[self::SESSION_KEY][$employeeId]);
            $this->jsonResponse(['success' => false, 'message' => 'Phiên đăng ký đã hết hạn. Hãy bắt đầu lại.'], 410);
            return null;
        }

        return $state;
    }

    private function cameraFrame(): ?string
    {
        $jpeg = $this->camera->captureJpeg();
        if (!is_string($jpeg) || strlen($jpeg) > self::MAX_IMAGE_BYTES || !$this->isValidImage($jpeg)) {
            return null;
        }

        return $jpeg;
    }

    private function isValidImage(string $image): bool
    {
        $mime = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);

        return in_array($mime, ['image/jpeg', 'image/png'], true)
            && getimagesizefromstring($image) !== false;
    }

    private function requestEmployeeId(): int
    {
        AuthController::requireAdmin();
        $employeeId = filter_var($_GET['id'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if ($employeeId === false) {
            $this->jsonResponse(['success' => false, 'message' => 'Mã nhân viên không hợp lệ.'], 404);
        }

        return (int)$employeeId;
    }

    private function requirePostCsrf(): bool
    {
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            header('Allow: POST');
            $this->jsonResponse(['success' => false, 'message' => 'Method Not Allowed'], 405);
            return false;
        }
        if (!CsrfToken::isValid()) {
            $this->jsonResponse(['success' => false, 'message' => 'Phiên biểu mẫu hết hạn. Tải lại trang và thử lại.'], 400);
            return false;
        }

        return true;
    }

    private function jsonResponse(array $payload, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: private, no-store');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
        exit;
    }
}
