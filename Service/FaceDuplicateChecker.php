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
 * AI1_DUPLICATE_FACE_AGGREGATION=max_5x5_cosine, plus a calibration report
 * produced by tools/calibrate_face_duplicate_threshold.py.
 */
final class FaceDuplicateChecker
{
    private const MIN_CALIBRATION_IDENTITIES = 10;
    private const MIN_GENUINE_PAIRS = 30;
    private const MIN_IMPOSTOR_PAIRS = 100;

    private ?float $threshold;
    private bool $thresholdValidated;
    private string $modelName;
    private string $aggregation;
    private ?array $calibrationReport;
    private string $calibrationReportError;

    /**
     * The temporary save bypass is available only for an explicitly enabled
     * development/demo process serving a loopback request. It never changes
     * evaluate() results, so CHECK_UNAVAILABLE cannot become a fake CLEAR.
     */
    public static function isLocalDemoBypassEnabled(?array $server = null): bool
    {
        $server ??= $_SERVER;
        $environment = strtolower(trim((string)(getenv('APP_ENV') ?: '')));
        if (!in_array($environment, ['local', 'development', 'dev'], true)
            || getenv('AI1_DEMO_ALLOW_UNCHECKED_ENROLLMENT') !== '1') {
            return false;
        }

        $hostHeader = trim((string)($server['HTTP_HOST'] ?? ''));
        $host = parse_url('http://' . $hostHeader, PHP_URL_HOST);
        $host = strtolower(trim(is_string($host) ? $host : '', '[]'));
        $remoteAddress = trim((string)($server['REMOTE_ADDR'] ?? ''));
        $isLoopback = $remoteAddress === '::1'
            || (filter_var($remoteAddress, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) !== false
                && str_starts_with($remoteAddress, '127.'));

        return $isLoopback && in_array($host, ['localhost', '127.0.0.1', '::1'], true);
    }

    /** Only an unavailable, uncalibrated threshold may be bypassed for a confirmed local demo save. */
    public static function isDemoBypassableUnavailable(array $result): bool
    {
        return ($result['status'] ?? null) === 'CHECK_UNAVAILABLE'
            && ($result['reason'] ?? null) === 'THRESHOLD_NOT_CALIBRATED';
    }

