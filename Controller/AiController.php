<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';
require_once __DIR__ . '/AuthController.php';
require_once __DIR__ . '/../Security/CsrfToken.php';
require_once __DIR__ . '/../Service/AiClient.php';

final class AiController
{
    private FaceEmbeddingModel $embeddings;

    public function __construct()
    {
        $this->embeddings = new FaceEmbeddingModel();
    }

    /** Phục vụ gallery cho Python AI qua request loopback; không lộ credential DB. */
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

    /** Start a read-only AI1 scan; this endpoint never writes attendance. */
    public function startRecognitionSession(): void
    {
        AuthController::requireAdmin();
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            $this->jsonResponse(['success' => false, 'message' => 'Method Not Allowed.'], 405);
        }
        if (!CsrfToken::isValid()) {
            $this->jsonResponse(['success' => false, 'message' => 'Phiên biểu mẫu hết hạn. Tải lại trang và thử lại.'], 400);
        }
        try {
            $result = (new AiClient())->startRecognitionSession();
            $status = !empty($result['success']) ? 202 : (!empty($result['busy']) ? 409 : 503);
            $this->jsonResponse($result, $status);
        } catch (Throwable $exception) {
            error_log('AI1 recognition session start failed: ' . $exception->getMessage());
            $this->jsonResponse(['success' => false, 'message' => 'AI1 chưa sẵn sàng để nhận diện.'], 503);
        }
    }

    /** Return authorized live scan progress/result to the Admin UI. */
    public function recognitionSessionStatus(): void
    {
        AuthController::requireAdmin();
        $sessionId = (string)($_GET['session_id'] ?? '');
        if (!preg_match('/^[a-f0-9]{32}$/D', $sessionId)) {
            $this->jsonResponse(['success' => false, 'message' => 'Mã phiên nhận diện không hợp lệ.'], 400);
        }
        try {
            $result = (new AiClient())->recognitionSessionStatus($sessionId);
            $this->jsonResponse($result, !empty($result['success']) ? 200 : 404);
        } catch (Throwable $exception) {
            error_log('AI1 recognition session status failed: ' . $exception->getMessage());
            $this->jsonResponse(['success' => false, 'message' => 'Không thể đọc trạng thái nhận diện.'], 503);
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
        header('Cache-Control: private, no-store');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
        exit;
    }

}
