<?php
declare(strict_types=1);

final class AiClient
{
    private const BASE_URL = 'http://127.0.0.1:5001';

    public function health(): array
    {
        return $this->requestJson('GET', '/health');
    }

    public function recognize(): array
    {
        return $this->requestJson('POST', '/api/ai/recognize');
    }

    public function refreshGallery(): array
    {
        return $this->requestJson('POST', '/api/ai/gallery/refresh');
    }

    public function cameraFrame(): string
    {
        $context = stream_context_create([
            'http' => [
                'method' => 'GET',
                'timeout' => 4,
                'ignore_errors' => true,
            ],
        ]);
        $image = @file_get_contents(self::BASE_URL . '/api/ai/frame', false, $context);
        if (!is_string($image) || $image === '' || !str_starts_with($image, "\xFF\xD8")) {
            throw new RuntimeException('Camera frame unavailable.');
        }

        return $image;
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
}
