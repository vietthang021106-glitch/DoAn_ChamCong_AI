<?php
declare(strict_types=1);

require_once __DIR__ . '/Security/CsrfToken.php';

if (session_status() !== PHP_SESSION_ACTIVE) {
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');
    $isHttps = isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== '' && $_SERVER['HTTPS'] !== 'off';
    session_set_cookie_params([
        'lifetime' => 0,
        'path' => '/',
        'secure' => $isHttps,
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
    session_start();
}

CsrfToken::token();

require_once __DIR__ . '/Controller/AuthController.php';
require_once __DIR__ . '/Controller/EmployeeController.php';
require_once __DIR__ . '/Controller/DashboardController.php';
require_once __DIR__ . '/Controller/ShiftController.php';
require_once __DIR__ . '/Controller/AttendanceController.php';
require_once __DIR__ . '/Controller/AiController.php';
require_once __DIR__ . '/Controller/HealthController.php';
require_once __DIR__ . '/Controller/AlertController.php';
require_once __DIR__ . '/Controller/MyController.php';

$authController = new AuthController();
$controller = new EmployeeController();
$dashboardController = new DashboardController();
$shiftController = new ShiftController();
$attendanceController = new AttendanceController();
$aiController = new AiController();
$healthController = new HealthController();
$alertController = new AlertController();
$myController = new MyController();
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$action = $_GET['action'] ?? 'index';
$requestPath = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';

if ($requestPath === '/api/chamcong') {
    if ($method !== 'POST') {
        header('Allow: POST');
        http_response_code(405);
        exit('Method Not Allowed');
    }
    $attendanceController->recordApi();
    return;
}

if ($action === 'internal_face_gallery' && $method === 'GET') {
    $aiController->internalFaceGallery();
    return;
}

if ($action === 'ai_camera' && $method === 'GET') {
    $aiController->index();
    return;
}

if ($action === 'ai_camera_frame' && $method === 'GET') {
    $aiController->cameraFrame();
    return;
}

if ($action === 'ai_recognize' && $method === 'POST') {
    $aiController->recognize();
    return;
}

if ($action === 'login' && $method === 'GET') {
    $authController->showLogin();
    return;
}

if ($action === 'login' && $method === 'POST') {
    $authController->login();
    return;
}

if ($action === 'logout' && $method === 'POST') {
    $authController->logout();
    return;
}

if ($action === 'index' && $method === 'GET') {
    $controller->index();
    return;
}

if ($action === 'dashboard' && $method === 'GET') {
    $dashboardController->index();
    return;
}

if ($action === 'create' && $method === 'GET') {
    $controller->createForm();
    return;
}

if ($action === 'store' && $method === 'POST') {
    $controller->store();
    return;
}

if ($action === 'edit' && $method === 'GET') {
    $controller->editForm($controller->requestedEmployeeId());
    return;
}

if ($action === 'update' && $method === 'POST') {
    $controller->update($controller->requestedEmployeeId());
    return;
}

if ($action === 'shifts' && $method === 'GET') {
    $shiftController->index();
    return;
}

if ($action === 'assign_shift' && $method === 'POST') {
    $shiftController->assign();
    return;
}

if ($action === 'attendance' && $method === 'GET') {
    $attendanceController->index();
    return;
}

if ($action === 'health' && $method === 'GET') {
    $healthController->index();
    return;
}

if ($action === 'alerts' && $method === 'GET') {
    $alertController->index();
    return;
}

if ($action === 'my' && $method === 'GET') {
    $myController->index();
    return;
}

if (in_array($action, ['my_attendance_image_in', 'my_attendance_image_out'], true) && $method === 'GET') {
    $myController->sendEvidence($action === 'my_attendance_image_in' ? 'in' : 'out');
    return;
}

if ($action === 'attendance_image_in' && $method === 'GET') {
    $attendanceController->sendEvidence('in');
    return;
}

if ($action === 'attendance_image_out' && $method === 'GET') {
    $attendanceController->sendEvidence('out');
    return;
}

if (in_array($action, ['index', 'dashboard', 'create', 'store', 'edit', 'update', 'login', 'logout', 'shifts', 'assign_shift', 'attendance', 'health', 'alerts', 'attendance_image_in', 'attendance_image_out', 'my', 'my_attendance_image_in', 'my_attendance_image_out', 'internal_face_gallery', 'ai_camera', 'ai_camera_frame', 'ai_recognize'], true)) {
    $allowedMethods = match ($action) {
        'login' => 'GET, POST',
        'store', 'update', 'logout', 'assign_shift', 'ai_recognize' => 'POST',
        'internal_face_gallery', 'ai_camera', 'ai_camera_frame', 'attendance_image_in', 'attendance_image_out', 'my', 'my_attendance_image_in', 'my_attendance_image_out', 'health', 'alerts' => 'GET',
        default => 'GET',
    };
    header('Allow: ' . $allowedMethods);
    http_response_code(405);
    exit('Method Not Allowed');
}

http_response_code(404);
echo 'Không tìm thấy trang được yêu cầu.';
