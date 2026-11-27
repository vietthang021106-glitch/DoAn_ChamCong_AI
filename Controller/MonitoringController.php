<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/HealthModel.php';
require_once __DIR__ . '/AuthController.php';

final class MonitoringController
{
    private const PAGE_SIZES = [5, 10, 20, 50];

    private HealthModel $health;

    public function __construct()
    {
        $this->health = new HealthModel();
    }

    /** Hiển thị lịch sử sức khỏe và biểu đồ nhịp tim cho Admin. */
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
        if (mb_strlen($filters['keyword'], 'UTF-8') > 100) {
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
        $healthPage = $this->pageNumber('health_page');
        $employees = $healthRows = $chartData = [];
        $totalHealthRows = 0;
        $error = null;

        try {
            $employees = $this->health->findEmployees();
            if ($filters['employee_id'] !== null && !$this->employeeExists($employees, $filters['employee_id'])) {
                $filters['employee_id'] = null;
                $errors['employee_id'] = 'Không tìm thấy nhân viên.';
            }

            $healthResult = $this->health->findHistory($filters, $healthPage, $pageSize);
            $totalHealthRows = $healthResult['total'];
            $totalHealthPages = max(1, (int)ceil($totalHealthRows / $pageSize));
            $healthPage = min($healthPage, $totalHealthPages);
            if ($healthPage !== $this->pageNumber('health_page')) {
                $healthResult = $this->health->findHistory($filters, $healthPage, $pageSize);
            }
            $healthRows = $healthResult['records'];
            $chartData = $this->health->findChartData($filters, 20);
        } catch (Throwable $exception) {
            error_log('Health page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải dữ liệu sức khỏe. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        $totalHealthPages = max(1, (int)ceil($totalHealthRows / $pageSize));
        $pageTitle = 'Sức khỏe';
        require __DIR__ . '/../View/monitoring.php';
    }

    private function pageNumber(string $key): int
    {
        $page = filter_var($this->queryText($key) ?: '1', FILTER_VALIDATE_INT);

        return is_int($page) && $page > 0 && $page <= 1000000 ? $page : 1;
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
