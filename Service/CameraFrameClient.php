<?php
declare(strict_types=1);

final class CameraFrameClient
{
    private const FRAME_URL = 'http://127.0.0.1:5000/internal/camera/frame';

    public function captureJpeg(): ?string
    {
        $snapshot = $this->captureSnapshot();

        return $snapshot['jpeg'] ?? null;
    }

    /** Fetch one camera frame together with the camera owner's unique sequence number. */
    public function captureSnapshot(): ?array
    {
        $context = stream_context_create([
            'http' => [
                'method' => 'GET',
                'timeout' => 1.5,
                'ignore_errors' => true,
            ],
        ]);
        $image = @file_get_contents(self::FRAME_URL, false, $context);
        $headers = $http_response_header ?? [];
        $sequence = null;
        foreach ($headers as $header) {
            if (preg_match('/^X-Frame-Sequence:\s*(\d+)\s*$/i', $header, $matches)) {
                $sequence = (int)$matches[1];
                break;
            }
        }

        if (!is_string($image) || strlen($image) < 4 || strlen($image) > 2 * 1024 * 1024
            || !str_starts_with($image, "\xFF\xD8") || !str_ends_with($image, "\xFF\xD9")
            || !is_int($sequence) || $sequence < 1) {
            return null;
        }

        return ['jpeg' => $image, 'sequence' => $sequence];
    }
}
