<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/DeviceModel.php';
require_once __DIR__ . '/AuthController.php';

final class DeviceController
{
    /** Hiển thị danh sách thiết bị đã khai báo, không điều khiển thiết bị. */
    public function index(): void
    {
        AuthController::requireAdmin();

        $devices = [];
        $error = null;
        try {
            $devices = (new DeviceModel())->findAll();
        } catch (Throwable $exception) {
            error_log('Device list read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải danh sách thiết bị. Vui lòng thử lại sau.';
        }

        $pageTitle = 'Thiết bị';
        require __DIR__ . '/../View/devices.php';
    }
}
