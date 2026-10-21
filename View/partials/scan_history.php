<?php
$scanPaginationQuery = [
    'action' => 'attendance',
    'tab' => 'scan_history',
    'date' => $date,
    'employee_id' => $employeeId ?? '',
    'device_id' => $deviceId ?? '',
    'reason' => $reason,
    'limit' => $limit,
];
$scanPageUrl = static fn(int $targetPage): string => '/?' . http_build_query($scanPaginationQuery + ['page' => $targetPage]);
$h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
?>
<form class="workspace-filters attendance-workspace-filters" method="get" action="/">
    <input type="hidden" name="action" value="attendance">
    <input type="hidden" name="tab" value="scan_history">
    <div class="filter-grid attendance-filter-grid">
        <div class="form-field">
            <label for="scan-date">Ngày</label>
            <input id="scan-date" type="date" name="date" value="<?= $h($date) ?>">
            <?php if (isset($errors['date'])): ?><p class="field-error"><?= $h($errors['date']) ?></p><?php endif; ?>
        </div>
        <div class="form-field">
            <label for="scan-employee">Nhân viên</label>
            <select id="scan-employee" name="employee_id">
                <option value="">Tất cả nhân viên</option>
                <?php foreach ($employees as $employee): ?>
                    <?php $optionId = (int)$employee['MaNV']; ?>
                    <option value="<?= $optionId ?>" <?= $employeeId === $optionId ? 'selected' : '' ?>>
                        NV<?= str_pad((string)$optionId, 3, '0', STR_PAD_LEFT) ?> · <?= $h($employee['HoTen'] ?? '') ?>
                    </option>
                <?php endforeach; ?>
            </select>
            <?php if (isset($errors['employee_id'])): ?><p class="field-error"><?= $h($errors['employee_id']) ?></p><?php endif; ?>
        </div>
        <div class="form-field">
            <label for="scan-reason">Lý do</label>
            <select id="scan-reason" name="reason">
                <option value="">Tất cả lý do</option>
                <?php foreach ($reasonLabels as $code => $label): ?>
                    <option value="<?= $h($code) ?>" <?= $reason === $code ? 'selected' : '' ?>><?= $h($label) ?></option>
                <?php endforeach; ?>
            </select>
            <?php if (isset($errors['reason'])): ?><p class="field-error"><?= $h($errors['reason']) ?></p><?php endif; ?>
        </div>
        <div class="form-field">
            <label for="scan-device">Thiết bị</label>
            <select id="scan-device" name="device_id">
                <option value="">Tất cả thiết bị</option>
                <?php foreach ($devices as $device): ?>
                    <?php $optionId = (int)$device['MaTB']; ?>
                    <option value="<?= $optionId ?>" <?= $deviceId === $optionId ? 'selected' : '' ?>>
                        TB<?= str_pad((string)$optionId, 3, '0', STR_PAD_LEFT) ?><?= !empty($device['LoaiTB']) ? ' · ' . $h($device['LoaiTB']) : '' ?>
                    </option>
                <?php endforeach; ?>
            </select>
            <?php if (isset($errors['device_id'])): ?><p class="field-error"><?= $h($errors['device_id']) ?></p><?php endif; ?>
        </div>
        <div class="form-field">
            <label for="scan-limit">Số dòng</label>
            <select id="scan-limit" name="limit"><?php foreach ([10, 20, 50, 100] as $size): ?><option value="<?= $size ?>" <?= $limit === $size ? 'selected' : '' ?>><?= $size ?></option><?php endforeach; ?></select>
            <?php if (isset($errors['limit'])): ?><p class="field-error"><?= $h($errors['limit']) ?></p><?php endif; ?>
        </div>
    </div>
    <?php if (isset($errors['page'])): ?><p class="field-error" role="alert"><?= $h($errors['page']) ?></p><?php endif; ?>
    <div class="workspace-filter-actions">
        <button class="button button--primary button--small" type="submit">Lọc</button>
        <a class="text-action" href="/?action=attendance&amp;tab=scan_history">Xóa bộ lọc</a>
    </div>
</form>

<?php if ($error !== null): ?>
    <div class="notice notice--error" role="alert"><?= $h($error) ?></div>
<?php endif; ?>

