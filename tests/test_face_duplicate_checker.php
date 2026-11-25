<?php
declare(strict_types=1);

require_once __DIR__ . '/../Service/FaceDuplicateChecker.php';

function assertDuplicateCheck(bool $condition, string $message): void
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

function duplicateVector(float $angle): string
{
    $values = array_fill(0, 512, 0.0);
    $values[0] = cos($angle);
    $values[1] = sin($angle);
    return pack('g*', ...$values);
}

function duplicateSamples(float $angle): array
{
    $image = base64_decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aPZsAAAAASUVORK5CYII=',
        true
    );
    $poses = ['frontal', 'left', 'right', 'up', 'down'];
    $samples = [];
    foreach ($poses as $pose) {
        $samples[] = ['pose' => $pose, 'vector' => duplicateVector($angle), 'image' => $image];
    }
    return $samples;
}

function duplicateRows(int $employeeId, float $angle, int $count = 5): array
{
    $rows = [];
    for ($index = 1; $index <= $count; $index++) {
        $rows[] = [
            'MaNV' => $employeeId,
            'MaEmbedding' => ($employeeId * 100) + $index,
            'SoChieu' => 512,
            'VectorData' => duplicateVector($angle),
            'HoTen' => 'Nhân viên ' . $employeeId,
        ];
    }
    return $rows;
}

$samples = duplicateSamples(0.0);
$unconfigured = new FaceDuplicateChecker();
$empty = $unconfigured->evaluate(2, $samples, []);
assertDuplicateCheck($empty['status'] === 'CLEAR', 'An empty other-employee gallery should be clear.');

$checker = new FaceDuplicateChecker(0.95, true, 'buffalo_l', 'max_5x5_cosine');
$differentEmployee = $checker->evaluate(2, $samples, duplicateRows(1, 0.45));
assertDuplicateCheck($differentEmployee['status'] === 'CLEAR', 'A new face below the calibrated threshold should be clear.');

$sameAsNv001 = $checker->evaluate(22, $samples, duplicateRows(1, 0.0));
assertDuplicateCheck($sameAsNv001['status'] === 'SUSPECTED_DUPLICATE', 'An identical face under a different ID should be suspected.');
assertDuplicateCheck($sameAsNv001['candidate_id'] === 1, 'The suspected employee ID should be returned to the Admin flow.');

$selfReenrollment = $unconfigured->evaluate(1, $samples, duplicateRows(1, 0.0));
assertDuplicateCheck($selfReenrollment['status'] === 'CLEAR', 'Re-enrollment must exclude the same employee.');

$highSimilarityButBelowLimit = (new FaceDuplicateChecker(0.995, true, 'buffalo_l', 'max_5x5_cosine'))
    ->evaluate(2, $samples, duplicateRows(1, 0.15));
assertDuplicateCheck(
    $highSimilarityButBelowLimit['status'] === 'CLEAR',
    'A relatively high score below the configured threshold must not be declared a duplicate.'
);

$noThreshold = $unconfigured->evaluate(22, $samples, duplicateRows(1, 0.0));
assertDuplicateCheck($noThreshold['status'] === 'CHECK_UNAVAILABLE', 'An uncalibrated threshold must fail closed.');
assertDuplicateCheck($noThreshold['reason'] === 'THRESHOLD_NOT_CALIBRATED', 'Missing calibration must be explicit.');

$partialGallery = $checker->evaluate(22, $samples, duplicateRows(1, 0.0, 2));
assertDuplicateCheck($partialGallery['status'] === 'CHECK_UNAVAILABLE', 'A partial employee gallery must fail closed.');

$invalidGallery = duplicateRows(1, 0.0);
$invalidGallery[2]['VectorData'] = str_repeat("\0", 32);
assertDuplicateCheck(
    $checker->evaluate(22, $samples, $invalidGallery)['status'] === 'CHECK_UNAVAILABLE',
    'An invalid stored vector must fail closed.'
);

$invalidNew = $samples;
$invalidNew[4]['vector'] = str_repeat("\0", 32);
assertDuplicateCheck(
    $checker->evaluate(22, $invalidNew, duplicateRows(1, 0.0))['status'] === 'CHECK_UNAVAILABLE',
    'An invalid new vector must fail closed.'
);

echo "Face duplicate checker PASS\n";
