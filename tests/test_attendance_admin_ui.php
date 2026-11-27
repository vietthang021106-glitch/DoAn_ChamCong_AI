<?php
declare(strict_types=1);

$_SESSION = [
    'user_id' => 1,
    'is_admin' => true,
    'display_name' => 'Admin',
    'role' => 'Admin',
    'employee_csrf_token' => 'test-token',
];
$_GET = ['action' => 'attendance'];

$activeTab = 'attendance';
$pageTitle = 'Chấm công';
$fromDate = '2026-11-27';
$toDate = '2026-11-27';
$employeeId = null;
$keyword = '';
$status = '';
$limit = 20;
$page = 1;
$totalPages = 1;
$employees = [];
$errors = [];
$error = null;
$attendanceRows = [];

ob_start();
require __DIR__ . '/../View/attendance.php';
$html = (string)ob_get_clean();

$checks = [
    'Attendance state filter is present' => str_contains($html, 'name="status"'),
    'Failed scan history remains reachable' => str_contains($html, 'tab=scan_history'),
    'Duplicate AI1 camera widget is absent' => !str_contains($html, 'data-ai1-recognition'),
    'Duplicate scan action is absent' => !str_contains($html, 'Bắt đầu quét'),
    'Duplicate live camera view is absent' => !str_contains($html, 'data-live-attendance'),
    'Device navigation item is absent' => !str_contains($html, '>Thiết bị</a>'),
    'Recognition script is not loaded on admin history' => !str_contains($html, 'face_recognition.js'),
];

foreach ($checks as $label => $passed) {
    if (!$passed) {
        fwrite(STDERR, "FAIL: {$label}.\n");
        exit(1);
    }
}

echo "PASS: compact attendance admin view, no duplicate scan UI, failed-scan link preserved.\n";
