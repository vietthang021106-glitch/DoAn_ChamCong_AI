<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';
require_once __DIR__ . '/../Service/FaceDuplicateChecker.php';

final class FaceEnrollmentConflict extends RuntimeException
{
}

final class FaceEmbeddingModel
{
    private ?PDO $connection;
    private FaceDuplicateChecker $duplicateChecker;

    public function __construct(?PDO $connection = null, ?FaceDuplicateChecker $duplicateChecker = null)
    {
        $this->connection = $connection;
        $this->duplicateChecker = $duplicateChecker ?? new FaceDuplicateChecker();
    }

    /** Lấy metadata các mẫu khuôn mặt của nhân viên, không tải blob ảnh vào danh sách. */
    public function findByEmployee(int $employeeId): array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT MaEmbedding, MaNV, SoChieu, ThoiGianTao,
                   CASE WHEN AnhKhuonMat IS NULL THEN 0 ELSE 1 END AS HasImage
            FROM FaceEmbedding
            WHERE MaNV = :employee_id
            ORDER BY MaEmbedding
            SQL);
        $statement->execute(['employee_id' => $employeeId]);

        return $statement->fetchAll();
    }

    /** Đọc blob ảnh và chủ sở hữu theo MaEmbedding để controller kiểm tra quyền truy cập. */
    public function findImageById(int $embeddingId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT MaEmbedding, MaNV, AnhKhuonMat
            FROM FaceEmbedding
            WHERE MaEmbedding = :embedding_id
            SQL);
        $statement->execute(['embedding_id' => $embeddingId]);
        $row = $statement->fetch();

        return $row === false ? null : $row;
    }

    /** Đếm số embedding hiện lưu của một nhân viên. */
    public function countByEmployee(int $employeeId): int
    {
        $statement = ($this->connection ?? Database::getConnection())->prepare(
            'SELECT COUNT(*) FROM FaceEmbedding WHERE MaNV = :employee_id'
        );
        $statement->execute(['employee_id' => $employeeId]);

        return (int)$statement->fetchColumn();
    }

    /** Count embeddings for active employees, matching the AI gallery endpoint. */
    public function countAllActive(): int
    {
        $pdo = $this->connection ?? Database::getConnection();
        $activeEmployee = Database::activeEmployeePredicate('nv', $pdo);
        $statement = $pdo->query(
            'SELECT COUNT(*) FROM FaceEmbedding fe '
            . 'INNER JOIN NhanVien nv ON nv.MaNV = fe.MaNV WHERE ' . $activeEmployee
        );

        return (int)$statement->fetchColumn();
    }

    /** Reload the committed batch and compare all five vectors and images byte-for-byte. */
    public function verifyBatchByEmployee(int $employeeId, array $samples): bool
    {
        try {
            $samples = $this->validateSamples($samples);
        } catch (Throwable $exception) {
            return false;
        }
        $statement = ($this->connection ?? Database::getConnection())->prepare(<<<'SQL'
            SELECT SoChieu, VectorData, AnhKhuonMat
            FROM FaceEmbedding
            WHERE MaNV = :employee_id
            ORDER BY MaEmbedding
            SQL);
        $statement->execute(['employee_id' => $employeeId]);
        $rows = $statement->fetchAll();
        if (count($rows) !== 5) {
            return false;
        }
        foreach ($rows as $index => $row) {
            if ((int)($row['SoChieu'] ?? 0) !== 512
                || $this->lobBytes($row['VectorData'] ?? null) !== $samples[$index]['vector']
                || $this->lobBytes($row['AnhKhuonMat'] ?? null) !== $samples[$index]['image']) {
                return false;
            }
        }

        return true;
    }

    /** Stable hash for one employee's samples, without changing the DB schema. */
    public function enrollmentRevision(int $employeeId): array
    {
        $statement = ($this->connection ?? Database::getConnection())->prepare(<<<'SQL'
            SELECT MaEmbedding, VectorData
            FROM FaceEmbedding
            WHERE MaNV = :employee_id
            ORDER BY MaEmbedding
            SQL);
        $statement->execute(['employee_id' => $employeeId]);
        $rows = $statement->fetchAll();

        return ['count' => count($rows), 'revision' => $this->revisionFromRows($rows)];
    }

    /**
     * Read-only duplicate precheck for the five pending samples. The final save
     * always repeats this against the locked, latest gallery.
     */
    public function checkDuplicate(int $employeeId, array $samples): array
    {
        try {
            $validated = $this->validateSamples($samples);
        } catch (Throwable $exception) {
            return $this->duplicateChecker->unavailable('INVALID_NEW_SAMPLES');
        }
        try {
            $pdo = $this->connection ?? Database::getConnection();
            $rows = $this->loadOtherEmployeeGalleryRows($pdo, $employeeId, false);
            return $this->duplicateChecker->evaluate($employeeId, $validated, $rows);
        } catch (Throwable $exception) {
            return $this->duplicateChecker->unavailable('GALLERY_UNAVAILABLE');
        }
    }

    /** Xóa toàn bộ embedding của đúng nhân viên trong transaction và trả số row bị xóa. */
    public function deleteByEmployee(int $employeeId): int
    {
        $pdo = Database::getConnection();
        $pdo->beginTransaction();
        try {
            $statement = $pdo->prepare('DELETE FROM FaceEmbedding WHERE MaNV = :employee_id');
            $statement->execute(['employee_id' => $employeeId]);
            $deleted = $statement->rowCount();
            $pdo->commit();

            return $deleted;
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    /** Thay batch 5 pose nguyên tử; batch mới lỗi sẽ rollback và giữ nguyên mẫu cũ. */
    public function replaceByEmployee(
        int $employeeId,
        array $samples,
        string $expectedRevision,
        ?array &$saveContext = null,
        bool $demoUnverifiedConfirmed = false
    ): array
    {
        $saveContext = ['demo_duplicate_check_skipped' => false, 'duplicate_check' => null];
        $samples = $this->validateSamples($samples);
        if (!preg_match('/^[a-f0-9]{64}$/D', $expectedRevision)) {
            throw new InvalidArgumentException('Enrollment gallery revision is invalid.');
        }
        $pdo = $this->connection ?? Database::getConnection();
        $driver = (string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME);
        $lockName = 'ai1_face_gallery_enrollment';
        $lockAcquired = false;
        try {
            if ($driver === 'mysql') {
                try {
                    $lock = $pdo->prepare('SELECT GET_LOCK(:lock_name, 10)');
                    $lock->execute(['lock_name' => $lockName]);
                    $lockAcquired = (int)$lock->fetchColumn() === 1;
                } catch (Throwable $exception) {
                    throw new FaceDuplicateCheckException(
                        $this->duplicateChecker->unavailable('GALLERY_ENROLLMENT_LOCK_UNAVAILABLE')
                    );
                }
                if (!$lockAcquired) {
                    throw new FaceDuplicateCheckException(
                        $this->duplicateChecker->unavailable('GALLERY_ENROLLMENT_LOCK_UNAVAILABLE')
                    );
                }
            }

            $pdo->beginTransaction();
            $activeEmployee = Database::activeEmployeePredicate('', $pdo);
            $forUpdate = $driver === 'mysql' ? ' FOR UPDATE' : '';
            $employee = $pdo->prepare(
                'SELECT MaNV FROM NhanVien WHERE MaNV = :employee_id AND ' . $activeEmployee . $forUpdate
            );
            $employee->execute(['employee_id' => $employeeId]);
            if ($employee->fetchColumn() === false) {
                throw new RuntimeException('Không tìm thấy nhân viên.');
            }

            $currentSql = <<<'SQL'
                SELECT MaEmbedding, SoChieu, VectorData, AnhKhuonMat
                FROM FaceEmbedding
                WHERE MaNV = :employee_id
                ORDER BY MaEmbedding
                SQL;
            if ($driver === 'mysql') {
                $currentSql .= ' FOR UPDATE';
            }
            $currentStatement = $pdo->prepare($currentSql);
            $currentStatement->execute(['employee_id' => $employeeId]);
            $currentRows = $currentStatement->fetchAll();
            if ($this->matchesSamples($currentRows, $samples)) {
                $this->requireDuplicateCheckOrLocalDemoBypass(
                    $pdo, $employeeId, $samples, $saveContext, $demoUnverifiedConfirmed
                );
                $ids = array_map(static fn(array $row): int => (int)$row['MaEmbedding'], $currentRows);
                $pdo->commit();
                return $ids;
            }
            $currentRevision = $this->revisionFromRows($currentRows);
            if (!hash_equals($expectedRevision, $currentRevision)) {
                throw new FaceEnrollmentConflict('Gallery đã thay đổi trong lúc đăng ký. Hãy tải lại và đăng ký lại.');
            }

            $this->requireDuplicateCheckOrLocalDemoBypass(
                $pdo, $employeeId, $samples, $saveContext, $demoUnverifiedConfirmed
            );

            $delete = $pdo->prepare('DELETE FROM FaceEmbedding WHERE MaNV = :employee_id');
            $delete->execute(['employee_id' => $employeeId]);
            $ids = $this->insertSamples($pdo, $employeeId, $samples);
            if (count($ids) !== 5 || !$this->verifyBatchUsingConnection($pdo, $employeeId, $samples)) {
                throw new RuntimeException('Saved enrollment batch did not pass transactional read-back verification.');
            }
            $pdo->commit();

            return $ids;
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        } finally {
            if ($lockAcquired) {
                try {
                    $release = $pdo->prepare('SELECT RELEASE_LOCK(:lock_name)');
                    $release->execute(['lock_name' => $lockName]);
                } catch (Throwable $exception) {
                    error_log('Face enrollment advisory lock release failed.');
                }
            }
        }
    }

    /** Keep duplicate decisions authoritative; only an explicitly enabled local demo can
     * proceed when the check is unavailable solely because calibration is missing. */
    private function requireDuplicateCheckOrLocalDemoBypass(
        PDO $pdo,
        int $employeeId,
        array $samples,
        array &$saveContext,
        bool $demoUnverifiedConfirmed
    ): void {
        $result = $this->checkDuplicateInsideTransaction($pdo, $employeeId, $samples);
        $saveContext['duplicate_check'] = $result;
        if (($result['status'] ?? null) === 'CLEAR') {
            return;
        }
        if ($demoUnverifiedConfirmed
            && FaceDuplicateChecker::isLocalDemoBypassEnabled()
            && FaceDuplicateChecker::isDemoBypassableUnavailable($result)) {
            $saveContext['demo_duplicate_check_skipped'] = true;
            error_log(sprintf(
                'AI1_ENROLLMENT_DEMO_UNCHECKED employee_id=%d duplicate_check=%s reason=%s',
                $employeeId,
                (string)($result['status'] ?? 'UNKNOWN'),
                (string)($result['reason'] ?? 'UNKNOWN')
            ));
            return;
        }
        throw new FaceDuplicateCheckException($result);
    }

    private function checkDuplicateInsideTransaction(PDO $pdo, int $employeeId, array $samples): array
    {
        try {
            $rows = $this->loadOtherEmployeeGalleryRows($pdo, $employeeId, true);
        } catch (Throwable $exception) {
            return $this->duplicateChecker->unavailable('GALLERY_UNAVAILABLE');
        }

        return $this->duplicateChecker->evaluate($employeeId, $samples, $rows);
    }

    /** Load the same active-employee gallery used by recognition, optionally locking its rows. */
    private function loadOtherEmployeeGalleryRows(PDO $pdo, int $employeeId, bool $lockRows): array
    {
        $activeEmployee = Database::activeEmployeePredicate('nv', $pdo);
        $sql = <<<SQL
            SELECT fe.MaNV, fe.MaEmbedding, fe.SoChieu, fe.VectorData, nv.HoTen
            FROM FaceEmbedding fe
            INNER JOIN NhanVien nv ON nv.MaNV = fe.MaNV
            WHERE fe.MaNV <> :employee_id AND {$activeEmployee}
            ORDER BY fe.MaNV, fe.MaEmbedding
            SQL;
        if ($lockRows && (string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME) === 'mysql') {
            $sql .= ' FOR UPDATE';
        }
        $statement = $pdo->prepare($sql);
        $statement->execute(['employee_id' => $employeeId]);

        return $statement->fetchAll();
    }

    /** Kiểm tra đủ 5 pose theo thứ tự, vector 512D và ảnh JPEG/PNG hợp lệ trước khi ghi. */
    private function validateSamples(array $samples): array
    {
        $poses = ['frontal', 'left', 'right', 'up', 'down'];
        if (count($samples) !== count($poses)) {
            throw new InvalidArgumentException('Enrollment requires exactly five samples.');
        }

        $samples = array_values($samples);
        $normalizedVectors = [];
        foreach ($samples as $index => $sample) {
            $vector = $sample['vector'] ?? null;
            $image = $sample['image'] ?? null;
            if (($sample['pose'] ?? null) !== $poses[$index]
                || !is_string($vector) || strlen($vector) !== 2048
                || !is_string($image) || $image === '') {
                throw new InvalidArgumentException('Each sample must include a 512D vector and an image.');
            }
            $normalized = $this->normalizeStoredVector($vector);
            $samples[$index]['vector'] = $normalized['bytes'];
            $normalizedVectors[] = $normalized['values'];
            $mime = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);
            if (!in_array($mime, ['image/jpeg', 'image/png'], true) || getimagesizefromstring($image) === false) {
                throw new InvalidArgumentException('Sample image must be a valid JPEG or PNG.');
            }
            if (strlen($image) > 5 * 1024 * 1024) {
                throw new InvalidArgumentException('Sample image exceeds the 5 MB limit.');
            }
        }

        foreach (array_slice($normalizedVectors, 1) as $vector) {
            $similarity = 0.0;
            foreach ($normalizedVectors[0] as $offset => $value) {
                $similarity += $value * $vector[$offset];
            }
            if (!is_finite($similarity) || $similarity < 0.45) {
                throw new InvalidArgumentException('Các mẫu 5 góc không cùng một danh tính.');
            }
        }

        return $samples;
    }

    /** Decode little-endian float32 bytes, validate finite 512D, and re-normalize. */
    private function normalizeStoredVector(string $bytes): array
    {
        $values = unpack('g*', $bytes);
        if (!is_array($values) || count($values) !== 512) {
            throw new InvalidArgumentException('Embedding must contain exactly 512 float32 values.');
        }
        $normSquared = 0.0;
        foreach ($values as $value) {
            if (!is_finite((float)$value)) {
                throw new InvalidArgumentException('Embedding contains a non-finite value.');
            }
            $normSquared += (float)$value * (float)$value;
        }
        $norm = sqrt($normSquared);
        if (!is_finite($norm) || $norm <= 1e-12) {
            throw new InvalidArgumentException('Embedding has an invalid norm.');
        }
        $normalized = [];
        foreach ($values as $value) {
            $normalized[] = (float)$value / $norm;
        }
        $packed = pack('g*', ...$normalized);
        $roundTrip = unpack('g*', $packed);

        return ['bytes' => $packed, 'values' => array_values($roundTrip)];
    }

    private function revisionFromRows(array $rows): string
    {
        $pairs = [];
        foreach ($rows as $row) {
            $vector = $this->lobBytes($row['VectorData'] ?? null);
            $pairs[] = [(int)$row['MaEmbedding'], hash('sha256', $vector)];
        }
        usort($pairs, static fn(array $left, array $right): int => $left[0] <=> $right[0]);

        return hash('sha256', json_encode($pairs, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES));
    }

    private function matchesSamples(array $rows, array $samples): bool
    {
        if (count($rows) !== count($samples)) {
            return false;
        }
        foreach ($rows as $index => $row) {
            if ((int)($row['SoChieu'] ?? 0) !== 512
                || $this->lobBytes($row['VectorData'] ?? null) !== $samples[$index]['vector']
                || $this->lobBytes($row['AnhKhuonMat'] ?? null) !== $samples[$index]['image']) {
                return false;
            }
        }
        return true;
    }

    private function lobBytes(mixed $value): string
    {
        if (is_resource($value)) {
            @rewind($value);
            $value = stream_get_contents($value);
        }
        if (!is_string($value)) {
            throw new RuntimeException('Database returned an invalid embedding blob.');
        }

        return $value;
    }

    /** Chèn các cặp ảnh/vector đã validate bằng cùng kết nối transaction. */
    private function insertSamples(PDO $pdo, int $employeeId, array $samples): array
    {
        $timestampExpression = (string)$pdo->getAttribute(PDO::ATTR_DRIVER_NAME) === 'mysql'
            ? 'CURRENT_TIMESTAMP(3)'
            : 'CURRENT_TIMESTAMP';
        $statement = $pdo->prepare(
            'INSERT INTO FaceEmbedding (MaNV, VectorData, AnhKhuonMat, SoChieu, ThoiGianTao) '
            . 'VALUES (:employee_id, :vector, :image, 512, ' . $timestampExpression . ')'
        );
        $ids = [];
        foreach ($samples as $sample) {
            $statement->bindValue(':employee_id', $employeeId, PDO::PARAM_INT);
            $statement->bindValue(':vector', $sample['vector'], PDO::PARAM_LOB);
            $statement->bindValue(':image', $sample['image'], PDO::PARAM_LOB);
            $statement->execute();
            $ids[] = (int)$pdo->lastInsertId();
        }

        return $ids;
    }

    /** Verify the exact five persisted samples before the transaction commits. */
    private function verifyBatchUsingConnection(PDO $pdo, int $employeeId, array $samples): bool
    {
        $statement = $pdo->prepare(<<<'SQL'
            SELECT SoChieu, VectorData, AnhKhuonMat
            FROM FaceEmbedding
            WHERE MaNV = :employee_id
            ORDER BY MaEmbedding
            SQL);
        $statement->execute(['employee_id' => $employeeId]);
        $rows = $statement->fetchAll();
        if (count($rows) !== 5) {
            return false;
        }
        foreach ($rows as $index => $row) {
            if ((int)($row['SoChieu'] ?? 0) !== 512
                || $this->lobBytes($row['VectorData'] ?? null) !== $samples[$index]['vector']
                || $this->lobBytes($row['AnhKhuonMat'] ?? null) !== $samples[$index]['image']) {
                return false;
            }
        }

        return true;
    }

    /** Đọc gallery cho AI nội bộ và base64 hóa vector chỉ ở ranh giới HTTP/JSON. */
    public function findAllForInternalGallery(): array
    {
        $connection = $this->connection ?? Database::getConnection();
        $activeEmployee = Database::activeEmployeePredicate('nv', $connection);
        $rows = $connection->query(<<<SQL
            SELECT fe.MaNV, fe.MaEmbedding, fe.SoChieu, fe.VectorData, nv.HoTen
            FROM FaceEmbedding fe
            INNER JOIN NhanVien nv ON nv.MaNV = fe.MaNV
            WHERE {$activeEmployee}
            ORDER BY fe.MaNV, fe.MaEmbedding
            SQL)->fetchAll();

        $embeddings = [];
        foreach ($rows as $row) {
            $vector = $row['VectorData'];
            $dimensions = (int)$row['SoChieu'];
            if (!is_string($vector) || $dimensions !== 512 || strlen($vector) !== 2048) {
                throw new RuntimeException('Invalid stored face embedding.');
            }

            $embeddings[] = [
                'ma_nv' => (int)$row['MaNV'],
                'ma_embedding' => (int)$row['MaEmbedding'],
                'ho_ten' => (string)($row['HoTen'] ?? ''),
                'so_chieu' => $dimensions,
                'vector' => base64_encode($vector),
                'sha256' => hash('sha256', $vector),
            ];
        }

        return $embeddings;
    }
}
