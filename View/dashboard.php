<?php
require __DIR__ . '/layout/header.php';
$h = static fn(mixed $value): string => htmlspecialchars(
    (string)($value ?? ''),
    ENT_QUOTES | ENT_SUBSTITUTE,
    'UTF-8'
);
$summary = $dashboard['summary'];
$attendance = $dashboard['attendance'];
$weekly = $dashboard['weekly'];
$environment = $dashboard['environment'];
$health = $dashboard['health'];
$donutValues = [
    'Đúng giờ' => (int)$summary['on_time'],
    'Đang làm' => (int)$summary['working'],
    'Đi trễ' => (int)$summary['late'],
    'Về sớm' => (int)$summary['early'],
    'Chưa chấm' => (int)$summary['not_checked'],
];
$donutColors = ['#16a34a', '#2563eb', '#d97706', '#dc2626', '#98a2b3'];
$donutTotal = array_sum($donutValues);
$donutStops = [];
$donutOffset = 0.0;
if ($donutTotal > 0) {
    foreach (array_values($donutValues) as $index => $value) {
        $nextOffset = $donutOffset + ($value / $donutTotal * 100);
        $donutStops[] = $donutColors[$index] . ' ' . $donutOffset . '% ' . $nextOffset . '%';
        $donutOffset = $nextOffset;
    }
} else {
    $donutStops[] = '#e5e7eb 0% 100%';
}
$donutStyle = 'conic-gradient(' . implode(', ', $donutStops) . ')';
$weeklyMax = 1;
foreach ($weekly as $day) {
    $weeklyMax = max($weeklyMax, (int)$day['check_in'], (int)$day['check_out']);
}
?>
<main class="page-container dashboard-page">
    <section class="page-heading" aria-labelledby="page-title">
        <div>
            <p class="eyebrow">Tổng quan</p>
            <h1 id="page-title">Tình hình hôm nay</h1>
            <p class="page-description">Ngày <?= $h($dashboard['date']) ?></p>
        </div>
    </section>

    <?php if ($error !== null): ?>
        <div class="notice notice--error" role="alert"><?= $h($error) ?></div>
    <?php endif; ?>

    <section class="dashboard-kpi-grid" aria-label="Chỉ số tổng quan">
        <article class="dashboard-kpi">
            <span class="dashboard-kpi-label">Tổng nhân viên</span>
            <strong class="dashboard-kpi-value"><?= (int)$summary['total_employees'] ?></strong>
            <span class="dashboard-kpi-note">trong hệ thống</span>
        </article>
        <article class="dashboard-kpi">
            <span class="dashboard-kpi-label">Đăng ký khuôn mặt</span>
            <strong class="dashboard-kpi-value"><?= (int)$summary['face_registered'] ?>/<?= (int)$summary['total_employees'] ?></strong>
            <span class="dashboard-kpi-note"><?= (int)$summary['face_missing'] ?> chưa đăng ký · <?= (int)$summary['face_embeddings'] ?> embedding đã lưu</span>
        </article>
        <article class="dashboard-kpi">
            <span class="dashboard-kpi-label">Có phân ca hôm nay</span>
            <strong class="dashboard-kpi-value"><?= (int)$summary['assigned_today'] ?></strong>
            <span class="dashboard-kpi-note">nhân viên</span>
        </article>
        <article class="dashboard-kpi">
            <span class="dashboard-kpi-label">Đã chấm công</span>
            <strong class="dashboard-kpi-value"><?= (int)$summary['checked_in'] ?></strong>
            <span class="dashboard-kpi-note">nhân viên có giờ vào</span>
        </article>
    </section>

    <section class="dashboard-status-grid" aria-label="Trạng thái chấm công">
        <div class="dashboard-status dashboard-status--green"><span>Đúng giờ</span><strong><?= (int)$summary['on_time'] ?></strong></div>
        <div class="dashboard-status dashboard-status--blue"><span>Đang làm việc</span><strong><?= (int)$summary['working'] ?></strong></div>
        <div class="dashboard-status dashboard-status--amber"><span>Đi trễ</span><strong><?= (int)$summary['late'] ?></strong></div>
        <div class="dashboard-status dashboard-status--red"><span>Về sớm</span><strong><?= (int)$summary['early'] ?></strong></div>
        <div class="dashboard-status dashboard-status--muted"><span>Chưa chấm công</span><strong><?= (int)$summary['not_checked'] ?></strong></div>
    </section>

    <section class="dashboard-panel" aria-labelledby="today-attendance-title">
        <div class="dashboard-panel-heading">
            <div>
                <h2 id="today-attendance-title">Chấm công hôm nay</h2>
                <p><?= count($attendance) ?> nhân viên · <?= (int)$summary['face_missing'] ?> chưa đăng ký khuôn mặt</p>
            </div>
        </div>
        <div class="table-scroll">
            <table class="employee-table data-table dashboard-attendance-table">
                <caption class="visually-hidden">Chấm công nhân viên ngày <?= $h($dashboard['date']) ?></caption>
                <thead>
                    <tr>
                        <th>Mã NV</th><th>Họ tên</th><th>Ca</th><th>Giờ vào</th><th>Giờ ra</th><th>Trạng thái vào</th><th>Trạng thái ra</th>
                    </tr>
                </thead>
                <tbody>
                <?php if ($attendance === []): ?>
                    <tr><td colspan="7"><div class="empty-state">Chưa có nhân viên để hiển thị.</div></td></tr>
                <?php else: ?>
                    <?php foreach ($attendance as $row): ?>
                        <?php $employeeId = (int)$row['MaNV']; ?>
                        <tr>
                            <td><span class="employee-code">NV<?= str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) ?></span></td>
                            <td><?= $h($row['HoTen']) ?></td>
                            <td>
                                <span><?= $h($row['TenCaDisplay']) ?></span>
                                <?php if ($row['ThoiGianCa'] !== '--'): ?><small class="dashboard-table-subtext"><?= $h($row['ThoiGianCa']) ?></small><?php endif; ?>
                            </td>
                            <td class="dashboard-time"><?= $h($row['GioVaoDisplay']) ?></td>
                            <td class="dashboard-time"><?= $h($row['GioRaDisplay']) ?></td>
                            <td><span class="dashboard-badge"><?= $h($row['TrangThaiVao']) ?></span></td>
                            <td><span class="dashboard-badge"><?= $h($row['TrangThaiRa']) ?></span></td>
                        </tr>
                    <?php endforeach; ?>
                <?php endif; ?>
                </tbody>
            </table>
        </div>
    </section>

    <section class="dashboard-chart-grid" aria-label="Biểu đồ chấm công">
        <article class="dashboard-panel">
            <div class="dashboard-panel-heading"><div><h2>Cơ cấu chấm công hôm nay</h2><p>Phân loại theo trạng thái hiện tại</p></div></div>
            <div class="dashboard-chart-body dashboard-donut-layout">
                <div class="dashboard-donut" role="img" aria-label="Biểu đồ tròn cơ cấu trạng thái chấm công hôm nay" style="background: <?= $h($donutStyle) ?>">
                    <span><?= $donutTotal ?></span>
                    <small>lượt trạng thái</small>
                </div>
                <ul class="dashboard-chart-legend">
                    <?php foreach ($donutValues as $label => $value): ?>
                        <?php $colorIndex = array_search($label, array_keys($donutValues), true); ?>
                        <li><span><i style="background: <?= $h($donutColors[$colorIndex]) ?>"></i><?= $h($label) ?></span><strong><?= $value ?></strong></li>
                    <?php endforeach; ?>
                </ul>
            </div>
        </article>

        <article class="dashboard-panel">
            <div class="dashboard-panel-heading"><div><h2>7 ngày gần nhất</h2><p>Số lượt vào và ra</p></div></div>
            <div class="dashboard-chart-body">
                <div class="dashboard-weekly-chart" role="img" aria-label="Biểu đồ lượt vào và ra trong 7 ngày gần nhất">
                    <?php foreach ($weekly as $day): ?>
                        <?php
                        $inHeight = max(3, (int)round((int)$day['check_in'] / $weeklyMax * 100));
                        $outHeight = max(3, (int)round((int)$day['check_out'] / $weeklyMax * 100));
                        ?>
                        <div class="dashboard-weekly-day">
                            <div class="dashboard-weekly-bars">
                                <span class="dashboard-weekly-bar dashboard-weekly-bar--in" style="height: <?= $inHeight ?>%" title="Người vào: <?= (int)$day['check_in'] ?>"></span>
                                <span class="dashboard-weekly-bar dashboard-weekly-bar--out" style="height: <?= $outHeight ?>%" title="Người ra: <?= (int)$day['check_out'] ?>"></span>
                            </div>
                            <span class="dashboard-weekly-label"><?= $h($day['label']) ?></span>
                            <small><?= $h(substr($day['date'], 5)) ?></small>
                        </div>
                    <?php endforeach; ?>
                </div>
                <div class="dashboard-weekly-legend"><span><i class="dashboard-weekly-bar--in"></i>Người vào</span><span><i class="dashboard-weekly-bar--out"></i>Người ra</span></div>
            </div>
        </article>
    </section>

    <section class="dashboard-detail-grid" aria-label="Môi trường và sức khỏe">
        <article class="dashboard-panel">
            <div class="dashboard-panel-heading"><div><h2>Môi trường gần nhất</h2><p>Thông số mới nhất được lưu trong hệ thống</p></div></div>
            <div class="dashboard-panel-body">
                <?php if ($environment === null): ?>
                    <p class="dashboard-empty">Chưa có dữ liệu.</p>
                <?php else: ?>
                    <dl class="dashboard-reading-grid">
                        <div><dt>Nhiệt độ</dt><dd><?= $environment['NhietDo'] === null ? '--' : $h($environment['NhietDo']) . ' °C' ?></dd></div>
                        <div><dt>Độ ẩm</dt><dd><?= $environment['DoAm'] === null ? '--' : $h($environment['DoAm']) . ' %' ?></dd></div>
                    </dl>
                    <p class="dashboard-timestamp">Cập nhật <?= $h($environment['ThoiGian']) ?></p>
                <?php endif; ?>
            </div>
        </article>

        <article class="dashboard-panel">
            <div class="dashboard-panel-heading"><div><h2>Sức khỏe gần nhất</h2><p><?= (int)$health['today_count'] ?> bản ghi hôm nay</p></div><a class="dashboard-section-link" href="/?action=health">Xem tất cả</a></div>
            <div class="dashboard-panel-body">
                <?php if ($health['latest'] === null): ?>
                    <p class="dashboard-empty">Chưa có dữ liệu.</p>
                <?php else: ?>
                    <p class="dashboard-health-name"><?= $h($health['latest']['HoTen'] ?? 'Không rõ nhân viên') ?></p>
                    <dl class="dashboard-reading-grid">
                        <div><dt>Nhịp tim</dt><dd><?= $health['latest']['NhipTim'] === null ? '--' : $h($health['latest']['NhipTim']) . ' bpm' ?></dd></div>
                        <div><dt>SpO₂</dt><dd><?= $health['latest']['SpO2'] === null ? '--' : $h($health['latest']['SpO2']) . ' %' ?></dd></div>
                    </dl>
                    <p class="dashboard-timestamp">Cập nhật <?= $h($health['latest']['ThoiGian']) ?></p>
                <?php endif; ?>
            </div>
        </article>
    </section>

    <section class="dashboard-panel dashboard-alert-panel" aria-labelledby="recent-alerts-title">
        <div class="dashboard-panel-heading"><div><h2 id="recent-alerts-title">Cảnh báo gần đây</h2><p><?= count($dashboard['alerts']) ?> bản ghi mới nhất</p></div><a class="dashboard-section-link" href="/?action=alerts">Xem tất cả</a></div>
        <?php if ($dashboard['alerts'] === []): ?>
            <p class="dashboard-empty dashboard-alert-empty">Chưa có cảnh báo.</p>
        <?php else: ?>
            <ul class="dashboard-alert-list">
                <?php foreach ($dashboard['alerts'] as $alert): ?>
                    <li>
                        <div class="dashboard-alert-main">
                            <strong><?= $h($alert['HoTen'] ?? 'Không rõ nhân viên') ?></strong>
                            <span><?= $h($alert['LoaiCanhBao'] ?? 'Cảnh báo') ?></span>
                            <?php if (($alert['NoiDung'] ?? '') !== ''): ?><p><?= $h($alert['NoiDung']) ?></p><?php endif; ?>
                        </div>
                        <time><?= $h($alert['ThoiGian']) ?></time>
                    </li>
                <?php endforeach; ?>
            </ul>
        <?php endif; ?>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>
