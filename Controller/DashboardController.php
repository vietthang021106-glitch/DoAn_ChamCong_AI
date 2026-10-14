<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/DashboardModel.php';
require_once __DIR__ . '/AuthController.php';

final class DashboardController
{
    private DashboardModel $dashboard;

    public function __construct()
    {
        $this->dashboard = new DashboardModel();
    }

    public function index(): void
    {
        AuthController::requireAdmin();

        $today = (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))
            ->format('Y-m-d');
        $error = null;

        try {
            $dashboard = $this->dashboard->findOverview($today);
        } catch (Throwable $exception) {
            error_log('Dashboard read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải dữ liệu tổng quan. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
            $dashboard = [
                'date' => $today,
                'summary' => [
                    'total_employees' => 0,
                    'face_embeddings' => 0,
                    'face_registered' => 0,
                    'face_missing' => 0,
                    'assigned_today' => 0,
                    'checked_in' => 0,
                    'on_time' => 0,
                    'working' => 0,
                    'late' => 0,
                    'early' => 0,
                    'not_checked' => 0,
                ],
                'attendance' => [],
                'weekly' => [],
                'environment' => null,
                'health' => ['latest' => null, 'today_count' => 0],
                'alerts' => [],
            ];
        }

        $pageTitle = 'Tổng quan | Smart Attendance';
        require __DIR__ . '/../View/dashboard.php';
    }
}
