<?php
require __DIR__ . '/layout/header.php';
$h = static fn(mixed $value): string => htmlspecialchars(
    (string)($value ?? ''),
    ENT_QUOTES | ENT_SUBSTITUTE,
    'UTF-8'
);
$paginationQuery = [
    'action' => 'health',
    'from_date' => $filters['from_date'],
    'to_date' => $filters['to_date'],
    'employee_id' => $filters['employee_id'] ?? '',
    'keyword' => $filters['keyword'],
    'per_page' => $pageSize,
];
$pageUrl = static fn(int $targetPage): string => '/?' . http_build_query($paginationQuery + ['page' => $targetPage]);
$chartJson = json_encode($chartData, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT);
?>
<main class="page-container">
    <section class="page-heading" aria-labelledby="page-title">
        <div>
            <p class="eyebrow">Theo dõi</p>
            <h1 id="page-title">Sức khỏe nhân viên</h1>
            <p class="page-description">Lịch sử nhịp tim và SpO₂ từ dữ liệu cảm biến đã lưu.</p>
        </div>
    </section>

    <?php if ($error !== null): ?><div class="notice notice--error" role="alert"><?= $h($error) ?></div><?php endif; ?>

    <section class="dashboard-panel health-chart-panel" aria-labelledby="health-chart-title">
        <div class="dashboard-panel-heading">
            <div><h2 id="health-chart-title">Nhịp tim gần nhất</h2><p>Tối đa 20 bản ghi, hiển thị theo thứ tự thời gian</p></div>
        </div>
        <?php if ($chartData === []): ?>
            <p class="empty-state">Chưa có dữ liệu sức khỏe.</p>
        <?php else: ?>
            <div class="health-chart-wrap">
                <svg id="health-chart" class="health-chart" viewBox="0 0 800 220" role="img" aria-label="Biểu đồ nhịp tim theo thời gian"></svg>
            </div>
            <script type="application/json" id="health-chart-data"><?= $chartJson ?: '[]' ?></script>
        <?php endif; ?>
    </section>

    <section class="form-panel filter-panel" aria-label="Bộ lọc sức khỏe">
        <form class="employee-form" method="get" action="/">
            <input type="hidden" name="action" value="health">
            <div class="filter-grid attendance-filter-grid">
                <div class="form-field">
                    <label for="health-from">Từ ngày</label>
                    <input id="health-from" type="date" name="from_date" value="<?= $h($filters['from_date']) ?>">
                    <?php if (isset($errors['from_date'])): ?><p class="field-error"><?= $h($errors['from_date']) ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="health-to">Đến ngày</label>
                    <input id="health-to" type="date" name="to_date" value="<?= $h($filters['to_date']) ?>">
                    <?php if (isset($errors['to_date'])): ?><p class="field-error"><?= $h($errors['to_date']) ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="health-employee">Nhân viên</label>
                    <select id="health-employee" name="employee_id">
                        <option value="">Tất cả nhân viên</option>
                        <?php foreach ($employees as $employee): ?>
                            <?php $id = (int)$employee['MaNV']; ?>
                            <option value="<?= $id ?>" <?= (int)($filters['employee_id'] ?? 0) === $id ? 'selected' : '' ?>>
                                NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?> · <?= $h($employee['HoTen']) ?>
                            </option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['employee_id'])): ?><p class="field-error"><?= $h($errors['employee_id']) ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="health-keyword">Mã hoặc họ tên</label>
                    <input id="health-keyword" type="search" name="keyword" maxlength="100" value="<?= $h($filters['keyword']) ?>" placeholder="Tìm MaNV hoặc HoTen">
                    <?php if (isset($errors['keyword'])): ?><p class="field-error"><?= $h($errors['keyword']) ?></p><?php endif; ?>
                </div>
            </div>
            <?php if (isset($errors['date_range'])): ?><p class="field-error" role="alert"><?= $h($errors['date_range']) ?></p><?php endif; ?>
            <div class="form-actions filter-actions">
                <button class="button button--primary" type="submit">Lọc dữ liệu</button>
                <a class="button button--secondary" href="/?action=health">Xóa bộ lọc</a>
                <label class="inline-filter" for="health-page-size"><span>Số dòng</span>
                    <select id="health-page-size" name="per_page">
                        <?php foreach ([5, 10, 20, 50] as $size): ?><option value="<?= $size ?>" <?= $size === $pageSize ? 'selected' : '' ?>><?= $size ?></option><?php endforeach; ?>
                    </select>
                </label>
            </div>
        </form>
    </section>

    <section class="employee-section" aria-labelledby="health-history-title">
        <div class="section-heading">
            <div>
                <h2 id="health-history-title">Lịch sử sức khỏe</h2>
                <p class="section-description"><?= (int)$totalRows ?> kết quả · Trang <?= (int)$page ?>/<?= (int)$totalPages ?></p>
            </div>
        </div>
        <?php if ($records === []): ?>
            <div class="empty-state">Không có dữ liệu sức khỏe phù hợp.</div>
        <?php else: ?>
            <div class="table-scroll">
                <table class="employee-table data-table">
                    <caption class="visually-hidden">Lịch sử chỉ số sức khỏe từ cảm biến</caption>
                    <thead><tr><th>Mã nhân viên</th><th>Họ tên</th><th>Nhịp tim</th><th>SpO₂</th><th>Thời gian</th></tr></thead>
                    <tbody>
                    <?php foreach ($records as $record): $employeeId = (int)$record['MaNV']; ?>
                        <tr>
                            <td><span class="employee-code">NV<?= str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) ?></span></td>
                            <td><?= $h($record['HoTen']) ?></td>
                            <td><?= $record['NhipTim'] === null ? '--' : $h($record['NhipTim']) . ' bpm' ?></td>
                            <td><?= $record['SpO2'] === null ? '--' : $h($record['SpO2']) . ' %' ?></td>
                            <td><?= $record['ThoiGian'] === null ? '--' : $h((new DateTimeImmutable((string)$record['ThoiGian']))->format('Y-m-d H:i:s')) ?></td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
            <?php if ($totalPages > 1): ?>
                <nav class="attendance-pagination" aria-label="Phân trang lịch sử sức khỏe">
                    <?php if ($page > 1): ?><a class="button button--secondary button--small" href="<?= $h($pageUrl($page - 1)) ?>">Trang trước</a><?php else: ?><span class="button button--secondary button--small is-disabled" aria-disabled="true">Trang trước</span><?php endif; ?>
                    <span>Trang <?= (int)$page ?> / <?= (int)$totalPages ?></span>
                    <?php if ($page < $totalPages): ?><a class="button button--secondary button--small" href="<?= $h($pageUrl($page + 1)) ?>">Trang sau</a><?php else: ?><span class="button button--secondary button--small is-disabled" aria-disabled="true">Trang sau</span><?php endif; ?>
                </nav>
            <?php endif; ?>
        <?php endif; ?>
    </section>
</main>
<script src="/public/js/health.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>
