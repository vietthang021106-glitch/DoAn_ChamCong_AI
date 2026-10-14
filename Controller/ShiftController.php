<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/ShiftModel.php';
require_once __DIR__ . '/AuthController.php';
require_once __DIR__ . '/../Security/CsrfToken.php';

final class ShiftController
{
    private ShiftModel $shifts;

    public function __construct()
    {
        $this->shifts = new ShiftModel();
    }

    public function index(): void
    {
        AuthController::requireAdmin();

        $today = (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))->format('Y-m-d');
        $selectedDate = trim((string)($_GET['date'] ?? $today));
        $errors = [];
        if (!$this->isValidDate($selectedDate)) {
            $selectedDate = $today;
            $errors['NgayLamViec'] = 'Ngày không hợp lệ.';
        }

        $formValues = [
            'MaNV' => '',
            'MaCa' => '',
            'NgayLamViec' => $selectedDate,
        ];
        $error = null;
        $successMessage = $_SESSION['shift_success'] ?? null;
        unset($_SESSION['shift_success']);

        try {
            $employees = $this->shifts->findEmployees();
            $availableShifts = $this->shifts->findAll();
            $assignments = $this->shifts->findAssignmentsByDate($selectedDate);
        } catch (Throwable $exception) {
            error_log('Shift page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $employees = $availableShifts = $assignments = [];
            $error = 'Không thể tải dữ liệu ca làm việc. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        $csrfToken = CsrfToken::token();
        $pageTitle = 'Phân ca nhân viên | Smart Attendance';
        require __DIR__ . '/../View/shifts.php';
    }

    public function assign(): void
    {
        AuthController::requireAdmin();

        if (!CsrfToken::isValid()) {
            http_response_code(400);
            exit('Yêu cầu không hợp lệ. Vui lòng tải lại trang và thử lại.');
        }

        $employeeId = filter_var($_POST['MaNV'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $shiftId = filter_var($_POST['MaCa'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $date = trim((string)($_POST['NgayLamViec'] ?? ''));
        $errors = [];

        if (!is_int($employeeId) || !$this->shifts->employeeExists($employeeId)) {
            $errors['MaNV'] = 'Vui lòng chọn nhân viên hợp lệ.';
        }
        if (!is_int($shiftId) || !$this->shifts->shiftExists($shiftId)) {
            $errors['MaCa'] = 'Vui lòng chọn ca làm việc hợp lệ.';
        }
        if (!$this->isValidDate($date)) {
            $errors['NgayLamViec'] = 'Vui lòng chọn ngày hợp lệ.';
        }

        if ($errors !== []) {
            $this->renderWithErrors([
                'MaNV' => is_int($employeeId) ? (string)$employeeId : '',
                'MaCa' => is_int($shiftId) ? (string)$shiftId : '',
                'NgayLamViec' => $date,
            ], $errors, $this->isValidDate($date) ? $date : null);
            return;
        }

        try {
            $this->shifts->saveAssignment($employeeId, $shiftId, $date);
            $_SESSION['shift_success'] = 'Đã lưu phân ca cho ngày ' . $date . '.';
            header('Location: /?action=shifts&date=' . rawurlencode($date), true, 303);
            exit;
        } catch (Throwable $exception) {
            error_log('Shift assignment failed: ' . $exception->getMessage());
            $this->renderWithErrors([
                'MaNV' => (string)$employeeId,
                'MaCa' => (string)$shiftId,
                'NgayLamViec' => $date,
            ], [], $date, 'Không thể lưu phân ca. Vui lòng thử lại.');
        }
    }

    private function renderWithErrors(array $formValues, array $errors, ?string $date, ?string $error = null): void
    {
        http_response_code($error === null ? 422 : 500);
        $this->indexWithState($formValues, $errors, $error);
    }

    private function indexWithState(array $formValues, array $errors, ?string $error): void
    {
        $today = (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))->format('Y-m-d');
        $selectedDate = $this->isValidDate((string)($formValues['NgayLamViec'] ?? ''))
            ? (string)$formValues['NgayLamViec']
            : $today;
        $successMessage = null;

        try {
            $employees = $this->shifts->findEmployees();
            $availableShifts = $this->shifts->findAll();
            $assignments = $this->shifts->findAssignmentsByDate($selectedDate);
        } catch (Throwable $exception) {
            error_log('Shift form reload failed: ' . $exception->getMessage());
            http_response_code(500);
            $employees = $availableShifts = $assignments = [];
            $error = 'Không thể tải dữ liệu ca làm việc. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        $csrfToken = CsrfToken::token();
        $pageTitle = 'Phân ca nhân viên | Smart Attendance';
        require __DIR__ . '/../View/shifts.php';
    }

    private function isValidDate(string $value): bool
    {
        $date = DateTimeImmutable::createFromFormat('!Y-m-d', $value);
        $errors = DateTimeImmutable::getLastErrors();

        return $date !== false
            && $date->format('Y-m-d') === $value
            && ($errors === false || ($errors['warning_count'] === 0 && $errors['error_count'] === 0));
    }
}
