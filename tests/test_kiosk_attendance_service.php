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
assertSameValue('Nguyen Van A', $checkin['employee_name'], 'Check-in returns verified employee name');
assertSameValue([7, 2, 'server-camera-jpeg'], $attendanceCalls[0], 'Server identity/device/evidence passed');
$passed++;

// A no-shift response carries the backend employee name for the result card;
// the primary identity remains numeric and the user-facing message omits the ID.
$aiPayload = makeKioskRecognition(['recognized' => true, 'ma_nv' => 22, 'ho_ten' => 'Nguyễn Viết Thắng']);
$attendancePayload = ['status' => 'error', 'action' => 'error', 'message' => 'Nhân viên chưa được phân ca hôm nay'];
$nv022 = $service->recordFromRecognitionSession(str_repeat('6', 32), 1, $session);
assertSameValue([22, 1, 'server-camera-jpeg'], $attendanceCalls[count($attendanceCalls) - 1], 'NV022 numeric identity is passed to attendance');
assertSameValue(22, $nv022['employee_id'], 'NV022 identity is retained in no-shift result');
assertSameValue('Nguyễn Viết Thắng', $nv022['employee_name'], 'No-shift result carries verified employee name');
assertSameValue('Bạn chưa được phân ca hôm nay. Vui lòng liên hệ quản lý.', $nv022['message'], 'No-shift message is user-facing');
assertSameValue(false, str_contains($nv022['message'], 'NV022'), 'Employee code is not the main message');
$passed++;

$attendancePayload = ['status' => 'error', 'action' => 'error', 'message' => 'Chưa đến giờ chấm công'];
$tooEarly = $service->recordFromRecognitionSession(str_repeat('7', 32), 1, $session);
assertSameValue('Nguyễn Viết Thắng', $tooEarly['employee_name'], 'Too-early rejection carries verified name');
assertSameValue('Chưa đến giờ chấm công. Vui lòng chờ đến giờ quy định.', $tooEarly['message'], 'Too-early message is clear');
$attendancePayload = ['status' => 'error', 'action' => 'error', 'message' => 'Không có ca làm hợp lệ'];
$invalidShift = $service->recordFromRecognitionSession(str_repeat('8', 32), 1, $session);
assertSameValue('Bạn chưa được phân ca hôm nay. Vui lòng liên hệ quản lý.', $invalidShift['message'], 'Invalid shift maps to safe schedule message');
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
assertSameValue('Nguyễn Viết Thắng', $completed['employee_name'], 'Completed result carries verified name');
$attendancePayload = ['status' => 'error', 'action' => 'error', 'message' => 'write failed'];
$failed = $service->recordFromRecognitionSession(str_repeat('1', 32), 2, $session);
assertSameValue('RETRY', $failed['state'], 'Failed write is not success');
$passed++;

$attendanceThrows = true;
$aiPayload = makeKioskRecognition(['recognized' => true, 'ma_nv' => 12, 'ho_ten' => 'Database Failure User']);
$writeFailure = $service->recordFromRecognitionSession(str_repeat('9', 32), 2, $session);
assertSameValue('RETRY', $writeFailure['state'], 'Attendance exception is rejected');
assertSameValue('Database Failure User', $writeFailure['employee_name'], 'Recognized name survives attendance exception');
$attendanceThrows = false;
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
assertSameValue('Camera Test', $cameraOffline['employee_name'], 'Post-match camera error carries verified name');
assertSameValue($callsBeforeCameraFailure, count($attendanceCalls), 'Camera outage does not write attendance');
$passed++;

echo "Kiosk attendance service: {$passed} checks passed. No database was used.\n";
