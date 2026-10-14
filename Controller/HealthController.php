<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/HealthModel.php';
require_once __DIR__ . '/AuthController.php';

final class HealthController
{
    private const PAGE_SIZES = [5, 10, 20, 50];

    private HealthModel $health;

    public function __construct()
    {
        $this->health = new HealthModel();
    }

    public function index(): void
    {
        AuthController::requireAdmin();

        $filters = [
            'from_date' => $this->queryText('from_date'),
            'to_date' => $this->queryText('to_date'),
            'employee_id' => null,
            'keyword' => $this->queryText('keyword'),
        ];
        $errors = [];
        $this->validateDates($filters, $errors);

        if (strlen($filters['keyword']) > 400) {
            $filters['keyword'] = '';
            $errors['keyword'] = 'Từ khóa tối đa 100 ký tự.';
        }

        $employeeInput = $this->queryText('employee_id');
        if ($employeeInput !== '') {
            $employeeId = filter_var($employeeInput, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
            if (is_int($employeeId)) {
                $filters['employee_id'] = $employeeId;
            } else {
                $errors['employee_id'] = 'Mã nhân viên không hợp lệ.';
            }
        }

        $pageSizeInput = filter_var($this->queryText('per_page') ?: '20', FILTER_VALIDATE_INT);
        $pageSize = is_int($pageSizeInput) && in_array($pageSizeInput, self::PAGE_SIZES, true)
            ? $pageSizeInput
            : 20;
        $pageInput = filter_var($this->queryText('page') ?: '1', FILTER_VALIDATE_INT);
        $page = is_int($pageInput) && $pageInput > 0 && $pageInput <= 1000000 ? $pageInput : 1;

        $employees = $records = $chartData = [];
        $totalRows = 0;
        $error = null;
        try {
            $employees = $this->health->findEmployees();
            if ($filters['employee_id'] !== null && !$this->employeeExists($employees, $filters['employee_id'])) {
                $filters['employee_id'] = null;
                $errors['employee_id'] = 'Không tìm thấy nhân viên.';
            }
            $result = $this->health->findHistory($filters, $page, $pageSize);
            $totalRows = $result['total'];
            $totalPages = max(1, (int)ceil($totalRows / $pageSize));
            $page = min($page, $totalPages);
            if ($page !== (int)($pageInput ?: 1)) {
                $result = $this->health->findHistory($filters, $page, $pageSize);
            }
            $records = $result['records'];
            $chartData = $this->health->findChartData(20);
        } catch (Throwable $exception) {
            error_log('Health page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải dữ liệu sức khỏe. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        $totalPages = max(1, (int)ceil($totalRows / $pageSize));
        $pageTitle = 'Sức khỏe nhân viên | Smart Attendance';
        require __DIR__ . '/../View/health.php';
    }

    private function validateDates(array &$filters, array &$errors): void
    {
        foreach (['from_date', 'to_date'] as $key) {
            if ($filters[$key] !== '' && !$this->isValidDate($filters[$key])) {
                $filters[$key] = '';
                $errors[$key] = 'Ngày không hợp lệ.';
            }
        }
        if ($filters['from_date'] !== '' && $filters['to_date'] !== '' && $filters['from_date'] > $filters['to_date']) {
            $errors['date_range'] = 'Ngày bắt đầu không được sau ngày kết thúc.';
            $filters['from_date'] = $filters['to_date'] = '';
        }
    }

    private function isValidDate(string $value): bool
    {
        $date = DateTimeImmutable::createFromFormat('!Y-m-d', $value);
        $errors = DateTimeImmutable::getLastErrors();

        return $date !== false
            && $date->format('Y-m-d') === $value
            && ($errors === false || ($errors['warning_count'] === 0 && $errors['error_count'] === 0));
    }

    private function queryText(string $key): string
    {
        $value = $_GET[$key] ?? '';

        return is_string($value) || is_numeric($value) ? trim((string)$value) : '';
    }

    private function employeeExists(array $employees, int $employeeId): bool
    {
        foreach ($employees as $employee) {
            if ((int)$employee['MaNV'] === $employeeId) {
                return true;
            }
        }

        return false;
    }
}
