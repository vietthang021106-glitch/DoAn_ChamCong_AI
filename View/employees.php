<?php require __DIR__ . '/layout/header.php'; ?>
<main class="page-container">
    <section class="page-heading" aria-labelledby="page-title">
        <div>
            <p class="eyebrow">Quản lý</p>
            <h1 id="page-title">Quản lý nhân viên</h1>
            <p class="page-description">Danh sách nhân viên và trạng thái đăng ký khuôn mặt.</p>
        </div>
        <a class="button button--primary" href="/?action=create">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
            </svg>
            Thêm nhân viên
        </a>
    </section>

    <section class="summary-grid" aria-label="Tổng quan nhân viên">
        <article class="summary-item">
            <span class="summary-label">Tổng số nhân viên</span>
            <strong class="summary-value"><?= (int)$stats['total'] ?></strong>
        </article>
        <article class="summary-item summary-item--registered">
            <span class="summary-label">Đã đăng ký khuôn mặt</span>
            <strong class="summary-value"><?= (int)$stats['registered'] ?></strong>
        </article>
        <article class="summary-item summary-item--pending">
            <span class="summary-label">Chưa đăng ký khuôn mặt</span>
            <strong class="summary-value"><?= (int)$stats['not_registered'] ?></strong>
        </article>
    </section>

    <section class="employee-section" aria-labelledby="employee-list-title">
        <?php if ($successMessage !== null): ?>
            <div class="notice notice--success" role="status"><?= htmlspecialchars((string)$successMessage, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php endif; ?>
        <div class="section-heading">
            <div>
                <h2 id="employee-list-title">Danh sách nhân viên</h2>
                <p class="section-description"><span id="visible-count"><?= count($employees) ?></span> nhân viên</p>
            </div>
            <label class="search-field">
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="10.8" cy="10.8" r="6.3" stroke="currentColor" stroke-width="1.7"/>
                    <path d="m15.5 15.5 4 4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
                </svg>
                <span class="visually-hidden">Tìm theo mã hoặc họ tên</span>
                <input id="employee-search" type="search" placeholder="Tìm theo mã hoặc họ tên" autocomplete="off">
            </label>
        </div>

        <?php if ($error !== null): ?>
            <div class="notice notice--error" role="alert"><?= htmlspecialchars($error, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php elseif ($employees === []): ?>
            <div class="empty-state">Chưa có nhân viên trong hệ thống.</div>
        <?php else: ?>
            <div class="table-scroll">
                <table class="employee-table">
                    <caption class="visually-hidden">Danh sách nhân viên và trạng thái đăng ký khuôn mặt</caption>
                    <thead>
                    <tr>
                        <th scope="col">Mã nhân viên</th>
                        <th scope="col">Họ tên</th>
                        <th scope="col">Vai trò</th>
                        <th scope="col">Khuôn mặt</th>
                        <th scope="col"><span class="visually-hidden">Thao tác</span></th>
                    </tr>
                    </thead>
                    <tbody id="employee-rows">
                    <?php foreach ($employees as $employee): ?>
                        <?php
                        $employeeId = (int)$employee['MaNV'];
                        $employeeCode = 'NV' . str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT);
                        $employeeName = (string)($employee['HoTen'] ?? '');
                        $role = (string)($employee['TenVaiTro'] ?? 'Chưa phân vai trò');
                        $faceRegistered = (int)$employee['FaceRegistered'] === 1;
                        $searchValue = $employeeCode . ' ' . $employeeId . ' ' . $employeeName;
                        ?>
                        <tr class="employee-row" data-search="<?= htmlspecialchars($searchValue, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>">
                            <td><span class="employee-code"><?= htmlspecialchars($employeeCode, ENT_QUOTES, 'UTF-8') ?></span></td>
                            <td class="employee-name"><?= htmlspecialchars($employeeName !== '' ? $employeeName : 'Chưa cập nhật', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><span class="role-label"><?= htmlspecialchars($role, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></span></td>
                            <td>
                                <?php if ($faceRegistered): ?>
                                    <span class="status-pill status-pill--registered"><span aria-hidden="true"></span>Đã đăng ký</span>
                                <?php else: ?>
                                    <span class="status-pill status-pill--pending"><span aria-hidden="true"></span>Chưa đăng ký</span>
                                <?php endif; ?>
                            </td>
                            <td class="employee-actions">
                                <a class="button button--secondary button--small" href="/?action=edit&amp;id=<?= $employeeId ?>" aria-label="Sửa <?= htmlspecialchars($employeeName, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>">Sửa</a>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
            <p class="empty-search" id="empty-search" hidden>Không tìm thấy nhân viên phù hợp.</p>
        <?php endif; ?>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>
