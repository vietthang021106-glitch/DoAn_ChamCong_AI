<?php
declare(strict_types=1);

require_once __DIR__ . '/../Service/EnrollmentCaptureState.php';

function assertEnrollment(bool $condition, string $message): void
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

$state = EnrollmentCaptureState::create();
for ($frame = 1; $frame < 8; $frame++) {
    $result = EnrollmentCaptureState::observe($state, true);
    assertEnrollment(!$result['capture_due'], 'Capture started before frame eight.');
}
$result = EnrollmentCaptureState::observe($state, true);
assertEnrollment($result['capture_due'] && $result['stable_frame_count'] === 8,
                 'Eight consecutive ready frames should enable capture.');

$sample = ['vector' => str_repeat("\x01", 2048), 'image' => "\xFF\xD8sample"];
$captured = EnrollmentCaptureState::recordSample($state,
    ['frontal', 'left', 'right', 'up', 'down'], 'frontal', $sample);
assertEnrollment($captured === 1, 'First pose should advance progress to one.');
assertEnrollment($state['current_pose_index'] === 1 && $state['stable_frame_count'] === 0,
                 'Recording a sample must advance pose and reset stability.');

for ($frame = 0; $frame < 5; $frame++) {
    EnrollmentCaptureState::observe($state, true);
}
$result = EnrollmentCaptureState::observe($state, false);
assertEnrollment(!$result['capture_due'] && $result['stable_frame_count'] === 0,
                 'A rejected frame must reset the consecutive stability count.');

$freshFrames = EnrollmentCaptureState::create();
for ($sequence = 20; $sequence < 28; $sequence++) {
    $fresh = EnrollmentCaptureState::observeSnapshot($freshFrames, $sequence, true);
}
assertEnrollment($fresh['capture_due'] && $fresh['fresh_frame'],
                 'Eight distinct increasing camera frames should enable capture.');
$duplicate = EnrollmentCaptureState::observeSnapshot($freshFrames, 27, true);
assertEnrollment(!$duplicate['fresh_frame'] && !$duplicate['capture_due']
                 && $duplicate['stable_frame_count'] === 0,
                 'A repeated camera frame must reset stability instead of counting twice.');

$blocked = false;
try {
    EnrollmentCaptureState::recordSample($state,
        ['frontal', 'left', 'right', 'up', 'down'], 'left', $sample);
} catch (LogicException) {
    $blocked = true;
}
assertEnrollment($blocked, 'State machine must reject capture without eight stable frames.');

$fullBatch = EnrollmentCaptureState::create();
$poses = ['frontal', 'left', 'right', 'up', 'down'];
foreach ($poses as $index => $pose) {
    for ($frame = 0; $frame < EnrollmentCaptureState::STABLE_FRAMES_REQUIRED; $frame++) {
        $stability = EnrollmentCaptureState::observe($fullBatch, true);
    }
    assertEnrollment($stability['capture_due'], 'Each pose should require eight consecutive ready frames.');
    $captured = EnrollmentCaptureState::recordSample($fullBatch, $poses, $pose, $sample);
    assertEnrollment($captured === $index + 1, 'Pose index should advance after staging the pair.');
}
assertEnrollment(count($fullBatch['samples']) === 5
                 && EnrollmentCaptureState::poseIndex($fullBatch) === 5,
                 'A full staged batch should contain all five ordered poses.');
fwrite(STDOUT, "EnrollmentCaptureState PASS\n");
