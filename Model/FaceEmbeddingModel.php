<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class FaceEmbeddingModel
{
    public function findAllForInternalGallery(): array
    {
        $rows = Database::getConnection()->query(<<<'SQL'
            SELECT MaNV, MaEmbedding, SoChieu, VectorData
            FROM FaceEmbedding
            ORDER BY MaNV, MaEmbedding
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
                'so_chieu' => $dimensions,
                'vector' => base64_encode($vector),
                'sha256' => hash('sha256', $vector),
            ];
        }

        return $embeddings;
    }
}
