<?php
require __DIR__ . '/layout/header.php';
$h = static fn(mixed $value): string => htmlspecialchars(
    (string)($value ?? ''),
    ENT_QUOTES | ENT_SUBSTITUTE,
    'UTF-8'
);
$paginationQuery = [
    'action' => 'alerts',
    'from_date' => $filters['from_date'],
    'to_date' => $filters['to_date'],
    'employee_id' => $filters['employee_id'] ?? '',
    'category' => $filters['category'],
    'per_page' => $pageSize,
];
$pageUrl = static fn(int $targetPage): string => '/?' . http_build_query($paginationQuery + ['page' => $targetPage]);
?>
<main class="page-container">
    <section class="page-heading" aria-labelledby="page-title">
        <div>
            <p class="eyebrow">Theo dõi</p>
            <h1 id="page-title">Cảnh báo</h1>
            <p class="page-description">Lịch sử cảnh báo và dữ liệu trạng thái liên quan đã lưu.</p>
        </div>
    </section>

    <?php if ($error !== null): ?><div class="notice notice--error" role="alert"><?= $h($error) ?></div><?php endif; ?>

    <section class="form-panel filter-panel" aria-label="Bộ lọc cảnh báo">
        <form class="employee-form" method="get" action="/">
            <input type="hidden" name="action" value="alerts">
            <input type="hidden" name="per_page" value="<?= (int)$pageSize ?>">
            <div class="filter-grid attendance-filter-grid">
                <div class="form-field">
                    <label for="alerts-from">Từ ngày</label>
                    <input id="alerts-from" type="date" name="from_date" value="<?= $h($filters['from_date']) ?>">
                    <?php if (isset($errors['from_date'])): ?><p class="field-error"><?= $h($errors['from_date']) ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="alerts-to">Đến ngày</label>
                    <input id="alerts-to" type="date" name="to_date" value="<?= $h($filters['to_date']) ?>">
                    <?php if (isset($errors['to_date'])): ?><p class="field-error"><?= $h($errors['to_date']) ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="alerts-employee">Nhân viên</label>
                    <select id="alerts-employee" name="employee_id">
                        <option value="">Tất cả nhân viên</option>
                        <?php foreach ($employees as $employee): ?>
                            <?php $id = (int)$employee['MaNV']; ?>
                            <option value="<?= $id ?>" <?= (int)($filters['employee_id'] ?? 0) === $id ? 'selected' : '' ?>>NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?> · <?= $h($employee['HoTen']) ?></option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['employee_id'])): ?><p class="field-error"><?= $h($errors['employee_id']) ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="alerts-category">Loại cảnh báo / biểu hiện</label>
                    <select id="alerts-category" name="category">
                        <option value="">Tất cả loại</option>
                        <?php foreach ($categories as $item): $category = (string)$item['LoaiCanhBao']; ?>
                            <option value="<?= $h($category) ?>" <?= $filters['category'] === $category ? 'selected' : '' ?>><?= $h($category) ?></option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['category'])): ?><p class="field-error"><?= $h($errors['category']) ?></p><?php endif; ?>
                </div>
            </div>
            <?php if (isset($errors['date_range'])): ?><p class="field-error" role="alert"><?= $h($errors['date_range']) ?></p><?php endif; ?>
            <div class="form-actions filter-actions">
                <button class="button button--primary" type="submit">Lọc dữ liệu</button>
                <a class="button button--secondary" href="/?action=alerts">Xóa bộ lọc</a>
            </div>
        </form>
    </section>

    <section class="employee-section" aria-labelledby="alerts-list-title">
        <div class="section-heading">
            <div>
                <h2 id="alerts-list-title">Lịch sử cảnh báo</h2>
                <p class="section-description"><?= (int)$totalRows ?> kết quả · Trang <?= (int)$page ?>/<?= (int)$totalPages ?></p>
            </div>
        </div>
        <?php if ($records === []): ?>
            <div class="empty-state">Không có cảnh báo phù hợp.</div>
        <?php else: ?>
            <div class="table-scroll">
                <table class="employee-table data-table">
                    <caption class="visually-hidden">Lịch sử cảnh báo</caption>
                    <thead><tr><th>Thời gian</th><th>Mã nhân viên</th><th>Nhân viên</th><th>Loại / biểu hiện</th><th>Nội dung</th><th>Dữ liệu liên quan</th></tr></thead>
                    <tbody>
                    <?php foreach ($records as $record): $employeeId = (int)$record['MaNV']; ?>
                        <tr>
                            <td><?= $record['ThoiGian'] === null ? '--' : $h((new DateTimeImmutable((string)$record['ThoiGian']))->format('Y-m-d H:i:s')) ?></td>
                            <td><span class="employee-code">NV<?= str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) ?></span></td>
                            <td><?= $h($record['HoTen']) ?></td>
                            <td><?= $h($record['LoaiCanhBao'] ?: 'Cảnh báo AI') ?></td>
                            <td><?= $h($record['NoiDung'] ?: '--') ?></td>
                            <td class="related-data">
                                <?php $related = []; if ($record['MaTT'] !== null) $related[] = 'MaTT ' . (int)$record['MaTT']; if ($record['MaTB'] !== null) $related[] = 'MaTB ' . (int)$record['MaTB']; ?>
                                <?= $related === [] ? '--' : $h(implode(' · ', $related)) ?>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
            <?php if ($totalPages > 1): ?>
                <nav class="attendance-pagination" aria-label="Phân trang cảnh báo">
                    <?php if ($page > 1): ?><a class="button button--secondary button--small" href="<?= $h($pageUrl($page - 1)) ?>">Trang trước</a><?php else: ?><span class="button button--secondary button--small is-disabled" aria-disabled="true">Trang trước</span><?php endif; ?>
                    <span>Trang <?= (int)$page ?> / <?= (int)$totalPages ?></span>
                    <?php if ($page < $totalPages): ?><a class="button button--secondary button--small" href="<?= $h($pageUrl($page + 1)) ?>">Trang sau</a><?php else: ?><span class="button button--secondary button--small is-disabled" aria-disabled="true">Trang sau</span><?php endif; ?>
                </nav>
            <?php endif; ?>
        <?php endif; ?>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>