    public function __construct(
        ?float $threshold = null,
        ?bool $thresholdValidated = null,
        ?string $modelName = null,
        ?string $aggregation = null,
        ?array $calibrationReport = null
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
        if ($calibrationReport !== null) {
            $this->calibrationReport = $calibrationReport;
            $this->calibrationReportError = '';
        } else {
            [$this->calibrationReport, $this->calibrationReportError] = $this->loadCalibrationReport();
        }
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
            $configurationError = $this->thresholdConfigurationError();
            if ($configurationError !== null) {
                return $this->unavailable($configurationError);
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

    private function thresholdConfigurationError(): ?string
    {
        if ($this->threshold === null) {
            return 'THRESHOLD_NOT_CALIBRATED';
        }
        if (!is_finite($this->threshold) || $this->threshold < 0.0 || $this->threshold > 1.0) {
            return 'THRESHOLD_INVALID';
        }
        if (!$this->thresholdValidated) {
            return 'THRESHOLD_NOT_CALIBRATED';
        }
        if ($this->modelName !== 'buffalo_l') {
            return 'MODEL_MISMATCH';
        }
        if ($this->aggregation !== 'max_5x5_cosine') {
            return 'AGGREGATION_MISMATCH';
        }
        if ($this->calibrationReport === null) {
            return $this->calibrationReportError ?: 'CALIBRATION_REPORT_MISSING';
        }

        $report = $this->calibrationReport;
        if (($report['validated'] ?? false) !== true
            || ($report['model'] ?? null) !== 'buffalo_l'
            || ($report['aggregation'] ?? null) !== 'max_5x5_cosine'
            || (int)($report['version'] ?? 0) !== 1) {
            return 'CALIBRATION_REPORT_INVALID';
        }
        $reportThreshold = $report['threshold'] ?? null;
        if (!is_numeric($reportThreshold) || !is_finite((float)$reportThreshold)
            || abs((float)$reportThreshold - $this->threshold) > 1e-9) {
            return 'CALIBRATION_CONFIG_MISMATCH';
        }

        $counts = $report['sample_counts'] ?? [];
        if (!is_array($counts)) {
            return 'CALIBRATION_REPORT_INVALID';
        }
        $identityCount = (int)($counts['identity_count'] ?? 0);
        $sessionCount = (int)($counts['session_count'] ?? 0);
        $imageCount = (int)($counts['image_count'] ?? 0);
        $genuinePairCount = (int)($counts['genuine_pair_count'] ?? 0);
        $impostorPairCount = (int)($counts['impostor_pair_count'] ?? 0);
        if ($identityCount < self::MIN_CALIBRATION_IDENTITIES
            || $sessionCount < $identityCount * 2
            || $imageCount !== $sessionCount * 5
            || $genuinePairCount < self::MIN_GENUINE_PAIRS
            || $impostorPairCount < self::MIN_IMPOSTOR_PAIRS) {
            return 'CALIBRATION_DATA_INSUFFICIENT';
        }

        $targets = $report['targets'] ?? [];
        $metrics = $report['metrics'] ?? [];
        $targetFmr = $targets['max_fmr'] ?? null;
        $targetFnmr = $targets['max_fnmr'] ?? null;
        $fmr = $metrics['fmr'] ?? null;
        $fnmr = $metrics['fnmr'] ?? null;
        foreach ([$targetFmr, $targetFnmr, $fmr, $fnmr] as $rate) {
            if (!is_numeric($rate) || !is_finite((float)$rate)
                || (float)$rate < 0.0 || (float)$rate > 1.0) {
                return 'CALIBRATION_REPORT_INVALID';
            }
        }
        if ((int)($metrics['genuine_pair_count'] ?? -1) !== (int)$counts['genuine_pair_count']
            || (int)($metrics['impostor_pair_count'] ?? -1) !== (int)$counts['impostor_pair_count']
            || !is_numeric($metrics['false_match_count'] ?? null)
            || !is_numeric($metrics['false_non_match_count'] ?? null)
            || (int)$metrics['false_match_count'] < 0
            || (int)$metrics['false_match_count'] > $impostorPairCount
            || (int)$metrics['false_non_match_count'] < 0
            || (int)$metrics['false_non_match_count'] > $genuinePairCount
            || abs((float)$fmr - (int)$metrics['false_match_count'] / $impostorPairCount) > 1e-9
            || abs((float)$fnmr - (int)$metrics['false_non_match_count'] / $genuinePairCount) > 1e-9
            || !is_string($report['dataset_sha256'] ?? null)
            || !preg_match('/^[a-f0-9]{64}$/D', $report['dataset_sha256'])) {
            return 'CALIBRATION_REPORT_INVALID';
        }
        if ((float)$fmr > (float)$targetFmr || (float)$fnmr > (float)$targetFnmr) {
            return 'CALIBRATION_TARGETS_NOT_MET';
        }

        return null;
    }

    /** @return array{0:?array,1:string} */
    private function loadCalibrationReport(): array
    {
        $configuredPath = getenv('AI1_DUPLICATE_FACE_CALIBRATION_REPORT');
        if ($configuredPath === false || trim($configuredPath) === '') {
            return [null, 'CALIBRATION_REPORT_MISSING'];
        }
        $path = trim($configuredPath);
        if (!preg_match('/^(?:[A-Za-z]:[\\\\\/]|\\\\\\\\|\/)/', $path)) {
            $path = dirname(__DIR__) . DIRECTORY_SEPARATOR . $path;
        }
        if (!is_file($path) || !is_readable($path)) {
            return [null, 'CALIBRATION_REPORT_MISSING'];
        }
        $decoded = json_decode((string)file_get_contents($path), true);
        if (!is_array($decoded)) {
            return [null, 'CALIBRATION_REPORT_INVALID'];
        }

        return [$decoded, ''];
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
