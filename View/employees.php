<?php require __DIR__ . '/layout/header.php'; ?>
<main class="page-container">
    <section class="workspace" aria-labelledby="employee-list-title">
        <?php if ($successMessage !== null): ?>
            <div class="notice notice--success" role="status"><?= htmlspecialchars((string)$successMessage, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php endif; ?>
        <?php if ($deleteWarningMessage !== null): ?>
            <div class="notice notice--warning" role="alert"><?= htmlspecialchars((string)$deleteWarningMessage, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php endif; ?>
        <?php if ($deleteErrorMessage !== null): ?>
            <div class="notice notice--error" role="alert"><?= htmlspecialchars((string)$deleteErrorMessage, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php endif; ?>
        <div class="workspace-toolbar">
            <h1 id="employee-list-title">Nhân viên (<span id="visible-count"><?= count($employees) ?></span>)</h1>
            <label class="search-field">
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="10.8" cy="10.8" r="6.3" stroke="currentColor" stroke-width="1.7"/>
                    <path d="m15.5 15.5 4 4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
                </svg>
                <span class="visually-hidden">Tìm theo mã nhân viên hoặc họ tên</span>
                <input id="employee-search" type="search" placeholder="Tìm mã nhân viên hoặc họ tên" autocomplete="off">
            </label>
            <a class="button button--primary" href="/?action=create">Thêm nhân viên</a>
        </div>

        <?php if ($error !== null): ?>
            <div class="notice notice--error" role="alert"><?= htmlspecialchars($error, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php elseif ($employees === []): ?>
            <div class="empty-state">Chưa có nhân viên trong hệ thống.</div>
        <?php else: ?>
            <div class="table-scroll">
                <table class="employee-table employees-list-table">
                    <caption class="visually-hidden">Danh sách nhân viên và trạng thái đăng ký khuôn mặt</caption>
                    <thead>
                    <tr>
                        <th scope="col">Mã nhân viên</th>
                        <th scope="col">Họ tên</th>
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
                        $faceCount = (int)($employee['FaceEmbeddingCount'] ?? 0);
                        $searchValue = $employeeCode . ' ' . $employeeId . ' ' . $employeeName;
                        $deleteConfirmation = 'Bạn có chắc muốn xóa nhân viên ' . $employeeCode . ' – '
                            . ($employeeName !== '' ? $employeeName : 'Chưa cập nhật')
                            . '? Chỉ có thể xóa nếu nhân viên chưa đăng ký khuôn mặt và không có lịch sử hoặc dữ liệu liên quan. Nếu đủ điều kiện, hồ sơ và tài khoản liên kết sẽ bị xóa vĩnh viễn; thao tác này không thể hoàn tác.';
                        ?>
                        <tr class="employee-row" data-search="<?= htmlspecialchars($searchValue, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>">
                            <td><span class="employee-code"><?= htmlspecialchars($employeeCode, ENT_QUOTES, 'UTF-8') ?></span></td>
                            <td class="employee-name"><?= htmlspecialchars($employeeName !== '' ? $employeeName : 'Chưa cập nhật', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td>
                                <?php if ($faceCount > 0): ?>
                                    <span class="status-pill status-pill--registered"><span aria-hidden="true"></span>Đã đăng ký · <?= $faceCount ?> mẫu</span>
                                <?php else: ?>
                                    <span class="status-pill status-pill--pending"><span aria-hidden="true"></span>Chưa đăng ký</span>
                                <?php endif; ?>
                            </td>
                            <td class="employee-actions">
                                <a class="button button--secondary button--small" href="/?action=edit&amp;id=<?= $employeeId ?>" aria-label="Sửa <?= htmlspecialchars($employeeName, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>">Sửa</a>
                                <form class="inline-action-form" method="post" action="/?action=delete_employee" onsubmit="return confirm(this.dataset.confirm)" data-confirm="<?= htmlspecialchars($deleteConfirmation, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>">
                                    <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>">
                                    <input type="hidden" name="MaNV" value="<?= $employeeId ?>">
                                    <button class="button button--danger button--small" type="submit" aria-label="Xóa <?= htmlspecialchars($employeeName, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>">Xóa</button>
                                </form>
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
