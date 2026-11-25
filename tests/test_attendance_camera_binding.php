<?php
declare(strict_types=1);

require_once __DIR__ . '/../Service/AttendanceCameraBinding.php';

function assertSameBinding(?int $expected, ?int $actual, string $message): void
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true)
            . ', got ' . var_export($actual, true));
    }
}

$devices = [['MaTB' => 4], ['MaTB' => 9]];
$oldValue = getenv('AI1_CAMERA_DEVICE_ID');
putenv('AI1_CAMERA_DEVICE_ID');
assertSameBinding(null, AttendanceCameraBinding::deviceId($devices), 'Multiple devices require explicit camera binding');
assertSameBinding(4, AttendanceCameraBinding::deviceId([['MaTB' => 4]]), 'Single device can use the current singleton');
putenv('AI1_CAMERA_DEVICE_ID=9');
assertSameBinding(9, AttendanceCameraBinding::deviceId($devices), 'Explicit source binding');
putenv('AI1_CAMERA_DEVICE_ID=22');
assertSameBinding(null, AttendanceCameraBinding::deviceId($devices), 'Unknown device cannot claim the current camera');
if ($oldValue === false) {
    putenv('AI1_CAMERA_DEVICE_ID');
} else {
    putenv('AI1_CAMERA_DEVICE_ID=' . $oldValue);
}

echo "Attendance camera binding: 4 checks passed. No database was used.\n";
