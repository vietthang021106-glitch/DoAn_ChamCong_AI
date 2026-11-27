<?php require __DIR__ . '/layout/header.php'; ?>
<?php if ($activeTab === 'attendance'): ?>
<?php
$paginationQuery = [
    'action' => 'attendance',
    'from_date' => $fromDate,
    'to_date' => $toDate,
    'employee_id' => $employeeId ?? '',
    'keyword' => $keyword,
    'status' => $status,
    'limit' => $limit,
];
$pageUrl = static fn(int $targetPage): string => '/?' . http_build_query($paginationQuery + ['page' => $targetPage]);
?>
<?php endif; ?>
<main class="page-container">
    <section class="workspace attendance-workspace" aria-label="Tra cứu chấm công">
        <?php if ($activeTab === 'scan_history'): ?>
            <div class="attendance-page-heading">
                <div>
                    <p class="eyebrow">CHẤM CÔNG · KIỂM TRA SỰ CỐ</p>
                    <h1 id="attendance-page-title">Lịch sử quét thất bại</h1>
                    <p>Các lượt quét không tạo hoặc cập nhật chấm công.</p>
                </div>
                <a class="button button--secondary button--small" href="/?action=attendance">Về chấm công</a>
            </div>
            <?php require __DIR__ . '/partials/scan_history.php'; ?>
        <?php else: ?>
            <div class="attendance-page-heading">
                <div>
                    <p class="eyebrow">QUẢN TRỊ · LỊCH SỬ</p>
                    <h1 id="attendance-page-title">Chấm công</h1>
                    <p>Lọc lịch sử vào/ra, trạng thái và ảnh bằng chứng.</p>
                </div>
                <a class="button button--secondary button--small" href="/?action=attendance&amp;tab=scan_history">Quét thất bại</a>
            </div>
        <form class="workspace-filters attendance-workspace-filters" method="get" action="/">
            <input type="hidden" name="action" value="attendance">
            <div class="filter-grid attendance-filter-grid">
                <div class="form-field">
                    <label for="attendance-from">Từ ngày</label>
                    <input id="attendance-from" type="date" name="from_date" value="<?= htmlspecialchars($fromDate, ENT_QUOTES, 'UTF-8') ?>" required>
                    <?php if (isset($errors['from_date'])): ?><p class="field-error"><?= htmlspecialchars($errors['from_date'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="attendance-to">Đến ngày</label>
                    <input id="attendance-to" type="date" name="to_date" value="<?= htmlspecialchars($toDate, ENT_QUOTES, 'UTF-8') ?>" required>
                    <?php if (isset($errors['to_date'])): ?><p class="field-error"><?= htmlspecialchars($errors['to_date'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="attendance-employee">Nhân viên</label>
                    <select id="attendance-employee" name="employee_id">
                        <option value="">Tất cả nhân viên</option>
                        <?php foreach ($employees as $employee): ?>
                            <?php $id = (int)$employee['MaNV']; ?>
                            <option value="<?= $id ?>" <?= $employeeId === $id ? 'selected' : '' ?>>
                                NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?> · <?= htmlspecialchars((string)($employee['HoTen'] ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>
                            </option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['employee_id'])): ?><p class="field-error"><?= htmlspecialchars($errors['employee_id'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="attendance-status">Trạng thái</label>
                    <select id="attendance-status" name="status">
                        <option value="" <?= $status === '' ? 'selected' : '' ?>>Tất cả trạng thái</option>
                        <option value="not_checked" <?= $status === 'not_checked' ? 'selected' : '' ?>>Chưa chấm vào</option>
                        <option value="on_time_in" <?= $status === 'on_time_in' ? 'selected' : '' ?>>Vào đúng giờ</option>
                        <option value="working" <?= $status === 'working' ? 'selected' : '' ?>>Đang làm việc</option>
                        <option value="late" <?= $status === 'late' ? 'selected' : '' ?>>Đi trễ</option>
                        <option value="on_time_out" <?= $status === 'on_time_out' ? 'selected' : '' ?>>Ra đúng giờ</option>
                        <option value="early" <?= $status === 'early' ? 'selected' : '' ?>>Về sớm</option>
                        <option value="completed" <?= $status === 'completed' ? 'selected' : '' ?>>Đã chấm vào và ra</option>
                    </select>
                    <?php if (isset($errors['status'])): ?><p class="field-error"><?= htmlspecialchars($errors['status'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="attendance-keyword">Mã hoặc họ tên</label>
                    <input id="attendance-keyword" type="search" name="keyword" value="<?= htmlspecialchars($keyword, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>" maxlength="100" placeholder="Tìm MaNV hoặc HoTen">
                    <?php if (isset($errors['keyword'])): ?><p class="field-error"><?= htmlspecialchars($errors['keyword'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="attendance-limit">Số dòng</label>
                    <select id="attendance-limit" name="limit"><?php foreach ([10, 20, 50, 100] as $size): ?><option value="<?= $size ?>" <?= $limit === $size ? 'selected' : '' ?>><?= $size ?></option><?php endforeach; ?></select>
                </div>
            </div>
            <?php if (isset($errors['date_range'])): ?><p class="field-error" role="alert"><?= htmlspecialchars($errors['date_range'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
            <div class="workspace-filter-actions">
                <button class="button button--primary button--small" type="submit">Lọc</button>
                <a class="text-action" href="/?action=attendance">Hôm nay</a>
            </div>
        </form>

    <?php if ($error !== null): ?>
        <div class="notice notice--error" role="alert"><?= htmlspecialchars($error, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
    <?php endif; ?>

    <div class="workspace-table">
        <?php if ($errors === [] && $error === null && $attendanceRows === []): ?>
            <div class="empty-state">Không có dữ liệu chấm công phù hợp.</div>
        <?php elseif ($attendanceRows !== []): ?>
            <div class="table-scroll">
                <table class="employee-table data-table attendance-table">
                    <caption class="visually-hidden">Trạng thái chấm công và ảnh bằng chứng</caption>
                    <thead><tr>
                        <th>Ngày</th><th>Mã NV</th><th>Họ tên</th><th>Ca</th>
                        <th>Giờ vào</th><th>Ảnh vào</th><th>Giờ ra</th><th>Ảnh ra</th>
                        <th>Trạng thái vào</th><th>Trạng thái ra</th>
                    </tr></thead>
                    <tbody>
                    <?php foreach ($attendanceRows as $row): ?>
                        <?php
                        $id = (int)$row['MaNV'];
                        $employeeCode = 'NV' . str_pad((string)$id, 3, '0', STR_PAD_LEFT);
                        $employeeName = (string)($row['HoTen'] ?? '');
                        $evidencePerson = $employeeName;
                        $evidenceCode = $employeeCode;
                        $evidenceAttendanceId = isset($row['MaCC']) ? (int)$row['MaCC'] : null;
                        $h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
                        ?>
                        <tr>
                            <td><?= htmlspecialchars((string)($row['Ngay'] ?? $fromDate), ENT_QUOTES, 'UTF-8') ?></td>
                            <td><span class="employee-code"><?= $h($employeeCode) ?></span></td>
                            <td><?= $h($employeeName) ?></td>
                            <td><?= htmlspecialchars((string)($row['TenCa'] ?? '--') ?: '--', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><?= $row['GioVao'] ? htmlspecialchars((new DateTimeImmutable((string)$row['GioVao']))->format('H:i:s'), ENT_QUOTES, 'UTF-8') : '--' ?></td>
                            <td class="evidence-cell">
                                <?php
                                $evidenceAction = '/?action=attendance_image_in';
                                $evidenceKind = 'Ảnh vào';
                                $evidenceTime = !empty($row['GioVao']) ? (new DateTimeImmutable((string)$row['GioVao']))->format('d/m/Y H:i:s') : '';
                                if ((int)$row['HasImageIn'] === 1) {
                                    require __DIR__ . '/partials/evidence_thumbnail.php';
                                } else {
                                    echo '<span class="evidence-empty">--</span>';
                                }
                                ?>
                            </td>
                            <td><?= $row['GioRa'] ? htmlspecialchars((new DateTimeImmutable((string)$row['GioRa']))->format('H:i:s'), ENT_QUOTES, 'UTF-8') : '--' ?></td>
                            <td class="evidence-cell">
                                <?php
                                $evidenceAction = '/?action=attendance_image_out';
                                $evidenceKind = 'Ảnh ra';
                                $evidenceTime = !empty($row['GioRa']) ? (new DateTimeImmutable((string)$row['GioRa']))->format('d/m/Y H:i:s') : '';
                                if ((int)$row['HasImageOut'] === 1) {
                                    require __DIR__ . '/partials/evidence_thumbnail.php';
                                } else {
                                    echo '<span class="evidence-empty">--</span>';
                                }
                                ?>
                            </td>
                            <td><?= htmlspecialchars((string)$row['TrangThaiVao'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><?= htmlspecialchars((string)$row['TrangThaiRa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
            <?php if ($totalPages > 1): ?>
                <nav class="attendance-pagination" aria-label="Phân trang lịch sử chấm công">
                    <?php if ($page > 1): ?>
                        <a class="button button--secondary button--small" href="<?= htmlspecialchars($pageUrl($page - 1), ENT_QUOTES, 'UTF-8') ?>">Trang trước</a>
                    <?php else: ?>
                        <span class="button button--secondary button--small is-disabled" aria-disabled="true">Trang trước</span>
                    <?php endif; ?>
                    <span>Trang <?= (int)$page ?> / <?= (int)$totalPages ?></span>
                    <?php if ($page < $totalPages): ?>
                        <a class="button button--secondary button--small" href="<?= htmlspecialchars($pageUrl($page + 1), ENT_QUOTES, 'UTF-8') ?>">Trang sau</a>
                    <?php else: ?>
                        <span class="button button--secondary button--small is-disabled" aria-disabled="true">Trang sau</span>
                    <?php endif; ?>
                </nav>
            <?php endif; ?>
        <?php endif; ?>
    </div>
        <?php endif; ?>
    </section>
</main>
<?php require __DIR__ . '/partials/evidence_lightbox.php'; ?>
<script src="/public/js/evidence_lightbox.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>
