<?php require __DIR__ . '/layout/header.php'; ?>
<?php $h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); ?>
<main class="page-container">
    <section class="workspace" aria-labelledby="device-list-title">
        <div class="workspace-toolbar">
            <h1 id="device-list-title">Thiết bị<?php if ($error === null): ?> (<?= count($devices) ?>)<?php endif; ?></h1>
            <p class="device-list-description">Danh sách thiết bị chấm công đã được khai báo trong hệ thống.</p>
        </div>

        <?php if ($error !== null): ?>
            <div class="notice notice--error" role="alert"><?= $h($error) ?></div>
        <?php elseif ($devices === []): ?>
            <div class="empty-state">Chưa có thiết bị được khai báo.</div>
        <?php else: ?>
            <div class="table-scroll">
                <table class="employee-table data-table">
                    <caption class="visually-hidden">Danh sách thiết bị chấm công</caption>
                    <thead>
                        <tr><th scope="col">Mã thiết bị</th><th scope="col">Loại thiết bị</th><th scope="col">Trạng thái</th></tr>
                    </thead>
                    <tbody>
                        <?php foreach ($devices as $device): ?>
                            <tr>
                                <td><span class="employee-code">TB<?= str_pad((string)(int)$device['MaTB'], 3, '0', STR_PAD_LEFT) ?></span></td>
                                <td><?= $h($device['LoaiTB'] ?? '--') ?></td>
                                <td><?= $h($device['TrangThai'] ?? '--') ?></td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>
