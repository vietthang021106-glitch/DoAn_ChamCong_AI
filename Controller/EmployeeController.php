<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';
require_once __DIR__ . '/../Controller/AuthController.php';
require_once __DIR__ . '/../Security/CsrfToken.php';
require_once __DIR__ . '/../Service/AiClient.php';
require_once __DIR__ . '/../Model/DeviceModel.php';
require_once __DIR__ . '/../Service/AttendanceCameraBinding.php';

final class EmployeeController
{
    private EmployeeModel $employees;
    private FaceEmbeddingModel $faceEmbeddings;

    public function __construct()
    {
        $this->employees = new EmployeeModel();
        $this->faceEmbeddings = new FaceEmbeddingModel();
    }

    /** Đọc hồ sơ nhân viên thực tế và trạng thái đăng ký khuôn mặt cho trang quản trị. */
    public function index(): void
    {
        AuthController::requireAdmin();

        $employees = [];
        $error = null;
        $successMessage = $_SESSION['employee_success'] ?? null;
        $deleteErrorMessage = $_SESSION['employee_error'] ?? null;
        $deleteWarningMessage = $_SESSION['employee_warning'] ?? null;
        unset($_SESSION['employee_success']);
        unset($_SESSION['employee_error'], $_SESSION['employee_warning']);
        $csrfToken = CsrfToken::token();

        try {
            $employees = $this->employees->findAll();
        } catch (Throwable $exception) {
            error_log('Employee page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải danh sách nhân viên. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        require __DIR__ . '/../View/employees.php';
    }

    /** Permanently delete an employee only when no face or historical data is linked. */
    public function delete(): void
    {
        AuthController::requireAdmin();
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            header('Allow: POST');
            http_response_code(405);
            exit('Method Not Allowed');
        }
        if (!CsrfToken::isValid()) {
            http_response_code(400);
            exit('Yêu cầu không hợp lệ. Vui lòng tải lại trang và thử lại.');
        }
        unset($_SESSION['employee_error'], $_SESSION['employee_warning'], $_SESSION['employee_success']);

        $employeeId = filter_var(
            $_POST['MaNV'] ?? null,
            FILTER_VALIDATE_INT,
            ['options' => ['min_range' => 1]]
        );
        if (!is_int($employeeId)) {
            $_SESSION['employee_error'] = 'Mã nhân viên không hợp lệ.';
            $this->redirectToList();
        }
        $employeeCode = 'NV' . str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT);
        try {
            $result = $this->employees->deleteIfUnreferenced($employeeId);
            if ($result === EmployeeModel::DELETE_NOT_FOUND) {
                $_SESSION['employee_error'] = 'Không tìm thấy nhân viên ' . $employeeCode . ' hoặc nhân viên đã được xóa.';
                $this->redirectToList();
            }
            if ($result === EmployeeModel::DELETE_FACE_REGISTERED) {
                $_SESSION['employee_error'] = 'Không thể xóa nhân viên ' . $employeeCode
                    . ' vì đã đăng ký khuôn mặt. Hãy xóa đăng ký khuôn mặt bằng chức năng hiện có trước.';
                $this->redirectToList();
            }
            if ($result === EmployeeModel::DELETE_HAS_RELATED_DATA) {
                $_SESSION['employee_error'] = 'Không thể xóa nhân viên ' . $employeeCode
                    . ' vì còn dữ liệu liên quan. Không có lịch sử hoặc dữ liệu nào bị xóa.';
                $this->redirectToList();
            }

            $_SESSION['employee_success'] = 'Đã xóa nhân viên ' . $employeeCode . '.';
            try {
                $refresh = (new AiClient())->refreshGallery();
                if (($refresh['success'] ?? false) !== true) {
                    $_SESSION['employee_warning'] = 'Đã xóa nhân viên ' . $employeeCode
                        . ', nhưng AI chưa xác nhận tải lại gallery. Hãy làm mới dịch vụ AI trước khi tiếp tục nhận diện.';
                }
            } catch (Throwable $exception) {
                error_log('AI gallery refresh after employee delete failed: ' . $exception->getMessage());
                $_SESSION['employee_warning'] = 'Đã xóa nhân viên ' . $employeeCode
                    . ', nhưng chưa thể đồng bộ gallery AI. Hãy làm mới dịch vụ AI trước khi tiếp tục nhận diện.';
            }
            $this->redirectToList();
        } catch (Throwable $exception) {
            error_log('Employee delete failed: ' . $exception->getMessage());
            $_SESSION['employee_error'] = $this->isForeignKeyViolation($exception)
                ? 'Không thể xóa vì còn dữ liệu liên quan. Không có dữ liệu nào bị thay đổi.'
                : 'Không thể xóa nhân viên lúc này. Transaction đã được hoàn tác; vui lòng thử lại.';
            $this->redirectToList();
        }
    }

    public function createForm(array $values = [], array $errors = []): void
    {
        AuthController::requireAdmin();

        try {
            $this->renderForm('create', null, $values, $errors);
        } catch (Throwable $exception) {
            $this->handleFailure('Employee create form failed', $exception);
        }
    }

    /** Tạo hồ sơ nhân viên; nhân viên không có tài khoản đăng nhập Web. */
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
                $this->renderForm('create', null, $values, $errors);
                return;
            }

            $employeeId = $this->employees->createEmployee($values['HoTen']);
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

            $this->renderForm('edit', $employee);
        } catch (Throwable $exception) {
            $this->handleFailure('Employee edit form failed', $exception);
        }
    }

    /** Cập nhật hồ sơ nhân viên mà không thay đổi tài khoản đăng nhập Admin hoặc tài khoản cũ. */
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
                $this->renderForm('edit', $employee, $values, $errors);
                return;
            }

            $this->employees->updateEmployee($employeeId, $values['HoTen']);
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
            'HoTen' => trim($this->postString('HoTen')),
        ];
    }

    private function postString(string $key): string
    {
        return is_string($_POST[$key] ?? null) ? $_POST[$key] : '';
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

        return $errors;
    }

    private function isForeignKeyViolation(Throwable $exception): bool
    {
        for ($current = $exception; $current !== null; $current = $current->getPrevious()) {
            if (!$current instanceof PDOException) {
                continue;
            }
            $sqlState = (string)($current->errorInfo[0] ?? $current->getCode());
            $nativeCode = (int)($current->errorInfo[1] ?? 0);
            if ($sqlState === '23000' && in_array($nativeCode, [19, 1451, 1452], true)) {
                return true;
            }
        }
        return false;
    }

    private function renderForm(
        string $mode,
        ?array $employee,
        array $values = [],
        array $errors = []
    ): void {
        $csrfToken = CsrfToken::token();
        $attendanceDevices = [];
        $attendanceCameraDeviceId = null;
        try {
            $attendanceDevices = (new DeviceModel())->findAll();
            $attendanceCameraDeviceId = AttendanceCameraBinding::deviceId($attendanceDevices);
        } catch (Throwable $exception) {
            error_log('Employee face-enrollment device lookup failed.');
        }
        $faceSamples = $mode === 'edit' && $employee !== null
            ? $this->faceEmbeddings->findByEmployee((int)$employee['MaNV'])
            : [];
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
