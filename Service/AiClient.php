<?php
declare(strict_types=1);

final class AiClient
{
    private const BASE_URL = 'http://127.0.0.1:5001';

    /** Đọc trạng thái AI service nội bộ, không khởi chạy process Python mới. */
    public function health(): array
    {
        return $this->requestJson('GET', '/health');
    }

    /** Yêu cầu AI service tải lại gallery từ endpoint nội bộ PHP. */
    public function refreshGallery(): array
    {
        return $this->requestJson('POST', '/api/ai/gallery/refresh');
    }

    /** Gửi JPEG enrollment tới AI để kiểm tra pose mà chưa nhận sample lưu trữ. */
    public function inspectEnrollmentImage(string $jpeg, string $expectedPose): array
    {
        return $this->requestEnrollmentJson('/api/ai/enrollment/inspect', $jpeg, $expectedPose);
    }

    /** Yêu cầu AI trả embedding và đúng JPEG đã dùng cho capture enrollment. */
    public function captureEnrollmentSample(string $jpeg, string $expectedPose, ?string $referenceVector = null): array
    {
        return $this->requestEnrollmentJson('/api/ai/enrollment/capture', $jpeg, $expectedPose, $referenceVector);
    }

    /** Gửi JPEG tĩnh để AI service từ chối nhận diện thiếu ba snapshot, không ghi dữ liệu nghiệp vụ. */
    public function recognizeJpeg(string $jpeg): array
    {
        $context = stream_context_create([
            'http' => [
                'method' => 'POST',
                'header' => "Accept: application/json\r\nContent-Type: image/jpeg\r\n",
                'content' => $jpeg,
                'timeout' => 20,
                'ignore_errors' => true,
            ],
        ]);
        $body = @file_get_contents(self::BASE_URL . '/api/ai/recognize-image', false, $context);
        if (!is_string($body)) {
            throw new RuntimeException('AI service is unavailable.');
        }

        $response = json_decode($body, true);
        if (!is_array($response)) {
            throw new RuntimeException('AI service returned an invalid recognition response.');
        }

        return $response;
    }

    /** Start a three-fresh-frame AI1 recognition session. */
    public function startRecognitionSession(): array
    {
        return $this->requestJson('POST', '/api/ai/recognition-sessions');
    }

    /** Read one recognition session's progress or terminal result. */
    public function recognitionSessionStatus(string $sessionId): array
    {
        if (!preg_match('/^[a-f0-9]{32}$/D', $sessionId)) {
            throw new InvalidArgumentException('Recognition session ID is invalid.');
        }
        return $this->requestJson('GET', '/api/ai/recognition-sessions/' . $sessionId);
    }

    /** Start Smart Enrollment v2 on the shared camera singleton. */
    public function startEnrollmentSession(): array
    {
        return $this->requestJson('POST', '/api/ai/enrollment-sessions');
    }

    /** Reserve the shared camera while Admin completes manual enrollment poses. */
    public function startManualEnrollmentLock(): array
    {
        return $this->requestJson('POST', '/api/ai/enrollment-manual-lock');
    }

    /** Read progress for an AI-owned five-pose enrollment session. */
    public function enrollmentSessionStatus(string $sessionId): array
    {
        return $this->requestJson('GET', $this->enrollmentSessionPath($sessionId));
    }

    /** Fetch only the five selected, validated samples after Admin confirmation is requested. */
    public function enrollmentSessionSamples(string $sessionId): array
    {
        return $this->requestJson('GET', $this->enrollmentSessionPath($sessionId) . '/samples');
    }

    public function cancelEnrollmentSession(string $sessionId): array
    {
        return $this->requestJson('POST', $this->enrollmentSessionPath($sessionId) . '/cancel');
    }

    public function closeEnrollmentSession(string $sessionId): array
    {
        return $this->requestJson('POST', $this->enrollmentSessionPath($sessionId) . '/close');
    }

    private function enrollmentSessionPath(string $sessionId): string
    {
        if (!preg_match('/^[a-f0-9]{32}$/D', $sessionId)) {
            throw new InvalidArgumentException('Enrollment session ID is invalid.');
        }

        return '/api/ai/enrollment-sessions/' . $sessionId;
    }

    private function requestJson(string $method, string $path): array
    {
        $context = stream_context_create([
            'http' => [
                'method' => $method,
                'header' => "Accept: application/json\r\nContent-Type: application/json\r\n",
                'content' => $method === 'POST' ? '{}' : '',
                'timeout' => $method === 'POST' ? 30 : 4,
                'ignore_errors' => true,
            ],
        ]);
        $body = @file_get_contents(self::BASE_URL . $path, false, $context);
        if (!is_string($body)) {
            throw new RuntimeException('AI service is unavailable.');
        }

        $response = json_decode($body, true);
        if (!is_array($response)) {
            throw new RuntimeException('AI service returned an invalid response.');
        }

        return $response;
    }

    private function requestEnrollmentJson(string $path, string $jpeg, string $expectedPose, ?string $referenceVector = null): array
    {
        $payload = [
            'image' => base64_encode($jpeg),
            'expected_pose' => $expectedPose,
        ];
        if ($referenceVector !== null) {
            $payload['reference_vector'] = base64_encode($referenceVector);
        }
        $content = json_encode($payload, JSON_THROW_ON_ERROR);
        $context = stream_context_create([
            'http' => [
                'method' => 'POST',
                'header' => "Accept: application/json\r\nContent-Type: application/json\r\n",
                'content' => $content,
                'timeout' => 20,
                'ignore_errors' => true,
            ],
        ]);
        $body = @file_get_contents(self::BASE_URL . $path, false, $context);
        if (!is_string($body)) {
            throw new RuntimeException('AI service is unavailable.');
        }

        $response = json_decode($body, true);
        if (!is_array($response)) {
            throw new RuntimeException('AI service returned an invalid enrollment response.');
        }

        return $response;
    }
}
