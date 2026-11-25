<?php
declare(strict_types=1);

/**
 * Duplicate-face decision for buffalo_l 512D embeddings.
 *
 * A production threshold is deliberately not inferred from the recognition
 * threshold. It must be calibrated for max-over-5x5 cosine comparisons and
 * explicitly marked as validated in the environment.
 *
 * Required settings: AI1_DUPLICATE_FACE_THRESHOLD,
 * AI1_DUPLICATE_FACE_THRESHOLD_VALIDATED=1,
 * AI1_DUPLICATE_FACE_MODEL=buffalo_l, and
 * AI1_DUPLICATE_FACE_AGGREGATION=max_5x5_cosine.
 */
final class FaceDuplicateChecker
{
    private ?float $threshold;
    private bool $thresholdValidated;
    private string $modelName;
    private string $aggregation;

    public function __construct(
        ?float $threshold = null,
        ?bool $thresholdValidated = null,
        ?string $modelName = null,
        ?string $aggregation = null
    ) {
        $environmentThreshold = getenv('AI1_DUPLICATE_FACE_THRESHOLD');
        $this->threshold = $threshold ?? (
            $environmentThreshold !== false && is_numeric($environmentThreshold)
                ? (float)$environmentThreshold
                : null
        );
        $this->thresholdValidated = $thresholdValidated
            ?? getenv('AI1_DUPLICATE_FACE_THRESHOLD_VALIDATED') === '1';
        $this->modelName = $modelName ?? (getenv('AI1_DUPLICATE_FACE_MODEL') ?: '');
        $this->aggregation = $aggregation ?? (getenv('AI1_DUPLICATE_FACE_AGGREGATION') ?: '');
    }

    /**
     * Compare all five new pose samples with every stored sample of each other
     * employee. The employee score is max cosine over the 5 x gallery-samples
     * pairs, matching the current multi-sample MAX shape.
     */
    public function evaluate(int $employeeId, array $samples, array $galleryRows): array
    {
        try {
            if ($employeeId < 1 || count($samples) !== 5) {
                return $this->unavailable('INVALID_NEW_SAMPLES');
            }
            $newVectors = [];
            foreach ($samples as $sample) {
                $newVectors[] = $this->decodeNormalizedVector($sample['vector'] ?? null);
            }

            $groups = [];
            foreach ($galleryRows as $row) {
                $otherEmployeeId = filter_var($row['MaNV'] ?? null, FILTER_VALIDATE_INT);
                if (!is_int($otherEmployeeId) || $otherEmployeeId < 1) {
                    return $this->unavailable('INVALID_GALLERY_IDENTITY');
                }
                if ($otherEmployeeId === $employeeId) {
                    continue;
                }
                if ((int)($row['SoChieu'] ?? 0) !== 512) {
                    return $this->unavailable('INVALID_GALLERY_DIMENSION');
                }
                $vector = $this->decodeNormalizedVector($row['VectorData'] ?? null);
                $groups[$otherEmployeeId]['name'] = (string)($row['HoTen'] ?? '');
                $groups[$otherEmployeeId]['vectors'][] = $vector;
            }

            if ($groups === []) {
                return [
                    'status' => 'CLEAR',
                    'code' => 'NO_OTHER_FACE_SAMPLES',
                    'reason' => '',
                    'message' => 'Không có mẫu khuôn mặt của nhân viên khác để đối chiếu.',
                    'candidate_id' => null,
                    'candidate_name' => null,
                    'similarity' => null,
                    'threshold' => null,
                ];
            }

            foreach ($groups as $group) {
                if (count($group['vectors']) !== 5) {
                    return $this->unavailable('INCOMPLETE_GALLERY');
                }
            }
            if (!$this->hasValidatedThreshold()) {
                return $this->unavailable('THRESHOLD_NOT_CALIBRATED');
            }

            $best = null;
            foreach ($groups as $otherEmployeeId => $group) {
                $employeeScore = -INF;
                foreach ($newVectors as $newVector) {
                    foreach ($group['vectors'] as $storedVector) {
                        $score = $this->cosine($newVector, $storedVector);
                        if ($score > $employeeScore) {
                            $employeeScore = $score;
                        }
                    }
                }
                if ($best === null || $employeeScore > $best['similarity']) {
                    $best = [
                        'candidate_id' => (int)$otherEmployeeId,
                        'candidate_name' => $group['name'],
                        'similarity' => $employeeScore,
                    ];
                }
            }

            if ($best === null) {
                return $this->unavailable('GALLERY_EMPTY');
            }
            if ($best['similarity'] >= $this->threshold) {
                return [
                    'status' => 'SUSPECTED_DUPLICATE',
                    'code' => 'SIMILARITY_OVER_VALIDATED_THRESHOLD',
                    'reason' => '',
                    'message' => 'Khuôn mặt có khả năng trùng với nhân viên khác.',
                    'candidate_id' => $best['candidate_id'],
                    'candidate_name' => $best['candidate_name'],
                    'similarity' => (float)$best['similarity'],
                    'threshold' => $this->threshold,
                ];
            }

            return [
                'status' => 'CLEAR',
                'code' => 'BELOW_VALIDATED_THRESHOLD',
                'reason' => '',
                'message' => 'Không phát hiện bằng chứng trùng theo ngưỡng đã hiệu chỉnh.',
                'candidate_id' => null,
                'candidate_name' => null,
                'similarity' => (float)$best['similarity'],
                'threshold' => $this->threshold,
            ];
        } catch (Throwable $exception) {
            return $this->unavailable('INVALID_OR_UNREADABLE_EMBEDDING');
        }
    }

