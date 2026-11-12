<section class="live-monitor" data-live-attendance aria-label="Giám sát camera và lượt chấm công gần đây">
    <div class="live-monitor-heading">
        <div>
            <p class="eyebrow">CHẤM CÔNG · GIÁM SÁT</p>
            <h1>Camera và hoạt động gần đây</h1>
            <p>Trang chỉ giám sát, không ghi hoặc sửa lượt chấm công. Camera lấy từ nguồn singleton đang cấu hình trong dịch vụ.</p>
        </div>
        <p class="live-monitor-updated" data-live-feed-status role="status" aria-live="polite">Đang tải hoạt động…</p>
    </div>

    <?php if ($error !== null): ?>
        <div class="notice notice--error" role="alert"><?= htmlspecialchars($error, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
    <?php endif; ?>

    <div class="live-monitor-grid">
        <section class="live-monitor-panel" aria-label="Hình camera">
            <div class="live-monitor-panel-heading">
                <h2>Camera hiện tại</h2>
                <span data-live-camera-status role="status" aria-live="polite">Đang kết nối…</span>
            </div>
            <div class="live-monitor-camera">
                <img data-live-camera alt="Hình ảnh từ camera singleton" decoding="async">
            </div>
            <p class="live-monitor-note">Nguồn Webcam hoặc ESP32-CAM được cấu hình khi khởi động dịch vụ AI. Trang này không tự mở camera thứ hai.</p>
        </section>

        <section class="live-monitor-panel" aria-label="Lượt chấm công gần đây">
            <div class="live-monitor-panel-heading">
                <h2>Lượt chấm công gần nhất</h2>
                <span>Cập nhật định kỳ</span>
            </div>
            <div class="table-scroll">
                <table class="employee-table data-table live-monitor-table">
                    <caption class="visually-hidden">Các lượt chấm công gần nhất trong hệ thống</caption>
                    <thead>
                    <tr>
                        <th>Mã NV</th>
                        <th>Họ tên</th>
                        <th>Lượt</th>
                        <th>Ca</th>
                        <th>Thời gian</th>
                    </tr>
                    </thead>
                    <tbody data-live-attendance-rows>
                    <?php if ($recentPunches === []): ?>
                        <tr><td colspan="5" class="live-monitor-empty">Chưa có lượt chấm công.</td></tr>
                    <?php else: ?>
                        <?php foreach ($recentPunches as $row): ?>
                            <?php $isOut = ($row['PunchType'] ?? 'IN') === 'OUT'; ?>
                            <tr>
                                <td>NV<?= str_pad((string)(int)$row['MaNV'], 3, '0', STR_PAD_LEFT) ?></td>
                                <td><?= htmlspecialchars((string)$row['HoTen'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                                <td><span class="live-punch-tag <?= $isOut ? 'live-punch-tag--out' : 'live-punch-tag--in' ?>"><?= $isOut ? 'Check-out' : 'Check-in' ?></span></td>
                                <td><?= htmlspecialchars((string)($row['TenCa'] ?? '—'), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                                <td><?= htmlspecialchars((string)($row['EventTime'] ?? '—'), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                    </tbody>
                </table>
            </div>
        </section>
    </div>
</section>
