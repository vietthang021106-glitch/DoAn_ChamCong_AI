<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';

function assertFaceIntegrity(bool $condition, string $message): void
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

$model = new FaceEmbeddingModel();
$validate = new ReflectionMethod(FaceEmbeddingModel::class, 'validateSamples');
$normalize = new ReflectionMethod(FaceEmbeddingModel::class, 'normalizeStoredVector');
$revision = new ReflectionMethod(FaceEmbeddingModel::class, 'revisionFromRows');
$matches = new ReflectionMethod(FaceEmbeddingModel::class, 'matchesSamples');
$validate->setAccessible(true);
$normalize->setAccessible(true);
$revision->setAccessible(true);
$matches->setAccessible(true);

$png = base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aPZsAAAAASUVORK5CYII=', true);
$poses = ['frontal', 'left', 'right', 'up', 'down'];
$vectors = [];
for ($index = 0; $index < 5; $index++) {
    $values = array_fill(0, 512, 0.0);
    $values[0] = 1.0;
    $values[$index + 1] = 0.01;
    $vectors[] = pack('g*', ...$values);
}
$samples = [];
foreach ($poses as $index => $pose) {
    $samples[] = ['pose' => $pose, 'vector' => $vectors[$index], 'image' => $png];
}
$valid = $validate->invoke($model, $samples);
assertFaceIntegrity(count($valid) === 5, 'Exactly five valid pose samples should be accepted.');
assertFaceIntegrity(strlen($valid[0]['vector']) === 2048, 'Stored vector must be 2048 bytes.');

$wrongPerson = $samples;
$different = array_fill(0, 512, 0.0);
$different[511] = 1.0;
$wrongPerson[4]['vector'] = pack('g*', ...$different);
try {
    $validate->invoke($model, $wrongPerson);
    throw new RuntimeException('A different person must not pass five-sample validation.');
} catch (ReflectionException $exception) {
    throw $exception;
} catch (Throwable $exception) {
    assertFaceIntegrity(str_contains($exception->getMessage(), 'cùng một danh tính'), 'Wrong-person failure should be explicit.');
}

$nonFinite = array_fill(0, 512, 0.0);
$nonFinite[0] = NAN;
try {
    $normalize->invoke($model, pack('g*', ...$nonFinite));
    throw new RuntimeException('Non-finite vector should be rejected.');
} catch (Throwable $exception) {
    assertFaceIntegrity(str_contains($exception->getMessage(), 'non-finite'), 'Non-finite failure should be explicit.');
}

$normalA = $revision->invoke($model, [['MaEmbedding' => 1, 'VectorData' => $valid[0]['vector']]]);
$normalB = $revision->invoke($model, [['MaEmbedding' => 1, 'VectorData' => $valid[0]['vector']]]);
$changed = $revision->invoke($model, [['MaEmbedding' => 2, 'VectorData' => $valid[0]['vector']]]);
assertFaceIntegrity($normalA === $normalB && $normalA !== $changed, 'Gallery revision must be stable and change with sample identity.');
assertFaceIntegrity($matches->invoke($model, array_map(static fn(int $i): array => [
    'MaEmbedding' => $i + 1,
    'VectorData' => $valid[$i]['vector'],
    'AnhKhuonMat' => $png,
], array_keys($valid)), $valid), 'Exact persisted batch should be recognized as an idempotent retry.');

echo "FaceEmbedding integrity PASS\n";
