<?php
declare(strict_types=1);

require_once __DIR__ . '/../Service/KioskAttendanceService.php';

function assertSameValue(mixed $expected, mixed $actual, string $message): void
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true)
            . ', got ' . var_export($actual, true));
    }
}

function makeKioskRecognition(array $result, string $state = 'COMPLETED'): array
{
    return ['success' => true, 'state' => $state, 'result' => $result];
}

$passed = 0;
$sessionId = str_repeat('a', 32);
$aiPayload = [];
$aiThrows = false;
$attendanceCalls = [];
$attendancePayload = [];
$attendanceThrows = false;
$evidenceJpeg = 'server-camera-jpeg';
$service = new KioskAttendanceService(
    static function (string $id) use (&$aiPayload, &$aiThrows): array {
        if ($aiThrows) throw new RuntimeException('offline');
        return $aiPayload;
    },
    static function (int $employeeId, int $deviceId, ?string $image) use (&$attendanceCalls, &$attendancePayload, &$attendanceThrows): array {
        $attendanceCalls[] = [$employeeId, $deviceId, $image];
        if ($attendanceThrows) throw new RuntimeException('write failed');
        return $attendancePayload;
    },
    static function () use (&$evidenceJpeg): ?string { return $evidenceJpeg; }
);
$session = [];

// A MATCH alone is not success while the AI session is still processing.
$aiPayload = makeKioskRecognition(['recognized' => true, 'ma_nv' => 7], 'PROCESSING');
$result = $service->recordFromRecognitionSession($sessionId, 2, $session);
assertSameValue('PROCESSING', $result['state'], 'Pending AI state');
assertSameValue(0, count($attendanceCalls), 'No attendance write before terminal AI result');
$passed++;

// UNKNOWN and RETRY never reach attendance storage.
$aiPayload = makeKioskRecognition(['recognized' => false, 'reason' => 'UNKNOWN']);
$result = $service->recordFromRecognitionSession(str_repeat('b', 32), 2, $session);
assertSameValue('UNKNOWN', $result['state'], 'Unknown result');
assertSameValue(0, count($attendanceCalls), 'Unknown does not write');
$aiPayload = makeKioskRecognition(['recognized' => false, 'reason' => 'RETRY', 'retry_reason' => 'NO_FACE'], 'ABORTED');
$result = $service->recordFromRecognitionSession(str_repeat('c', 32), 2, $session);
assertSameValue('RETRY', $result['state'], 'Abort maps to retry');
assertSameValue(0, count($attendanceCalls), 'Retry does not write');
$passed++;

// Check-in success is returned only after AttendanceService confirms its write.
$aiPayload = makeKioskRecognition(['recognized' => true, 'ma_nv' => 7, 'ho_ten' => 'Nguyen Van A']);
$attendancePayload = ['status' => 'success', 'action' => 'checkin', 'TenCa' => 'Hành chính'];
$checkin = $service->recordFromRecognitionSession(str_repeat('d', 32), 2, $session);
assertSameValue('SUCCESS', $checkin['state'], 'Confirmed check-in');
assertSameValue('checkin', $checkin['action'], 'Check-in event');
assertSameValue([7, 2, 'server-camera-jpeg'], $attendanceCalls[0], 'Server identity/device/evidence passed');
$passed++;

// NV022 is passed as its numeric primary key, and a no-shift response identifies
// the matched employee instead of hiding a possible gallery/identity mismatch.
$aiPayload = makeKioskRecognition(['recognized' => true, 'ma_nv' => 22, 'ho_ten' => 'Nguyễn Viết Thắng']);
$attendancePayload = ['status' => 'error', 'action' => 'error', 'message' => 'Nhân viên chưa được phân ca hôm nay'];
$nv022 = $service->recordFromRecognitionSession(str_repeat('6', 32), 1, $session);
assertSameValue([22, 1, 'server-camera-jpeg'], $attendanceCalls[count($attendanceCalls) - 1], 'NV022 numeric identity is passed to attendance');
assertSameValue(22, $nv022['employee_id'], 'NV022 identity is retained in no-shift result');
assertSameValue(true, str_contains($nv022['message'], 'NV022'), 'No-shift message exposes matched employee code');
$passed++;

// The same terminal result can confirm a check-out.
$attendancePayload = ['status' => 'success', 'action' => 'checkout', 'TenCa' => 'Hành chính'];
$checkout = $service->recordFromRecognitionSession(str_repeat('e', 32), 2, $session);
assertSameValue('SUCCESS', $checkout['state'], 'Confirmed check-out');
assertSameValue('checkout', $checkout['action'], 'Check-out event');
$passed++;

// Existing completed attendance is reported as such, and failed writes are never success.
$attendancePayload = ['status' => 'success', 'action' => 'completed'];
$completed = $service->recordFromRecognitionSession(str_repeat('f', 32), 2, $session);
assertSameValue('ALREADY_COMPLETED', $completed['state'], 'Completed attendance');
$attendancePayload = ['status' => 'error', 'action' => 'error', 'message' => 'write failed'];
$failed = $service->recordFromRecognitionSession(str_repeat('1', 32), 2, $session);
assertSameValue('RETRY', $failed['state'], 'Failed write is not success');
$passed++;

// The employee ID is read only from AI's terminal result, not supplied by caller input.
$aiPayload = makeKioskRecognition(['recognized' => true, 'ma_nv' => 'invalid']);
$callsBeforeInvalid = count($attendanceCalls);
$invalid = $service->recordFromRecognitionSession(str_repeat('2', 32), 2, $session);
assertSameValue('RETRY', $invalid['state'], 'Invalid AI identity rejected');
assertSameValue($callsBeforeInvalid, count($attendanceCalls), 'Invalid identity cannot write');
$passed++;

// Replaying the same recognized session returns the cached outcome without a second write.
$aiPayload = makeKioskRecognition(['recognized' => true, 'ma_nv' => 9, 'ho_ten' => 'Test User']);
$attendancePayload = ['status' => 'success', 'action' => 'checkin'];
$replayId = str_repeat('3', 32);
$first = $service->recordFromRecognitionSession($replayId, 2, $session);
$callsAfterFirst = count($attendanceCalls);
$replayed = $service->recordFromRecognitionSession($replayId, 2, $session);
assertSameValue($first, $replayed, 'Replay returns same outcome');
assertSameValue($callsAfterFirst, count($attendanceCalls), 'Replay is idempotent');
$passed++;

// Internal AI outage is an offline state, never a success.
$aiThrows = true;
$offline = $service->recordFromRecognitionSession(str_repeat('4', 32), 2, $session);
assertSameValue('OFFLINE', $offline['state'], 'AI outage');
$passed++;

// A camera failure after recognition must not write attendance without evidence.
$aiThrows = false;
$evidenceJpeg = null;
$aiPayload = makeKioskRecognition(['recognized' => true, 'ma_nv' => 11, 'ho_ten' => 'Camera Test']);
$callsBeforeCameraFailure = count($attendanceCalls);
$cameraOffline = $service->recordFromRecognitionSession(str_repeat('5', 32), 2, $session);
assertSameValue('OFFLINE', $cameraOffline['state'], 'Camera outage blocks attendance');
assertSameValue('CAMERA_SOURCE_UNAVAILABLE', $cameraOffline['code'], 'Camera outage has precise code');
assertSameValue($callsBeforeCameraFailure, count($attendanceCalls), 'Camera outage does not write attendance');
$passed++;

echo "Kiosk attendance service: {$passed} checks passed. No database was used.\n";
