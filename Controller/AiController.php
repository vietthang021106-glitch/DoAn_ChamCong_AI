<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';
require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Service/AiClient.php';
require_once __DIR__ . '/AuthController.php';
require_once __DIR__ . '/../Security/CsrfToken.php';

final class AiController
{
    private FaceEmbeddingModel $embeddings;
    private EmployeeModel $employees;
    private AiClient $ai;

    public function __construct()
    {
        $this->embeddings = new FaceEmbeddingModel();
        $this->employees = new EmployeeModel();
        $this->ai = new AiClient();
    }

    public function internalFaceGallery(): void
    {
        if (!$this->isLoopbackRequest()) {
            $this->jsonResponse(['success' => false, 'message' => 'Local requests only.'], 403);
            return;
        }

        try {
            $this->jsonResponse([
                'success' => true,
                'embeddings' => $this->embeddings->findAllForInternalGallery(),
            ]);
        } catch (Throwable $exception) {
            error_log('Internal face gallery read failed.');
            $this->jsonResponse(['success' => false, 'message' => 'Không thể tải gallery khuôn mặt.'], 503);
        }
    }

    public function index(): void
    {
        AuthController::requireAdmin();
        $pageTitle = 'Camera AI | Smart Attendance';
        $csrfToken = CsrfToken::token();
        try {
            $health = $this->ai->health();
        } catch (Throwable $exception) {
            $health = ['success' => false, 'service' => 'python-ai'];
        }

        require __DIR__ . '/../View/ai_camera.php';
    }

    public function cameraFrame(): void
    {
        AuthController::requireAdmin();
        try {
            header('Content-Type: image/jpeg');
            header('Cache-Control: no-store');
            echo $this->ai->cameraFrame();
        } catch (Throwable $exception) {
            http_response_code(503);
            header('Content-Type: text/plain; charset=utf-8');
            echo 'Camera không khả dụng.';
        }
    }

    public function recognize(): void
    {
        AuthController::requireAdmin();
        if (!CsrfToken::isValid()) {
            $this->jsonResponse(['success' => false, 'message' => 'Yêu cầu không hợp lệ.'], 400);
            return;
        }

        try {
            $result = $this->ai->recognize();
            if (!empty($result['match']) && isset($result['ma_nv'])) {
                $employee = $this->employees->findById((int)$result['ma_nv']);
                $result['ho_ten'] = $employee['HoTen'] ?? null;
            } else {
                $result['ho_ten'] = null;
            }
            $this->jsonResponse($result);
        } catch (Throwable $exception) {
            $this->jsonResponse([
                'success' => false,
                'match' => false,
                'ma_nv' => null,
                'score' => null,
                'message' => 'Không thể kết nối AI service hoặc camera.',
            ], 503);
        }
    }

    private function isLoopbackRequest(): bool
    {
        return in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1', '::ffff:127.0.0.1'], true);
    }

    private function jsonResponse(array $payload, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
    }
}
