<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

/** Database access for rejected scans that did not create or update ChamCong. */
final class ScanHistoryModel
{
    private const REASON_CODES = [
        'KHONG_NHAN_DIEN',
        'NHIEU_KHUON_MAT',
        'KHONG_CO_PHAN_CA',
        'CA_DA_KET_THUC',
        'DA_HOAN_THANH',
    ];

    public function reasonLabels(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaCode, TenLyDo
            FROM LoaiLyDoQuet
            WHERE TrangThai = 1
            ORDER BY MaLyDo
            SQL)->fetchAll(PDO::FETCH_KEY_PAIR);
    }

    public function reasonLabel(string $reason): string
    {
        $statement = Database::getConnection()->prepare(
            'SELECT TenLyDo FROM LoaiLyDoQuet WHERE MaCode = :code'
        );
        $statement->execute(['code' => $reason]);

        return $statement->fetchColumn() ?: 'Lý do không hợp lệ';
    }

    /** Resolve a supported active MaCode without relying on fixed catalog IDs. */
    public function findReasonIdByCode(string $code): ?int
    {
        if (!in_array($code, self::REASON_CODES, true)) {
            return null;
        }
        $statement = Database::getConnection()->prepare(
            'SELECT MaLyDo FROM LoaiLyDoQuet WHERE MaCode = :code AND TrangThai = 1'
        );
        $statement->execute(['code' => $code]);
        $id = $statement->fetchColumn();

        return $id === false ? null : (int)$id;
    }

    private function requireReasonId(string $code): int
    {
        $id = $this->findReasonIdByCode($code);
        if ($id === null) {
            throw new InvalidArgumentException('Lý do quét không hợp lệ hoặc đã ngừng sử dụng.');
        }

        return $id;
    }

    /** Return one SQL-paginated page with employee, device, and shift labels. */
    public function findPaginated(array $filters, int $limit, int $offset): array
    {
        [$where, $params] = $this->buildFilters($filters);
        $statement = Database::getConnection()->prepare(<<<SQL
            SELECT
                SQ.MaLanQuet, SQ.MaNV, NV.HoTen, SQ.MaTB, TB.LoaiTB,
                SQ.MaCa, CLV.TenCa, SQ.ThoiGianQuet, SQ.MaLyDo,
                LD.MaCode, LD.TenLyDo,
                SQ.SoKhuonMat, SQ.DoTinCay, SQ.ChiTiet,
                CASE WHEN OCTET_LENGTH(SQ.AnhQuet) > 0 THEN 1 ELSE 0 END AS HasImage
            FROM LichSuQuet SQ
            INNER JOIN LoaiLyDoQuet LD ON LD.MaLyDo = SQ.MaLyDo
            LEFT JOIN NhanVien NV ON NV.MaNV = SQ.MaNV
            LEFT JOIN ThietBi TB ON TB.MaTB = SQ.MaTB
            LEFT JOIN CaLamViec CLV ON CLV.MaCa = SQ.MaCa
            WHERE 1 = 1 {$where}
            ORDER BY SQ.ThoiGianQuet DESC, SQ.MaLanQuet DESC
            LIMIT :limit OFFSET :offset
            SQL);
        foreach ($params as $name => $value) {
            $statement->bindValue(':' . $name, $value, is_int($value) ? PDO::PARAM_INT : PDO::PARAM_STR);
        }
        $statement->bindValue(':limit', $limit, PDO::PARAM_INT);
        $statement->bindValue(':offset', max(0, $offset), PDO::PARAM_INT);
        $statement->execute();

        return $statement->fetchAll();
    }

    /** Count rows with the same validated filters used by findPaginated(). */
    public function countFiltered(array $filters): int
    {
        [$where, $params] = $this->buildFilters($filters);
        $statement = Database::getConnection()->prepare(
            "SELECT COUNT(*) FROM LichSuQuet SQ WHERE 1 = 1 {$where}"
        );
        $statement->execute($params);

        return (int)$statement->fetchColumn();
    }

    /** Return the stored JPEG bytes for the protected image response. */
    public function findImageById(int $scanId): ?string
    {
        $statement = Database::getConnection()->prepare(
            'SELECT AnhQuet FROM LichSuQuet WHERE MaLanQuet = :scan_id'
        );
        $statement->execute(['scan_id' => $scanId]);
        $image = $statement->fetchColumn();

        return is_string($image) && $image !== '' ? $image : null;
    }

    /** Check whether an equivalent rejected scan was stored in the last 30 seconds. */
    public function existsRecentDuplicate(
        ?int $deviceId,
        ?int $employeeId,
        string $reason,
        ?string $referenceTime = null
    ): bool {
        $deviceClause = $deviceId === null ? 'SQ.MaTB IS NULL' : 'SQ.MaTB = :device_id';
        $employeeClause = $employeeId === null ? 'SQ.MaNV IS NULL' : 'SQ.MaNV = :employee_id';
        $reasonId = $this->requireReasonId($reason);
        $timeClause = $referenceTime === null
            ? 'SQ.ThoiGianQuet > DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 30 SECOND)'
            : 'SQ.ThoiGianQuet > DATE_SUB(:reference_time_start, INTERVAL 30 SECOND)
                AND SQ.ThoiGianQuet <= :reference_time_end';
        $statement = Database::getConnection()->prepare(<<<SQL
            SELECT 1
            FROM LichSuQuet SQ
            WHERE {$deviceClause}
                AND {$employeeClause}
                AND SQ.MaLyDo = :reason_id
                AND {$timeClause}
            LIMIT 1
            SQL);
        if ($deviceId !== null) {
            $statement->bindValue(':device_id', $deviceId, PDO::PARAM_INT);
        }
        if ($employeeId !== null) {
            $statement->bindValue(':employee_id', $employeeId, PDO::PARAM_INT);
        }
        $statement->bindValue(':reason_id', $reasonId, PDO::PARAM_INT);
        if ($referenceTime !== null) {
            $this->validateDateTime($referenceTime);
            $statement->bindValue(':reference_time_start', $referenceTime, PDO::PARAM_STR);
            $statement->bindValue(':reference_time_end', $referenceTime, PDO::PARAM_STR);
        }
        $statement->execute();

        return $statement->fetchColumn() !== false;
    }

    /** Validate and store one scan record, returning its new primary key. */
    public function create(array $scan): int
    {
        $this->validateScan($scan);
        $db = Database::getConnection();
        $fields = [
            'MaNV' => $scan['MaNV'] ?? null,
            'MaTB' => $scan['MaTB'] ?? null,
            'MaCa' => $scan['MaCa'] ?? null,
            'MaLyDo' => $this->requireReasonId($scan['LyDo']),
            'AnhQuet' => $scan['AnhQuet'],
            'SoKhuonMat' => $scan['SoKhuonMat'] ?? null,
            'DoTinCay' => $scan['DoTinCay'] ?? null,
            'ChiTiet' => $scan['ChiTiet'] ?? null,
        ];
        $columns = array_keys($fields);
        $placeholders = array_map(static fn(string $column): string => ':' . $column, $columns);
        $sql = 'INSERT INTO LichSuQuet (' . implode(', ', $columns) . ') VALUES (' . implode(', ', $placeholders) . ')';
        if (isset($scan['ThoiGianQuet'])) {
            $sql = 'INSERT INTO LichSuQuet (ThoiGianQuet, ' . implode(', ', $columns) . ') VALUES (:ThoiGianQuet, ' . implode(', ', $placeholders) . ')';
        }
        $statement = $db->prepare($sql);
        if (isset($scan['ThoiGianQuet'])) {
            $statement->bindValue(':ThoiGianQuet', $scan['ThoiGianQuet'], PDO::PARAM_STR);
        }
        foreach ($fields as $name => $value) {
            $type = match (true) {
                $name === 'AnhQuet' => PDO::PARAM_LOB,
                $value === null => PDO::PARAM_NULL,
                is_int($value) => PDO::PARAM_INT,
                default => PDO::PARAM_STR,
            };
            $statement->bindValue(':' . $name, $value, $type);
        }
        $statement->execute();

        return (int)$db->lastInsertId();
    }

    /** Atomically apply the cooldown for one device/employee/reason tuple. */
    public function createUnlessRecentDuplicate(array $scan): ?int
    {
        $this->validateScan($scan);
        $deviceId = $scan['MaTB'] ?? null;
        $employeeId = $scan['MaNV'] ?? null;
        $reason = $scan['LyDo'];
        $reasonId = $this->requireReasonId($reason);
        $lockName = 'scan_' . substr(hash('sha256', json_encode([
            $deviceId,
            $employeeId,
            $reasonId,
        ], JSON_THROW_ON_ERROR)), 0, 58);
        $db = Database::getConnection();
        $lock = $db->prepare('SELECT GET_LOCK(:lock_name, 5)');
        $lock->execute(['lock_name' => $lockName]);
        if ((int)$lock->fetchColumn() !== 1) {
            throw new RuntimeException('Không thể khóa chống ghi trùng lịch sử quét.');
        }

        try {
            if ($this->existsRecentDuplicate($deviceId, $employeeId, $reason)) {
                return null;
            }

            return $this->create($scan);
        } finally {
            $release = $db->prepare('SELECT RELEASE_LOCK(:lock_name)');
            $release->execute(['lock_name' => $lockName]);
        }
    }

    public function findDevices(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaTB, LoaiTB
            FROM ThietBi
            ORDER BY MaTB
            SQL)->fetchAll();
    }

    private function buildFilters(array $filters): array
    {
        $clauses = [];
        $params = [];
        if (($filters['date'] ?? null) !== null) {
            $clauses[] = 'SQ.ThoiGianQuet >= :date_start AND SQ.ThoiGianQuet < :date_end';
            $params['date_start'] = $filters['date'] . ' 00:00:00';
            $params['date_end'] = (new DateTimeImmutable($filters['date']))->modify('+1 day')->format('Y-m-d') . ' 00:00:00';
        }
        foreach (['employee_id' => 'SQ.MaNV', 'device_id' => 'SQ.MaTB'] as $key => $column) {
            if (($filters[$key] ?? null) !== null) {
                $placeholder = $key === 'employee_id' ? 'employee_id' : 'device_id';
                $clauses[] = "{$column} = :{$placeholder}";
                $params[$placeholder] = $filters[$key];
            }
        }
        if (($filters['reason'] ?? null) !== null) {
            $clauses[] = 'SQ.MaLyDo = :reason_id';
            $params['reason_id'] = $this->requireReasonId($filters['reason']);
        }

        return [$clauses === [] ? '' : ' AND ' . implode(' AND ', $clauses), $params];
    }

    private function validateScan(array $scan): void
    {
        $reason = $scan['LyDo'] ?? null;
        if (!is_string($reason) || !in_array($reason, self::REASON_CODES, true)) {
            throw new InvalidArgumentException('Lý do quét không hợp lệ.');
        }
        $employeeId = $scan['MaNV'] ?? null;
        if (in_array($reason, ['KHONG_NHAN_DIEN', 'NHIEU_KHUON_MAT'], true) && $employeeId !== null) {
            throw new InvalidArgumentException('Lý do này không được gắn với một nhân viên cụ thể.');
        }
        if (in_array($reason, ['KHONG_CO_PHAN_CA', 'CA_DA_KET_THUC', 'DA_HOAN_THANH'], true) && $employeeId === null) {
            throw new InvalidArgumentException('Lý do này yêu cầu nhân viên đã được nhận diện.');
        }
        if ($reason === 'NHIEU_KHUON_MAT' && isset($scan['SoKhuonMat']) && $scan['SoKhuonMat'] < 2) {
            throw new InvalidArgumentException('Lý do nhiều khuôn mặt yêu cầu ít nhất 2 khuôn mặt.');
        }
        foreach (['MaNV' => 'NhanVien', 'MaTB' => 'ThietBi', 'MaCa' => 'CaLamViec'] as $key => $table) {
            $id = $scan[$key] ?? null;
            if ($id !== null && (!is_int($id) || $id < 1 || !$this->foreignKeyExists($table, $id))) {
                throw new InvalidArgumentException($key . ' không hợp lệ.');
            }
        }

        $image = $scan['AnhQuet'] ?? null;
        if (!is_string($image) || $image === '') {
            throw new InvalidArgumentException('Ảnh quét không được để trống.');
        }
        $mime = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);
        $imageInfo = @getimagesizefromstring($image);
        if ($mime !== 'image/jpeg' || !is_array($imageInfo) || ($imageInfo['mime'] ?? '') !== 'image/jpeg') {
            throw new InvalidArgumentException('Ảnh quét phải là JPEG hợp lệ.');
        }

        $faceCount = $scan['SoKhuonMat'] ?? null;
        if ($faceCount !== null && (!is_int($faceCount) || $faceCount < 0 || $faceCount > 255)) {
            throw new InvalidArgumentException('Số khuôn mặt không hợp lệ.');
        }
        $confidence = $scan['DoTinCay'] ?? null;
        if ($confidence !== null && (!is_numeric($confidence) || !is_finite((float)$confidence) || (float)$confidence < 0 || (float)$confidence > 1)) {
            throw new InvalidArgumentException('Độ tin cậy phải nằm trong khoảng 0 đến 1.');
        }
        $detail = $scan['ChiTiet'] ?? null;
        if ($detail !== null && (!is_string($detail) || mb_strlen($detail, 'UTF-8') > 255)) {
            throw new InvalidArgumentException('Chi tiết không được vượt quá 255 ký tự.');
        }
        if (isset($scan['ThoiGianQuet'])) {
            $this->validateDateTime((string)$scan['ThoiGianQuet']);
        }
    }

    private function foreignKeyExists(string $table, int $id): bool
    {
        $columns = [
            'NhanVien' => 'MaNV',
            'ThietBi' => 'MaTB',
            'CaLamViec' => 'MaCa',
        ];
        $column = $columns[$table] ?? null;
        if ($column === null) {
            return false;
        }
        $statement = Database::getConnection()->prepare("SELECT 1 FROM {$table} WHERE {$column} = :id LIMIT 1");
        $statement->execute(['id' => $id]);

        return $statement->fetchColumn() !== false;
    }

    private function validateDateTime(string $value): void
    {
        try {
            new DateTimeImmutable($value);
        } catch (Throwable) {
            throw new InvalidArgumentException('Thời gian quét không hợp lệ.');
        }
    }
}
