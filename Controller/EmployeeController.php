<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Controller/AuthController.php';
require_once __DIR__ . '/../Security/CsrfToken.php';

final class EmployeeController
{
    private EmployeeModel $employees;

    public function __construct()
    {
        $this->employees = new EmployeeModel();
    }

    public function index(): void
    {
        AuthController::requireAdmin();

        $employees = [];
        $error = null;
        $stats = [
            'total' => 0,
            'registered' => 0,
            'not_registered' => 0,
        ];
        $successMessage = $_SESSION['employee_success'] ?? null;
        unset($_SESSION['employee_success']);

        try {
            $employees = $this->employees->findAll();
            $stats['total'] = count($employees);
            foreach ($employees as $employee) {
                if ((int)$employee['FaceRegistered'] === 1) {
                    $stats['registered']++;
                }
            }
            $stats['not_registered'] = $stats['total'] - $stats['registered'];
        } catch (Throwable $exception) {
            error_log('Employee page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải danh sách nhân viên. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        require __DIR__ . '/../View/employees.php';
    }

    public function createForm(array $values = [], array $errors = []): void
    {
        AuthController::requireAdmin();

        try {
            $this->renderForm('create', null, $this->employees->findRoles(), $values, $errors);
        } catch (Throwable $exception) {
            $this->handleFailure('Employee create form failed', $exception);
        }
    }

    public function store(): void
    {
        AuthController::requireAdmin();

        if (!CsrfToken::isValid()) {
            http_response_code(400);
            exit('Yêu cầu không hợp lệ. Vui lòng tải lại trang và thử lại.');
        }

        $values = $this->submittedValues();

        try {
            $errors = $this->validateValues($values);
            if ($errors !== []) {
                http_response_code(422);
                $this->renderForm('create', null, $this->employees->findRoles(), $values, $errors);
                return;
            }

            $employeeId = $this->employees->create($values['HoTen'], $values['MaVaiTro']);
            $_SESSION['employee_success'] = 'Đã thêm nhân viên NV' . str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) . '.';
            $this->redirectToList();
        } catch (Throwable $exception) {
            $this->handleFailure('Employee create failed', $exception);
        }
    }

    public function editForm(int $employeeId): void
    {
        AuthController::requireAdmin();

        try {
            $employee = $this->employees->findById($employeeId);
            if ($employee === null) {
                $this->notFound();
                return;
            }

            $this->renderForm('edit', $employee, $this->employees->findRoles());
        } catch (Throwable $exception) {
            $this->handleFailure('Employee edit form failed', $exception);
        }
    }

    public function update(int $employeeId): void
    {
        AuthController::requireAdmin();

        if (!CsrfToken::isValid()) {
            http_response_code(400);
            exit('Yêu cầu không hợp lệ. Vui lòng tải lại trang và thử lại.');
        }

        $values = $this->submittedValues();

        try {
            $employee = $this->employees->findById($employeeId);
            if ($employee === null) {
                $this->notFound();
                return;
            }

            $errors = $this->validateValues($values);
            if ($errors !== []) {
                http_response_code(422);
                $this->renderForm('edit', $employee, $this->employees->findRoles(), $values, $errors);
                return;
            }

            $this->employees->update($employeeId, $values['HoTen'], $values['MaVaiTro']);
            $_SESSION['employee_success'] = 'Đã cập nhật nhân viên NV' . str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) . '.';
            $this->redirectToList();
        } catch (Throwable $exception) {
            $this->handleFailure('Employee update failed', $exception);
        }
    }

    public function requestedEmployeeId(): int
    {
        AuthController::requireAdmin();

        $employeeId = filter_var(
            $_GET['id'] ?? null,
            FILTER_VALIDATE_INT,
            ['options' => ['min_range' => 1]]
        );

        if ($employeeId === false) {
            $this->notFound();
        }

        return (int)$employeeId;
    }

    private function submittedValues(): array
    {
        return [
            'HoTen' => trim((string)($_POST['HoTen'] ?? '')),
            'MaVaiTro' => filter_var(
                $_POST['MaVaiTro'] ?? null,
                FILTER_VALIDATE_INT,
                ['options' => ['min_range' => 1]]
            ),
        ];
    }

    private function validateValues(array $values): array
    {
        $errors = [];
        $name = $values['HoTen'];
        $nameLength = preg_match_all('/./us', $name, $matches);

        if ($name === '') {
            $errors['HoTen'] = 'Vui lòng nhập họ tên.';
        } elseif ($nameLength === false) {
            $errors['HoTen'] = 'Họ tên chứa ký tự không hợp lệ.';
        } elseif ($nameLength > 100) {
            $errors['HoTen'] = 'Họ tên không được vượt quá 100 ký tự.';
        }

        $roleId = $values['MaVaiTro'];
        if (!is_int($roleId) || !$this->employees->roleExists($roleId)) {
            $errors['MaVaiTro'] = 'Vui lòng chọn vai trò hợp lệ.';
        }

        return $errors;
    }

    private function renderForm(
        string $mode,
        ?array $employee,
        array $roles,
        array $values = [],
        array $errors = []
    ): void {
        $csrfToken = CsrfToken::token();
        require __DIR__ . '/../View/employee_form.php';
    }

    private function redirectToList(): void
    {
        header('Location: /', true, 303);
        exit;
    }

    private function notFound(): void
    {
        http_response_code(404);
        echo 'Không tìm thấy nhân viên.';
        exit;
    }

    private function handleFailure(string $context, Throwable $exception): void
    {
        error_log($context . ': ' . $exception->getMessage());
        http_response_code(500);
        echo 'Không thể xử lý yêu cầu lúc này. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
    }
}
