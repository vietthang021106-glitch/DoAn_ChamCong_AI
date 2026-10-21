<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/ScanHistoryModel.php';

/** Records only rejected scans that did not create or update a ChamCong row. */
final class ScanHistoryService
{
    public function __construct(private ?ScanHistoryModel $model = null)
    {
        $this->model ??= new ScanHistoryModel();
    }

    /**
     * Store a failed/rejected scan unless its matching event was saved in the last 30 seconds.
     *
     * @param string $lyDo Stable MaCode; the model resolves MaLyDo for storage and cooldown.
     * @return int|null New MaLanQuet, or null when the cooldown suppresses a duplicate.
     */
    public function recordFailedScan(
        ?int $maNV,
        ?int $maTB,
        ?int $maCa,
        string $lyDo,
        string $anhQuet,
        ?int $soKhuonMat = null,
        ?float $doTinCay = null,
        ?string $chiTiet = null
    ): ?int {
        return $this->model->createUnlessRecentDuplicate([
            'MaNV' => $maNV,
            'MaTB' => $maTB,
            'MaCa' => $maCa,
            'LyDo' => $lyDo,
            'AnhQuet' => $anhQuet,
            'SoKhuonMat' => $soKhuonMat,
            'DoTinCay' => $doTinCay,
            'ChiTiet' => $chiTiet,
        ]);
    }
}