    public function unavailable(string $reason): array
    {
        return [
            'status' => 'CHECK_UNAVAILABLE',
            'code' => 'DUPLICATE_CHECK_UNAVAILABLE',
            'reason' => $reason,
            'message' => 'Chưa thể kiểm tra trùng khuôn mặt. Vui lòng thử lại.',
            'candidate_id' => null,
            'candidate_name' => null,
            'similarity' => null,
            'threshold' => null,
        ];
    }

    private function hasValidatedThreshold(): bool
    {
        return $this->thresholdValidated
            && $this->threshold !== null
            && is_finite($this->threshold)
            && $this->threshold >= 0.0
            && $this->threshold <= 1.0
            && $this->modelName === 'buffalo_l'
            && $this->aggregation === 'max_5x5_cosine';
    }

    private function decodeNormalizedVector(mixed $bytes): array
    {
        if (!is_string($bytes) || strlen($bytes) !== 2048) {
            throw new InvalidArgumentException('Invalid 512D float32 embedding.');
        }
        $values = unpack('g*', $bytes);
        if (!is_array($values) || count($values) !== 512) {
            throw new InvalidArgumentException('Invalid 512D float32 embedding.');
        }
        $normSquared = 0.0;
        foreach ($values as $value) {
            if (!is_finite((float)$value)) {
                throw new InvalidArgumentException('Embedding contains non-finite values.');
            }
            $normSquared += (float)$value * (float)$value;
        }
        $norm = sqrt($normSquared);
        if (!is_finite($norm) || $norm <= 1e-12) {
            throw new InvalidArgumentException('Embedding norm is invalid.');
        }

        return array_map(static fn(float|int $value): float => (float)$value / $norm, array_values($values));
    }

    private function cosine(array $left, array $right): float
    {
        $similarity = 0.0;
        foreach ($left as $index => $value) {
            $similarity += $value * $right[$index];
        }

        return max(-1.0, min(1.0, $similarity));
    }
}

final class FaceDuplicateCheckException extends RuntimeException
{
    private array $check;

    public function __construct(array $check)
    {
        $this->check = $check;
        parent::__construct((string)($check['message'] ?? 'Không thể kiểm tra trùng khuôn mặt.'));
    }

    public function checkResult(): array
    {
        return $this->check;
    }
}
