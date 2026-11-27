<?php
require __DIR__ . '/layout/header.php';
$h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$baseQuery = [
    'action' => 'monitoring',
    'from_date' => $filters['from_date'],
    'to_date' => $filters['to_date'],
    'employee_id' => $filters['employee_id'] ?? '',
    'keyword' => $filters['keyword'],
    'per_page' => $pageSize,
];
$healthPageUrl = static function (int $targetPage) use ($baseQuery): string {
    return '/?' . http_build_query($baseQuery + ['health_page' => $targetPage]);
};
$chartJson = json_encode($chartData, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT);
?>
<main class="page-container">
    <section class="workspace" aria-label="Lịch sử sức khỏe nhân viên">
        <div class="attendance-page-heading">
            <div>
                <p class="eyebrow">THEO DÕI SỨC KHỎE</p>
                <h1 id="health-page-title">Sức khỏe</h1>
                <p>Lịch sử nhịp tim và SpO₂ từ cảm biến.</p>
            </div>
        </div>
        <?php if ($error !== null): ?><div class="notice notice--error" role="alert"><?= $h($error) ?></div><?php endif; ?>
        <form class="workspace-filters" method="get" action="/">
            <input type="hidden" name="action" value="monitoring">
            <div class="filter-grid monitoring-filter-grid">
                <div class="form-field"><label for="monitoring-from">Từ ngày</label><input id="monitoring-from" type="date" name="from_date" value="<?= $h($filters['from_date']) ?>"><?php if (isset($errors['from_date'])): ?><p class="field-error"><?= $h($errors['from_date']) ?></p><?php endif; ?></div>
                <div class="form-field"><label for="monitoring-to">Đến ngày</label><input id="monitoring-to" type="date" name="to_date" value="<?= $h($filters['to_date']) ?>"><?php if (isset($errors['to_date'])): ?><p class="field-error"><?= $h($errors['to_date']) ?></p><?php endif; ?></div>
                <div class="form-field">
                    <label for="monitoring-employee">Nhân viên</label>
                    <select id="monitoring-employee" name="employee_id">
                        <option value="">Tất cả nhân viên</option>
                        <?php foreach ($employees as $employee): $id = (int)$employee['MaNV']; ?>
                            <option value="<?= $id ?>" <?= (int)($filters['employee_id'] ?? 0) === $id ? 'selected' : '' ?>>NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?> · <?= $h($employee['HoTen']) ?></option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['employee_id'])): ?><p class="field-error"><?= $h($errors['employee_id']) ?></p><?php endif; ?>
                </div>
                <div class="form-field"><label for="monitoring-keyword">Mã hoặc họ tên</label><input id="monitoring-keyword" type="search" name="keyword" maxlength="100" value="<?= $h($filters['keyword']) ?>" placeholder="Tìm mã hoặc họ tên"><?php if (isset($errors['keyword'])): ?><p class="field-error"><?= $h($errors['keyword']) ?></p><?php endif; ?></div>
            </div>
            <?php if (isset($errors['date_range'])): ?><p class="field-error" role="alert"><?= $h($errors['date_range']) ?></p><?php endif; ?>
            <div class="workspace-filter-actions">
                <label for="monitoring-page-size">Số dòng<select id="monitoring-page-size" name="per_page"><?php foreach ([5, 10, 20, 50] as $size): ?><option value="<?= $size ?>" <?= $size === $pageSize ? 'selected' : '' ?>><?= $size ?></option><?php endforeach; ?></select></label>
                <button class="button button--primary button--small" type="submit">Lọc</button>
                <a class="text-action" href="/?action=monitoring">Xóa lọc</a>
            </div>
        </form>

        <?php if ($chartData === []): ?><div class="empty-state workspace-empty">Chưa có dữ liệu sức khỏe.</div><?php else: ?>
            <div class="health-chart-wrap"><svg id="health-chart" class="health-chart" viewBox="0 0 800 220" role="img" aria-label="Biểu đồ nhịp tim theo thời gian"></svg></div>
            <script type="application/json" id="health-chart-data"><?= $chartJson ?: '[]' ?></script>
        <?php endif; ?>
        <?php if ($healthRows === []): ?><div class="empty-state workspace-empty">Không có dữ liệu sức khỏe phù hợp.</div><?php else: ?>
            <div class="table-scroll"><table class="employee-table data-table">
                <caption class="visually-hidden">Lịch sử sức khỏe</caption>
                <thead><tr><th>Mã NV</th><th>Họ tên</th><th>Nhịp tim</th><th>SpO₂</th><th>Thời gian</th></tr></thead>
                <tbody><?php foreach ($healthRows as $record): $employeeId = (int)$record['MaNV']; ?>
                    <tr><td><span class="employee-code">NV<?= str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) ?></span></td><td><?= $h($record['HoTen']) ?></td><td><?= $record['NhipTim'] === null ? '--' : $h($record['NhipTim']) . ' bpm' ?></td><td><?= $record['SpO2'] === null ? '--' : $h($record['SpO2']) . ' %' ?></td><td><?= $record['ThoiGian'] === null ? '--' : $h((new DateTimeImmutable((string)$record['ThoiGian']))->format('Y-m-d H:i:s')) ?></td></tr>
                <?php endforeach; ?></tbody>
            </table></div>
            <?php if ($totalHealthPages > 1): ?><nav class="attendance-pagination" aria-label="Phân trang sức khỏe"><?php if ($healthPage > 1): ?><a class="text-action" href="<?= $h($healthPageUrl($healthPage - 1)) ?>">‹ Trước</a><?php endif; ?><span><?= (int)$healthPage ?> / <?= (int)$totalHealthPages ?></span><?php if ($healthPage < $totalHealthPages): ?><a class="text-action" href="<?= $h($healthPageUrl($healthPage + 1)) ?>">Sau ›</a><?php endif; ?></nav><?php endif; ?>
        <?php endif; ?>
    </section>
</main>
<script src="/public/js/health.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>
