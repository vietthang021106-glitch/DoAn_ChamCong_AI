<?php require __DIR__ . '/layout/header.php'; ?>
<?php
$h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$profile = $profile ?? [];
$historyQuery = ['action' => 'my', 'from_date' => $fromDate, 'to_date' => $toDate];
$pageUrl = static fn(int $targetPage): string => '/?' . http_build_query($historyQuery + ['page' => $targetPage]);
$checkIn = $today['attendance']['GioVao'] ?? null;
$checkOut = $today['attendance']['GioRa'] ?? null;
?>
<main class="page-container my-page">
    <section class="page-heading" aria-labelledby="my-title">
        <div>
            <p class="eyebrow">Nhân viên</p>
            <h1 id="my-title">Trang của tôi</h1>
            <p class="page-description">Thông tin cá nhân và hoạt động của bạn.</p>
        </div>
    </section>

    <?php if ($error !== null): ?>
        <div class="notice notice--error" role="alert"><?= $h($error) ?></div>
    <?php endif; ?>

    <section class="my-summary-grid" aria-label="Hồ sơ và chấm công hôm nay">
        <article class="dashboard-panel my-profile-panel">
            <div class="dashboard-panel-heading"><div><h2>Hồ sơ</h2><p>Thông tin nhân viên</p></div></div>
            <dl class="my-profile-list">
                <div><dt>Mã nhân viên</dt><dd>NV<?= str_pad((string)($profile['MaNV'] ?? ''), 3, '0', STR_PAD_LEFT) ?></dd></div>
                <div><dt>Họ tên</dt><dd><?= $h($profile['HoTen'] ?? '') ?></dd></div>
                <div><dt>Vai trò</dt><dd><?= $h($profile['TenVaiTro'] ?? '') ?></dd></div>
            </dl>
        </article>

        <article class="dashboard-panel">
            <div class="dashboard-panel-heading"><div><h2>Chấm công hôm nay</h2><p><?= $h($todayDate) ?></p></div></div>
            <div class="my-today-grid">
                <div><span>Ca làm việc</span><strong><?= $h($today['shift']['TenCa'] ?? 'Chưa được phân ca hôm nay') ?></strong>
                    <?php if ($today['shift'] !== null): ?><small><?= $h(substr((string)$today['shift']['GioBatDau'], 0, 5)) ?> – <?= $h(substr((string)$today['shift']['GioKetThuc'], 0, 5)) ?></small><?php endif; ?>
                </div>
                <div><span>Giờ vào</span><strong><?= $checkIn ? $h((new DateTimeImmutable((string)$checkIn))->format('H:i:s')) : '--' ?></strong><small><?= $h($today['statuses']['entry']) ?></small></div>
                <div><span>Giờ ra</span><strong><?= $checkOut ? $h((new DateTimeImmutable((string)$checkOut))->format('H:i:s')) : '--' ?></strong><small><?= $h($today['statuses']['exit']) ?></small></div>
                <div><span>Trạng thái</span><strong><?= $h($today['summary']) ?></strong><small><?= $today['shift'] === null && $today['attendance'] === null ? 'Chưa được phân ca hôm nay' : 'Theo ca đã phân' ?></small></div>
            </div>
            <?php if ($today['attendance'] !== null): ?>
                <div class="my-today-evidence">
                    <?php if ((int)$today['attendance']['HasImageIn'] === 1): ?><a href="/?action=my_attendance_image_in&amp;id=<?= (int)$today['attendance']['MaCC'] ?>" target="_blank" rel="noopener">Ảnh vào</a><?php endif; ?>
                    <?php if ((int)$today['attendance']['HasImageOut'] === 1): ?><a href="/?action=my_attendance_image_out&amp;id=<?= (int)$today['attendance']['MaCC'] ?>" target="_blank" rel="noopener">Ảnh ra</a><?php endif; ?>
                </div>
            <?php endif; ?>
        </article>
    </section>

    <section class="dashboard-panel my-section" aria-labelledby="my-attendance-title">
        <div class="dashboard-panel-heading"><div><h2 id="my-attendance-title">Lịch sử chấm công</h2><p><?= (int)$totalRows ?> bản ghi · Trang <?= (int)$page ?>/<?= (int)$totalPages ?></p></div></div>
        <form class="my-date-filter" method="get" action="/">
            <input type="hidden" name="action" value="my">
            <label>Từ ngày<input type="date" name="from_date" value="<?= $h($fromDate) ?>"></label>
            <label>Đến ngày<input type="date" name="to_date" value="<?= $h($toDate) ?>"></label>
            <button class="button button--primary button--small" type="submit">Lọc</button>
            <a class="button button--secondary button--small" href="/?action=my">Xóa lọc</a>
        </form>
        <?php if ($errors !== []): ?>
            <div class="my-validation-errors" role="alert">
                <?php foreach ($errors as $message): ?><p><?= $h($message) ?></p><?php endforeach; ?>
            </div>
        <?php endif; ?>
        <div class="table-scroll">
            <table class="employee-table data-table my-history-table">
                <thead><tr><th>Ngày</th><th>Ca</th><th>Giờ vào</th><th>Giờ ra</th><th>Trạng thái vào</th><th>Trạng thái ra</th><th>Ảnh</th></tr></thead>
                <tbody>
                <?php if ($attendanceRows === []): ?>
                    <tr><td colspan="7"><div class="empty-state">Chưa có lịch sử chấm công phù hợp.</div></td></tr>
                <?php else: foreach ($attendanceRows as $row): ?>
                    <tr>
                        <td><?= $row['GioVao'] ? $h((new DateTimeImmutable((string)$row['GioVao']))->format('Y-m-d')) : '--' ?></td>
                        <td><?= $h($row['TenCa'] ?? '--') ?></td>
                        <td><?= $row['GioVao'] ? $h((new DateTimeImmutable((string)$row['GioVao']))->format('H:i:s')) : '--' ?></td>
                        <td><?= $row['GioRa'] ? $h((new DateTimeImmutable((string)$row['GioRa']))->format('H:i:s')) : '--' ?></td>
                        <td><?= $h($row['Statuses']['entry']) ?></td>
                        <td><?= $h($row['Statuses']['exit']) ?></td>
                        <td class="evidence-cell">
                            <?php if ((int)$row['HasImageIn'] === 1): ?><a href="/?action=my_attendance_image_in&amp;id=<?= (int)$row['MaCC'] ?>" target="_blank" rel="noopener">Ảnh vào</a><?php endif; ?>
                            <?php if ((int)$row['HasImageOut'] === 1): ?><a href="/?action=my_attendance_image_out&amp;id=<?= (int)$row['MaCC'] ?>" target="_blank" rel="noopener">Ảnh ra</a><?php endif; ?>
                            <?php if ((int)$row['HasImageIn'] !== 1 && (int)$row['HasImageOut'] !== 1): ?>--<?php endif; ?>
                        </td>
                    </tr>
                <?php endforeach; endif; ?>
                </tbody>
            </table>
        </div>
        <?php if ($totalPages > 1): ?>
            <nav class="attendance-pagination" aria-label="Phân trang lịch sử cá nhân">
                <?php if ($page > 1): ?><a class="button button--secondary button--small" href="<?= $h($pageUrl($page - 1)) ?>">Trang trước</a><?php endif; ?>
                <span>Trang <?= (int)$page ?> / <?= (int)$totalPages ?></span>
                <?php if ($page < $totalPages): ?><a class="button button--secondary button--small" href="<?= $h($pageUrl($page + 1)) ?>">Trang sau</a><?php endif; ?>
            </nav>
        <?php endif; ?>
    </section>

    <section class="my-lower-grid" aria-label="Sức khỏe và cảnh báo">
        <article class="dashboard-panel">
            <div class="dashboard-panel-heading"><div><h2>Sức khỏe của tôi</h2><p><?= count($healthRows) ?> bản ghi gần nhất</p></div></div>
            <div class="table-scroll"><table class="employee-table data-table">
                <thead><tr><th>Nhịp tim</th><th>SpO₂</th><th>Thời gian</th></tr></thead>
                <tbody><?php if ($healthRows === []): ?><tr><td colspan="3"><div class="empty-state">Chưa có dữ liệu sức khỏe.</div></td></tr><?php else: foreach ($healthRows as $row): ?>
                    <tr><td><?= $row['NhipTim'] === null ? '--' : $h($row['NhipTim']) . ' bpm' ?></td><td><?= $row['SpO2'] === null ? '--' : $h($row['SpO2']) . '%' ?></td><td><?= $h($row['ThoiGian']) ?></td></tr>
                <?php endforeach; endif; ?></tbody>
            </table></div>
        </article>
        <article class="dashboard-panel">
            <div class="dashboard-panel-heading"><div><h2>Cảnh báo của tôi</h2><p><?= count($alertRows) ?> cảnh báo gần nhất</p></div></div>
            <div class="table-scroll"><table class="employee-table data-table">
                <thead><tr><th>Loại</th><th>Nội dung</th><th>Thời gian</th></tr></thead>
                <tbody><?php if ($alertRows === []): ?><tr><td colspan="3"><div class="empty-state">Không có cảnh báo.</div></td></tr><?php else: foreach ($alertRows as $row): ?>
                    <tr><td><?= $h($row['LoaiCanhBao'] ?: 'Cảnh báo AI') ?></td><td><?= $h($row['NoiDung'] ?? '') ?></td><td><?= $h($row['ThoiGian'] ?? '--') ?></td></tr>
                <?php endforeach; endif; ?></tbody>
            </table></div>
        </article>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>
