<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class HealthModel
{
    public function findEmployees(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaNV, HoTen
            FROM NhanVien
            ORDER BY MaNV
            SQL)->fetchAll();
    }

    public function findHistory(array $filters, int $page, int $pageSize): array
    {
        $where = [];
        $params = [];

        if ($filters['from_date'] !== '') {
            $where[] = 'SK.ThoiGian >= :from_date';
            $params['from_date'] = $filters['from_date'] . ' 00:00:00';
        }
        if ($filters['to_date'] !== '') {
            $where[] = 'SK.ThoiGian < DATE_ADD(:to_date, INTERVAL 1 DAY)';
            $params['to_date'] = $filters['to_date'] . ' 00:00:00';
        }
        if ($filters['employee_id'] !== null) {
            $where[] = 'SK.MaNV = :employee_id';
            $params['employee_id'] = $filters['employee_id'];
        }
        if ($filters['keyword'] !== '') {
            $where[] = "(
                CAST(SK.MaNV AS CHAR) LIKE :employee_code
                OR CONCAT('NV', LPAD(SK.MaNV, 3, '0')) LIKE :formatted_employee_code
                OR NV.HoTen LIKE :employee_name
            )";
            $pattern = '%' . $filters['keyword'] . '%';
            $params['employee_code'] = $pattern;
            $params['formatted_employee_code'] = $pattern;
            $params['employee_name'] = $pattern;
        }

        $fromSql = <<<'SQL'
            FROM LichSuSucKhoe SK
            INNER JOIN NhanVien NV ON NV.MaNV = SK.MaNV
            SQL;
        $whereSql = $where === [] ? '' : ' WHERE ' . implode(' AND ', $where);
        $pdo = Database::getConnection();

        $count = $pdo->prepare('SELECT COUNT(*) ' . $fromSql . $whereSql);
        $count->execute($params);
        $totalRows = (int)$count->fetchColumn();

        $offset = ($page - 1) * $pageSize;
        $statement = $pdo->prepare(<<<SQL
            SELECT SK.MaSK, SK.MaNV, NV.HoTen, SK.NhipTim, SK.SpO2, SK.ThoiGian
            {$fromSql}
            {$whereSql}
            ORDER BY SK.ThoiGian DESC, SK.MaSK DESC
            LIMIT :limit OFFSET :offset
            SQL);
        foreach ($params as $name => $value) {
            $statement->bindValue(':' . $name, $value);
        }
        $statement->bindValue(':limit', $pageSize, PDO::PARAM_INT);
        $statement->bindValue(':offset', $offset, PDO::PARAM_INT);
        $statement->execute();

        return ['records' => $statement->fetchAll(), 'total' => $totalRows];
    }

    public function findChartData(int $limit = 20): array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT NV.HoTen, SK.NhipTim, SK.ThoiGian
            FROM LichSuSucKhoe SK
            INNER JOIN NhanVien NV ON NV.MaNV = SK.MaNV
            ORDER BY SK.ThoiGian DESC, SK.MaSK DESC
            LIMIT :limit
            SQL);
        $statement->bindValue(':limit', $limit, PDO::PARAM_INT);
        $statement->execute();

        return array_reverse($statement->fetchAll());
    }
}