<div class="workspace-table">
    <?php if ($errors === [] && $error === null && $scanRows === []): ?>
        <div class="empty-state">Chưa có lần quét thất bại.</div>
    <?php elseif ($scanRows !== []): ?>
        <div class="table-scroll">
            <table class="employee-table data-table scan-history-table">
                <caption class="visually-hidden">Các lần quét không tạo hoặc cập nhật chấm công</caption>
                <thead><tr><th>Thời gian</th><th>Nhân viên</th><th>Thiết bị</th><th>Ca</th><th>Lý do</th><th>Ảnh</th></tr></thead>
                <tbody>
                <?php foreach ($scanRows as $row): ?>
                    <?php
                    $scanId = (int)$row['MaLanQuet'];
                    $hasEmployee = $row['MaNV'] !== null;
                    $personName = (string)($row['HoTen'] ?? '');
                    $employeeCode = $hasEmployee ? 'NV' . str_pad((string)(int)$row['MaNV'], 3, '0', STR_PAD_LEFT) : '—';
                    $evidencePerson = $hasEmployee ? $personName : '—';
                    $evidenceCode = $employeeCode;
                    $evidenceAttendanceId = $scanId;
                    $evidenceAction = '/?action=scan_history_image';
                    $evidenceKind = 'Ảnh quét';
                    $evidenceTitle = 'Ảnh quét';
                    $evidenceTime = (new DateTimeImmutable((string)$row['ThoiGianQuet']))->format('d/m/Y H:i:s');
                    $reasonLabel = (string)$row['TenLyDo'];
                    $detailParts = ['Lý do: ' . $reasonLabel];
                    if ($row['SoKhuonMat'] !== null) {
                        $detailParts[] = 'Số khuôn mặt: ' . (int)$row['SoKhuonMat'];
                    }
                    if ($row['DoTinCay'] !== null) {
                        $detailParts[] = 'Độ tin cậy: ' . number_format((float)$row['DoTinCay'], 4, '.', '');
                    }
                    if (!empty($row['ChiTiet'])) {
                        $detailParts[] = (string)$row['ChiTiet'];
                    }
                    $evidenceDetail = implode(' · ', $detailParts);
                    ?>
                    <tr>
                        <td><?= $h((new DateTimeImmutable((string)$row['ThoiGianQuet']))->format('d/m/Y H:i:s')) ?></td>
                        <td>
                            <?php if ($hasEmployee): ?>
                                <span class="employee-code"><?= $h($employeeCode) ?></span> · <?= $h($personName) ?>
                            <?php else: ?>—<?php endif; ?>
                        </td>
                        <td><?= $row['MaTB'] === null ? '—' : $h('TB' . str_pad((string)(int)$row['MaTB'], 3, '0', STR_PAD_LEFT) . (!empty($row['LoaiTB']) ? ' · ' . $row['LoaiTB'] : '')) ?></td>
                        <td><?= $row['MaCa'] === null ? '—' : $h((string)($row['TenCa'] ?: 'Ca ' . (int)$row['MaCa'])) ?></td>
                        <td><?= $h($reasonLabel) ?></td>
                        <td class="evidence-cell">
                            <?php if ((int)$row['HasImage'] === 1): ?>
                                <?php require __DIR__ . '/evidence_thumbnail.php'; ?>
                            <?php else: ?>
                                <span class="evidence-empty">--</span>
                            <?php endif; ?>
                        </td>
                    </tr>
                <?php endforeach; ?>
                </tbody>
            </table>
        </div>
        <?php if ($totalPages > 1): ?>
            <nav class="attendance-pagination" aria-label="Phân trang lịch sử quét">
                <?php if ($page > 1): ?><a class="button button--secondary button--small" href="<?= $h($scanPageUrl($page - 1)) ?>">‹ Trước</a><?php else: ?><span class="button button--secondary button--small is-disabled" aria-disabled="true">‹ Trước</span><?php endif; ?>
                <span><?= (int)$page ?> / <?= (int)$totalPages ?></span>
                <?php if ($page < $totalPages): ?><a class="button button--secondary button--small" href="<?= $h($scanPageUrl($page + 1)) ?>">Sau ›</a><?php else: ?><span class="button button--secondary button--small is-disabled" aria-disabled="true">Sau ›</span><?php endif; ?>
            </nav>
        <?php endif; ?>
    <?php endif; ?>
</div>
