<?php require __DIR__ . '/layout/header.php'; ?>
<main class="page-container">
    <section class="page-heading" aria-labelledby="page-title">
        <div>
            <p class="eyebrow">Quản lý</p>
            <h1 id="page-title">Phân ca nhân viên</h1>
            <p class="page-description">Xem ca theo ngày và phân ca cho nhân viên.</p>
        </div>
    </section>

    <?php if ($successMessage !== null): ?>
        <div class="notice notice--success" role="status"><?= htmlspecialchars((string)$successMessage, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
    <?php endif; ?>
    <?php if ($error !== null): ?>
        <div class="notice notice--error" role="alert"><?= htmlspecialchars($error, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
    <?php endif; ?>

    <section class="form-panel shift-panel" aria-labelledby="assign-shift-title">
        <div class="section-heading">
            <div>
                <h2 id="assign-shift-title">Phân ca</h2>
                <p class="section-description">Nếu nhân viên đã có ca trong ngày, ca đó sẽ được cập nhật.</p>
            </div>
        </div>
        <form class="employee-form" method="post" action="/?action=assign_shift">
            <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
            <div class="filter-grid">
                <div class="form-field">
                    <label for="shift-employee">Nhân viên</label>
                    <select id="shift-employee" name="MaNV" required aria-invalid="<?= isset($errors['MaNV']) ? 'true' : 'false' ?>">
                        <option value="">Chọn nhân viên</option>
                        <?php foreach ($employees as $employee): ?>
                            <?php $id = (int)$employee['MaNV']; ?>
                            <option value="<?= $id ?>" <?= (string)($formValues['MaNV'] ?? '') === (string)$id ? 'selected' : '' ?>>
                                NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?> · <?= htmlspecialchars((string)($employee['HoTen'] ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>
                            </option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['MaNV'])): ?><p class="field-error"><?= htmlspecialchars($errors['MaNV'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="shift-id">Ca làm việc</label>
                    <select id="shift-id" name="MaCa" required aria-invalid="<?= isset($errors['MaCa']) ? 'true' : 'false' ?>">
                        <option value="">Chọn ca</option>
                        <?php foreach ($availableShifts as $shift): ?>
                            <?php $id = (int)$shift['MaCa']; ?>
                            <option value="<?= $id ?>" <?= (string)($formValues['MaCa'] ?? '') === (string)$id ? 'selected' : '' ?>>
                                <?= htmlspecialchars((string)$shift['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?> (<?= htmlspecialchars(substr((string)$shift['GioBatDau'], 0, 5), ENT_QUOTES, 'UTF-8') ?>–<?= htmlspecialchars(substr((string)$shift['GioKetThuc'], 0, 5), ENT_QUOTES, 'UTF-8') ?>)
                            </option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['MaCa'])): ?><p class="field-error"><?= htmlspecialchars($errors['MaCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="shift-date">Ngày làm việc</label>
                    <input id="shift-date" type="date" name="NgayLamViec" value="<?= htmlspecialchars((string)($formValues['NgayLamViec'] ?? $selectedDate), ENT_QUOTES, 'UTF-8') ?>" required aria-invalid="<?= isset($errors['NgayLamViec']) ? 'true' : 'false' ?>">
                    <?php if (isset($errors['NgayLamViec'])): ?><p class="field-error"><?= htmlspecialchars($errors['NgayLamViec'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
            </div>
            <div class="form-actions">
                <button class="button button--primary" type="submit">Lưu phân ca</button>
            </div>
        </form>
    </section>

    <section class="employee-section" aria-labelledby="assignment-list-title">
        <div class="section-heading">
            <div>
                <h2 id="assignment-list-title">Nhân viên đã phân ca</h2>
                <p class="section-description">Ngày <?= htmlspecialchars($selectedDate, ENT_QUOTES, 'UTF-8') ?> · <?= count($assignments) ?> phân ca</p>
            </div>
            <form class="inline-filter" method="get" action="/">
                <input type="hidden" name="action" value="shifts">
                <label for="assignment-date">Ngày</label>
                <input id="assignment-date" type="date" name="date" value="<?= htmlspecialchars($selectedDate, ENT_QUOTES, 'UTF-8') ?>" required>
                <button class="button button--secondary" type="submit">Xem</button>
            </form>
        </div>
        <?php if ($error === null && $assignments === []): ?>
            <div class="empty-state">Chưa có nhân viên được phân ca trong ngày này.</div>
        <?php elseif ($assignments !== []): ?>
            <div class="table-scroll">
                <table class="employee-table data-table">
                    <caption class="visually-hidden">Phân ca nhân viên ngày <?= htmlspecialchars($selectedDate, ENT_QUOTES, 'UTF-8') ?></caption>
                    <thead><tr><th>Mã nhân viên</th><th>Họ tên</th><th>Ca</th><th>Thời gian</th></tr></thead>
                    <tbody>
                    <?php foreach ($assignments as $assignment): ?>
                        <?php $id = (int)$assignment['MaNV']; ?>
                        <tr>
                            <td><span class="employee-code">NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?></span></td>
                            <td><?= htmlspecialchars((string)($assignment['HoTen'] ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><?= htmlspecialchars((string)$assignment['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><?= htmlspecialchars(substr((string)$assignment['GioBatDau'], 0, 5), ENT_QUOTES, 'UTF-8') ?>–<?= htmlspecialchars(substr((string)$assignment['GioKetThuc'], 0, 5), ENT_QUOTES, 'UTF-8') ?></td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>
