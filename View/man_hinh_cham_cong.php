<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#f1f3f4">
    <title><?= htmlspecialchars($pageTitle ?? 'Màn hình chấm công', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></title>
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="/public/css/man_hinh_cham_cong.css">
</head>
<body>
<div class="attendance-terminal"
     data-attendance-terminal
     data-csrf="<?= htmlspecialchars($csrfToken, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>"
     data-device-id="<?= $deviceId === null ? '' : (int)$deviceId ?>"
     data-device-ready="<?= $deviceId === null ? 'false' : 'true' ?>">
    <header class="terminal-header">
        <div class="terminal-title">
            <span class="terminal-mark" aria-hidden="true"></span>
            <div>
                <p>HỆ THỐNG</p>
                <h1>CHẤM CÔNG</h1>
            </div>
        </div>
        <div class="terminal-clock-block">
            <time class="terminal-clock" data-terminal-clock>--:--:--</time>
            <time class="terminal-date" data-terminal-date>Đang tải ngày</time>
        </div>
        <div class="terminal-device">
            <?= htmlspecialchars($deviceLabel !== '' ? $deviceLabel : 'THIẾT BỊ', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>
            <button class="terminal-fullscreen" type="button" data-terminal-fullscreen>Toàn màn hình</button>
        </div>
    </header>

    <main class="terminal-main">
        <section class="terminal-camera-section" aria-label="Camera chấm công">
            <div class="terminal-camera" data-terminal-camera-wrap>
                <img data-terminal-camera alt="Hình ảnh trực tiếp từ camera chấm công" hidden>
                <canvas data-terminal-result-frame aria-label="Khung hình nhận diện gần nhất" hidden></canvas>
                <svg data-terminal-scan-ring class="terminal-scan-ring" aria-hidden="true" hidden></svg>
                <div class="terminal-camera-empty" data-terminal-camera-empty>
                    <?php if ($deviceError !== null): ?>
                        <?= htmlspecialchars($deviceError, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>
                    <?php else: ?>
                        Đang kết nối camera...
                    <?php endif; ?>
                </div>
                <section class="terminal-enrollment-panel" data-terminal-enrollment hidden aria-live="polite">
                    <div class="terminal-enrollment-heading">
                        <div>
                            <p>ĐĂNG KÝ KHUÔN MẶT</p>
                            <strong data-terminal-enrollment-employee></strong>
                        </div>
                        <strong data-terminal-enrollment-progress>0/5</strong>
                    </div>
                    <p class="terminal-enrollment-pose" data-terminal-enrollment-pose>Đang chờ hướng dẫn</p>
                    <p class="terminal-enrollment-message" data-terminal-enrollment-message>Hãy nhìn vào camera.</p>
                    <ol class="terminal-enrollment-steps" data-terminal-enrollment-steps>
                        <li data-pose="frontal">Nhìn thẳng</li>
                        <li data-pose="left">Quay trái</li>
                        <li data-pose="right">Quay phải</li>
                        <li data-pose="up">Ngước lên</li>
                        <li data-pose="down">Cúi xuống</li>
                    </ol>
                </section>
            </div>
        </section>
    </main>

    <footer class="terminal-footer">
        <p class="terminal-status" data-terminal-status data-state="<?= $deviceError === null ? 'idle' : 'offline' ?>" role="status" aria-live="polite">
            <?= htmlspecialchars($deviceError === null ? 'Vui lòng nhìn vào camera.' : 'Màn hình chấm công chưa sẵn sàng.', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>
        </p>
        <p class="terminal-result" data-terminal-result hidden></p>
        <p class="terminal-hint" data-terminal-hint <?= $deviceError === null ? '' : 'hidden' ?>>Nhấn phím SPACE để bắt đầu chấm công</p>
    </footer>
</div>
<script src="/public/js/enrollment_ui_helpers.js" defer></script>
<script src="/public/js/man_hinh_cham_cong.js" defer></script>
</body>
</html>
