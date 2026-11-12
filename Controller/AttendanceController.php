<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/AttendanceModel.php';
require_once __DIR__ . '/../Model/ScanHistoryModel.php';
require_once __DIR__ . '/AuthController.php';
require_once __DIR__ . '/../Service/AttendanceService.php';
require_once __DIR__ . '/../Service/CameraFrameClient.php';

final class AttendanceController
{
    private AttendanceModel $attendance;
    private ScanHistoryModel $scanHistory;
    private AttendanceService $service;
    private CameraFrameClient $camera;

    public function __construct()
    {
        $this->attendance = new AttendanceModel();
        $this->scanHistory = new ScanHistoryModel();
        $this->service = new AttendanceService();
        $this->camera = new CameraFrameClient();
    }

    /** Lọc và phân trang dữ liệu chấm công theo ngày, nhân viên hoặc từ khóa. */
    public function index(): void
    {
        AuthController::requireAdmin();

        $activeTab = (string)($_GET['tab'] ?? 'attendance');
        if ($activeTab === 'scan_history') {
            $this->scanHistoryIndex();
            return;
        }
        if ($activeTab === 'live') {
            $this->liveAttendanceIndex();
            return;
        }
        if ($activeTab !== 'attendance') {
            http_response_code(404);
            return;
        }

        $today = (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))->format('Y-m-d');
        $fromDate = trim((string)($_GET['from_date'] ?? $today));
        $toDate = trim((string)($_GET['to_date'] ?? $today));
        $employeeId = null;
        $errors = [];
        $attendanceRows = [];
        $employees = [];
        $error = null;
        $keyword = trim((string)($_GET['keyword'] ?? ''));
        $page = filter_var($_GET['page'] ?? 1, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $limit = filter_var($_GET['limit'] ?? 20, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 100]]);
        $page = is_int($page) ? $page : 1;
        $limit = is_int($limit) ? $limit : 20;

        if (filter_var($_GET['page'] ?? 1, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]) === false) {
            $errors['page'] = 'Trang không hợp lệ.';
        }
        if (filter_var($_GET['limit'] ?? 20, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 100]]) === false) {
            $errors['limit'] = 'Số dòng mỗi trang không hợp lệ.';
        }
        if (mb_strlen($keyword, 'UTF-8') > 100) {
            $errors['keyword'] = 'Từ khóa không được vượt quá 100 ký tự.';
        }

        if ($fromDate === '') {
            $fromDate = $toDate;
        }
        if ($toDate === '') {
            $toDate = $fromDate;
        }
        if (!$this->isValidDate($fromDate)) {
            $errors['from_date'] = 'Ngày bắt đầu không hợp lệ.';
        }
        if (!$this->isValidDate($toDate)) {
            $errors['to_date'] = 'Ngày kết thúc không hợp lệ.';
        }
        if ($errors === [] && $fromDate > $toDate) {
            $errors['date_range'] = 'Ngày bắt đầu phải nhỏ hơn hoặc bằng ngày kết thúc.';
        }

        $rawEmployeeId = trim((string)($_GET['employee_id'] ?? ''));
        if ($rawEmployeeId !== '') {
            $parsedEmployeeId = filter_var($rawEmployeeId, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
            if (!is_int($parsedEmployeeId)) {
                $errors['employee_id'] = 'Nhân viên không hợp lệ.';
            } else {
                $employeeId = $parsedEmployeeId;
            }
        }

        if ($errors !== []) {
            http_response_code(422);
        }

        $totalRows = 0;
        $totalPages = 1;
        try {
            $employees = $this->attendance->findEmployees();
            if ($errors === []) {
                $isDaily = $fromDate === $toDate;
                $totalRows = $isDaily
                    ? $this->attendance->countDaily($fromDate, $employeeId, $keyword)
                    : $this->attendance->countHistory($fromDate, $toDate, $employeeId, $keyword);
                $totalPages = max(1, (int)ceil($totalRows / $limit));
                $page = min($page, $totalPages);
                $offset = ($page - 1) * $limit;
                $attendanceRows = $isDaily
                    ? $this->attendance->findDaily($fromDate, $employeeId, $keyword, $limit, $offset)
                    : $this->attendance->findHistory($fromDate, $toDate, $employeeId, $keyword, $limit, $offset);
                foreach ($attendanceRows as &$row) {
                    $statuses = $this->calculateStatuses(
                        $row['GioBatDau'] ?? null,
                        $row['GioKetThuc'] ?? null,
                        $row['GioVao'] ?? null,
                        $row['GioRa'] ?? null
                    );
                    $row['TrangThaiVao'] = $statuses['entry'];
                    $row['TrangThaiRa'] = $statuses['exit'];
                }
                unset($row);
            }
        } catch (Throwable $exception) {
            error_log('Attendance page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải dữ liệu chấm công. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        $isDaily = $fromDate === $toDate;
        $pageTitle = 'Chấm công';
        require __DIR__ . '/../View/attendance.php';
    }

    /** Màn hình giám sát chỉ đọc, dùng camera singleton và dữ liệu chấm công hiện có. */
    private function liveAttendanceIndex(): void
    {
        $recentPunches = [];
        $error = null;
        try {
            $recentPunches = $this->attendance->findRecentPunches(6);
        } catch (Throwable $exception) {
            error_log('Live attendance page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải lượt chấm công gần đây. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        $activeTab = 'live';
        $pageTitle = 'Giám sát chấm công trực tiếp';
        require __DIR__ . '/../View/attendance.php';
    }

    /** JSON feed chỉ đọc cho bảng lượt chấm công mới nhất trên màn hình giám sát. */
    public function liveAttendanceFeed(): void
    {
        AuthController::requireAdmin();
        try {
            $this->jsonResponse([
                'success' => true,
                'recent' => $this->attendance->findRecentPunches(6),
                'server_time' => (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))->format('H:i:s d/m/Y'),
            ], 200);
        } catch (Throwable $exception) {
            error_log('Live attendance feed read failed: ' . $exception->getMessage());
            $this->jsonResponse([
                'success' => false,
                'message' => 'Không thể cập nhật dữ liệu chấm công.',
            ], 503);
        }
    }

    /** Filter and render the administrator-only rejected-scan history. */
    private function scanHistoryIndex(): void
    {
        $date = trim((string)($_GET['date'] ?? ''));
        $employeeId = null;
        $deviceId = null;
        $reason = trim((string)($_GET['reason'] ?? ''));
        $errors = [];
        $scanRows = [];
        $error = null;
        $page = filter_var($_GET['page'] ?? 1, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $limit = filter_var($_GET['limit'] ?? 20, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 100]]);
        $page = is_int($page) ? $page : 1;
        $limit = is_int($limit) ? $limit : 20;

        if (filter_var($_GET['page'] ?? 1, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]) === false) {
            $errors['page'] = 'Trang không hợp lệ.';
        }
        if (filter_var($_GET['limit'] ?? 20, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 100]]) === false) {
            $errors['limit'] = 'Số dòng mỗi trang không hợp lệ.';
        }
        if ($date !== '' && !$this->isValidDate($date)) {
            $errors['date'] = 'Ngày không hợp lệ.';
        }
        foreach (['employee_id', 'device_id'] as $queryKey) {
            $rawId = trim((string)($_GET[$queryKey] ?? ''));
            if ($rawId === '') {
                continue;
            }
            $parsedId = filter_var($rawId, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
            if (!is_int($parsedId)) {
                $errors[$queryKey] = 'Giá trị bộ lọc không hợp lệ.';
                continue;
            }
            if ($queryKey === 'employee_id') {
                $employeeId = $parsedId;
            } else {
                $deviceId = $parsedId;
            }
        }
        $reasonLabels = [];

        $filters = [
            'date' => $date === '' ? null : $date,
            'employee_id' => $employeeId,
            'device_id' => $deviceId,
            'reason' => $reason === '' ? null : $reason,
        ];
        $employees = [];
        $devices = [];
        $totalRows = 0;
        $totalPages = 1;
        if ($errors !== []) {
            http_response_code(422);
        }
        try {
            $reasonLabels = $this->scanHistory->reasonLabels();
            if ($reason !== '' && !array_key_exists($reason, $reasonLabels)) {
                $errors['reason'] = 'Lý do quét không hợp lệ.';
                http_response_code(422);
            }
            $employees = $this->attendance->findEmployees();
            $devices = $this->scanHistory->findDevices();
            if ($errors === []) {
                $totalRows = $this->scanHistory->countFiltered($filters);
                $totalPages = max(1, (int)ceil($totalRows / $limit));
                $page = min($page, $totalPages);
                $scanRows = $this->scanHistory->findPaginated($filters, $limit, ($page - 1) * $limit);
            }
        } catch (Throwable $exception) {
            error_log('Scan history page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải lịch sử quét. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        $activeTab = 'scan_history';
        $pageTitle = 'Lịch sử quét thất bại';
        require __DIR__ . '/../View/attendance.php';
    }

    /** Trả ảnh vào/ra của một bản ghi; chỉ Admin được truy cập và binary không lưu lại thành file. */
    public function sendEvidence(string $type): void
    {
        AuthController::requireAdmin();
        $attendanceId = filter_var(
            $_GET['id'] ?? null,
            FILTER_VALIDATE_INT,
            ['options' => ['min_range' => 1]]
        );
        if (!is_int($attendanceId) || !in_array($type, ['in', 'out'], true)) {
            http_response_code(404);
            exit('Không tìm thấy ảnh bằng chứng.');
        }

        try {
            $image = $this->attendance->findEvidence($attendanceId, $type);
        } catch (Throwable $exception) {
            error_log('Attendance evidence read failed: ' . $exception->getMessage());
            http_response_code(500);
            exit('Không thể tải ảnh bằng chứng.');
        }

        if ($image === null) {
            http_response_code(404);
            exit('Không tìm thấy ảnh bằng chứng.');
        }

        $mimeType = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);
        if (!is_string($mimeType) || !str_starts_with($mimeType, 'image/')) {
            http_response_code(404);
            exit('Dữ liệu ảnh không hợp lệ.');
        }

        header('Content-Type: ' . $mimeType);
        header('Content-Length: ' . strlen($image));
        header('Cache-Control: private, no-store');
        header('X-Content-Type-Options: nosniff');
        echo $image;
    }

    /** Return a scan JPEG only to Admin; raw image bytes never enter HTML. */
    public function sendScanHistoryImage(): void
    {
        AuthController::requireAdmin();
        $scanId = filter_var($_GET['id'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if (!is_int($scanId)) {
            http_response_code(404);
            exit('Không tìm thấy ảnh lần quét.');
        }

        try {
            $image = $this->scanHistory->findImageById($scanId);
        } catch (Throwable $exception) {
            error_log('Scan history image read failed: ' . $exception->getMessage());
            http_response_code(500);
            exit('Không thể tải ảnh lần quét.');
        }
        if ($image === null) {
            http_response_code(404);
            exit('Không tìm thấy ảnh lần quét.');
        }

        header('Content-Type: image/jpeg');
        header('Content-Length: ' . strlen($image));
        header('Cache-Control: private, no-store');
        header('X-Content-Type-Options: nosniff');
        echo $image;
    }

    /** Xử lý API chấm công: đọc MaNV/MaTB, lấy ảnh từ camera nội bộ và giao nghiệp vụ cho service. */
    public function recordApi(): void
    {
        $data = json_decode((string)file_get_contents('php://input'), true);
        if (!is_array($data) || $data === []) {
            $this->jsonResponse(['status' => 'error', 'message' => 'No JSON body'], 400);
            return;
        }

        if (!array_key_exists('MaNV', $data) || $data['MaNV'] === null || $data['MaNV'] === '') {
            $this->jsonResponse(['status' => 'error', 'message' => 'Thiếu MaNV'], 400);
            return;
        }
        $employeeId = filter_var($data['MaNV'], FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $deviceId = filter_var($data['MaTB'] ?? 1, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if (!is_int($employeeId) || !is_int($deviceId)) {
            $this->jsonResponse(['status' => 'error', 'message' => 'MaNV hoặc MaTB không hợp lệ'], 400);
            return;
        }

        $image = $this->camera->captureJpeg();
        $result = $this->service->process($employeeId, $deviceId, $image);
        $this->jsonResponse($result, ($result['status'] ?? 'error') === 'success' ? 200 : 400);
    }

    private function calculateStatuses(?string $shiftStart, ?string $shiftEnd, ?string $checkIn, ?string $checkOut): array
    {
        if ($checkIn === null || $checkIn === '') {
            return ['entry' => 'Chưa chấm công', 'exit' => '--'];
        }

        $entryTime = (new DateTimeImmutable($checkIn))->format('H:i:s');
        $startTime = $shiftStart === null ? null : (new DateTimeImmutable($shiftStart))->format('H:i:s');
        $entryStatus = $startTime !== null && $entryTime > $startTime ? 'Đi trễ' : 'Đúng giờ';

        if ($checkOut === null || $checkOut === '') {
            return ['entry' => $entryStatus, 'exit' => 'Đang làm việc'];
        }

        $exitTime = (new DateTimeImmutable($checkOut))->format('H:i:s');
        $endTime = $shiftEnd === null ? null : (new DateTimeImmutable($shiftEnd))->format('H:i:s');
        $exitStatus = $endTime !== null && $exitTime < $endTime ? 'Về sớm' : 'Đúng giờ';

        return ['entry' => $entryStatus, 'exit' => $exitStatus];
    }

    private function isValidDate(string $value): bool
    {
        $date = DateTimeImmutable::createFromFormat('!Y-m-d', $value);
        $errors = DateTimeImmutable::getLastErrors();

        return $date !== false
            && $date->format('Y-m-d') === $value
            && ($errors === false || ($errors['warning_count'] === 0 && $errors['error_count'] === 0));
    }

    private function jsonResponse(array $payload, int $status): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    }
}
