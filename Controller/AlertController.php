<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/AlertModel.php';
require_once __DIR__ . '/AuthController.php';

final class AlertController
{
    private const PAGE_SIZES = [5, 10, 20, 50];

    private AlertModel $alerts;

    public function __construct()
    {
        $this->alerts = new AlertModel();
    }

    public function index(): void
    {
        AuthController::requireAdmin();

        $filters = [
            'from_date' => $this->queryText('from_date'),
            'to_date' => $this->queryText('to_date'),
            'employee_id' => null,
            'category' => $this->queryText('category'),
        ];
        $errors = [];
        $this->validateDates($filters, $errors);

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

        $employees = $categories = $records = [];
        $totalRows = 0;
        $error = null;
        try {
            $employees = $this->alerts->findEmployees();
            $categories = $this->alerts->findCategories();
            if ($filters['employee_id'] !== null && !$this->employeeExists($employees, $filters['employee_id'])) {
                $filters['employee_id'] = null;
                $errors['employee_id'] = 'Không tìm thấy nhân viên.';
            }
            if ($filters['category'] !== '' && !$this->categoryExists($categories, $filters['category'])) {
                $filters['category'] = '';
                $errors['category'] = 'Loại cảnh báo không hợp lệ.';
            }

            $result = $this->alerts->findAlerts($filters, $page, $pageSize);
            $totalRows = $result['total'];
            $totalPages = max(1, (int)ceil($totalRows / $pageSize));
            $page = min($page, $totalPages);
            if ($page !== (int)($pageInput ?: 1)) {
                $result = $this->alerts->findAlerts($filters, $page, $pageSize);
            }
            $records = $result['records'];
        } catch (Throwable $exception) {
            error_log('Alert page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải dữ liệu cảnh báo. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        $totalPages = max(1, (int)ceil($totalRows / $pageSize));
        $pageTitle = 'Cảnh báo | Smart Attendance';
        require __DIR__ . '/../View/alerts.php';
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

    private function categoryExists(array $categories, string $category): bool
    {
        foreach ($categories as $item) {
            if ((string)$item['LoaiCanhBao'] === $category) {
                return true;
            }
        }

        return false;
    }
}
