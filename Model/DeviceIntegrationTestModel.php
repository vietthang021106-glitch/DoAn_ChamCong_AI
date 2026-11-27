<?php

declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class DeviceIntegrationTestModel
{
    public function saveCameraTest(?int $employeeId, string $filename, string $jpegBytes): int
    {
        $statement = Database::getConnection()->prepare(
            "INSERT INTO DeviceIntegrationTest
                (LoaiDuLieu, MaNV, TenFile, Anh, NhipTim, SpO2, ThoiGian)
             VALUES
                ('CAMERA', :employee_id, :filename, :image, NULL, NULL, CURRENT_TIMESTAMP(3))"
        );
        $statement->bindValue(':employee_id', $employeeId, $employeeId === null ? PDO::PARAM_NULL : PDO::PARAM_INT);
        $statement->bindValue(':filename', $filename, PDO::PARAM_STR);
        $statement->bindValue(':image', $jpegBytes, PDO::PARAM_LOB);
        $statement->execute();

        return (int) Database::getConnection()->lastInsertId();
    }

    public function saveHealthTest(?int $employeeId, int $heartRate, float $spo2): int
    {
        $statement = Database::getConnection()->prepare(
            "INSERT INTO DeviceIntegrationTest
                (LoaiDuLieu, MaNV, TenFile, Anh, NhipTim, SpO2, ThoiGian)
             VALUES
                ('HEALTH', :employee_id, NULL, NULL, :heart_rate, :spo2, CURRENT_TIMESTAMP(3))"
        );
        $statement->bindValue(':employee_id', $employeeId, $employeeId === null ? PDO::PARAM_NULL : PDO::PARAM_INT);
        $statement->bindValue(':heart_rate', $heartRate, PDO::PARAM_INT);
        $statement->bindValue(':spo2', $spo2);
        $statement->execute();

        return (int) Database::getConnection()->lastInsertId();
    }

    /** @return array{MaTest:mixed,TenFile:mixed,Anh:mixed}|null */
    public function getLatestCamera(): ?array
    {
        $statement = Database::getConnection()->prepare(
            "SELECT MaTest, TenFile, Anh
             FROM DeviceIntegrationTest
             WHERE LoaiDuLieu = 'CAMERA'
             ORDER BY MaTest DESC
             LIMIT 1"
        );
        $statement->execute();
        $record = $statement->fetch();

        return $record === false ? null : $record;
    }

    /** @return array{MaTest:mixed,TenFile:mixed,Anh:mixed}|null */
    public function getCameraById(int $testId): ?array
    {
        $statement = Database::getConnection()->prepare(
            "SELECT MaTest, TenFile, Anh
             FROM DeviceIntegrationTest
             WHERE MaTest = :test_id
               AND LoaiDuLieu = 'CAMERA'
             LIMIT 1"
        );
        $statement->bindValue(':test_id', $testId, PDO::PARAM_INT);
        $statement->execute();
        $record = $statement->fetch();

        return $record === false ? null : $record;
    }

    /** @return array<int, array<string, mixed>> */
    public function getLatestRecords(int $limit = 20): array
    {
        $statement = Database::getConnection()->prepare(
            "SELECT
                MaTest AS ma_test,
                LoaiDuLieu AS loai_du_lieu,
                MaNV AS ma_nv,
                TenFile AS ten_file,
                OCTET_LENGTH(Anh) AS kich_thuoc_anh,
                NhipTim AS nhip_tim,
                SpO2 AS spo2,
                ThoiGian AS thoi_gian
             FROM DeviceIntegrationTest
             ORDER BY MaTest DESC
             LIMIT :limit"
        );
        $statement->bindValue(':limit', $limit, PDO::PARAM_INT);
        $statement->execute();

        return $statement->fetchAll();
    }
}
