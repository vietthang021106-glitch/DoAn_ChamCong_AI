<?php
declare(strict_types=1);

$assert = static function (bool $condition, string $message): void {
    if (!$condition) {
        fwrite(STDERR, "FAIL: {$message}\n");
        exit(1);
    }
    echo "PASS: {$message}\n";
};

$root = dirname(__DIR__);
$alertModel = $root . '/Model/AlertModel.php';
$assert(!is_file($alertModel), 'dedicated AlertModel is removed');

$routeSource = file_get_contents($root . '/index.php');
$monitoringSource = file_get_contents($root . '/Controller/MonitoringController.php');
$dashboardSource = file_get_contents($root . '/Model/DashboardModel.php');
$mySource = file_get_contents($root . '/Model/MyModel.php');
$healthView = file_get_contents($root . '/View/monitoring.php');
$assert(is_string($routeSource) && !str_contains($routeSource, "'alerts'"), 'PHP front controller has no alerts action');
$assert(is_string($monitoringSource) && !str_contains($monitoringSource, 'AlertModel'), 'health controller no longer depends on alert model');
$assert(is_string($dashboardSource) && !str_contains($dashboardSource, 'CanhBao'), 'dashboard query no longer reads alert records');
$assert(is_string($mySource) && !str_contains($mySource, 'CanhBao'), 'employee self-service query no longer reads alert records');
$assert(is_string($healthView) && str_contains($healthView, 'NhipTim') && str_contains($healthView, 'SpO₂'), 'health history still renders sensor measurements');

