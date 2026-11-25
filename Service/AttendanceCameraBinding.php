<?php
declare(strict_types=1);

/** Bind the single existing camera singleton to one configured attendance device. */
final class AttendanceCameraBinding
{
    /** @param array<int, array{MaTB:int|string}> $devices */
    public static function deviceId(array $devices): ?int
    {
        $configured = getenv('AI1_CAMERA_DEVICE_ID');
        if (is_string($configured) && trim($configured) !== '') {
            $id = filter_var(trim($configured), FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
            if (!is_int($id)) {
                return null;
            }
            foreach ($devices as $device) {
                if ((int)($device['MaTB'] ?? 0) === $id) {
                    return $id;
                }
            }

            return null;
        }

        if (count($devices) !== 1) {
            return null;
        }

        $id = filter_var($devices[0]['MaTB'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);

        return is_int($id) ? $id : null;
    }
}
