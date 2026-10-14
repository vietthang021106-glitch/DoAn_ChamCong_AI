<?php
require __DIR__ . '/layout/header.php';
$isEdit = $mode === 'edit';
$employeeId = $isEdit ? (int)$employee['MaNV'] : null;
$employeeName = $values['HoTen'] ?? ($employee['HoTen'] ?? '');
$selectedRole = $values['MaVaiTro'] ?? ($employee['MaVaiTro'] ?? null);
$formAction = $isEdit ? '/?action=update&amp;id=' . $employeeId : '/?action=store';
?>
<main class="page-container page-container--form">
    <a class="back-link" href="/">&larr; Danh sách nhân viên</a>
    <section class="page-heading" aria-labelledby="page-title">
        <div>
            <p class="eyebrow">Quản lý</p>
            <h1 id="page-title"><?= $isEdit ? 'Sửa nhân viên' : 'Thêm nhân viên' ?></h1>
            <p class="page-description"><?= $isEdit ? 'Cập nhật họ tên và vai trò.' : 'Nhập thông tin cơ bản để tạo hồ sơ nhân viên.' ?></p>
        </div>
    </section>

    <section class="form-panel" aria-label="Thông tin nhân viên">
        <?php if ($errors !== []): ?>
            <div class="notice notice--error" role="alert">Vui lòng kiểm tra lại thông tin bên dưới.</div>
        <?php endif; ?>

        <form class="employee-form" method="post" action="<?= $formAction ?>">
            <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">

            <?php if ($isEdit): ?>
                <div class="form-field">
                    <label for="employee-code">Mã nhân viên</label>
                    <input id="employee-code" type="text" value="NV<?= htmlspecialchars(str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT), ENT_QUOTES, 'UTF-8') ?>" readonly>
                    <p class="field-hint">Mã nhân viên không thể thay đổi.</p>
                </div>
            <?php endif; ?>

            <div class="form-field">
                <label for="employee-name">Họ tên <span aria-hidden="true">*</span></label>
                <input
                    id="employee-name"
                    name="HoTen"
                    type="text"
                    value="<?= htmlspecialchars((string)$employeeName, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>"
                    maxlength="100"
                    autocomplete="name"
                    required
                    aria-invalid="<?= isset($errors['HoTen']) ? 'true' : 'false' ?>"
                    aria-describedby="employee-name-error"
                >
                <?php if (isset($errors['HoTen'])): ?>
                    <p class="field-error" id="employee-name-error"><?= htmlspecialchars($errors['HoTen'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p>
                <?php endif; ?>
            </div>

            <div class="form-field">
                <label for="employee-role">Vai trò <span aria-hidden="true">*</span></label>
                <select
                    id="employee-role"
                    name="MaVaiTro"
                    required
                    aria-invalid="<?= isset($errors['MaVaiTro']) ? 'true' : 'false' ?>"
                    aria-describedby="employee-role-error"
                >
                    <option value="">Chọn vai trò</option>
                    <?php foreach ($roles as $role): ?>
                        <?php $roleId = (int)$role['MaVaiTro']; ?>
                        <option value="<?= $roleId ?>" <?= (string)$selectedRole === (string)$roleId ? 'selected' : '' ?>>
                            <?= htmlspecialchars((string)$role['TenVaiTro'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>
                        </option>
                    <?php endforeach; ?>
                </select>
                <?php if (isset($errors['MaVaiTro'])): ?>
                    <p class="field-error" id="employee-role-error"><?= htmlspecialchars($errors['MaVaiTro'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p>
                <?php endif; ?>
            </div>

            <div class="form-actions">
                <a class="button button--secondary" href="/">Hủy</a>
                <button class="button button--primary" type="submit"><?= $isEdit ? 'Lưu thay đổi' : 'Tạo nhân viên' ?></button>
            </div>
        </form>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>
