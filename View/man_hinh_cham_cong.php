<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#f1f3f4">
    <title><?= htmlspecialchars($pageTitle ?? 'Màn hình chấm công', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></title>
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="/public/css/man_hinh_cham_cong.css?v=<?= (int)filemtime(__DIR__ . '/../public/css/man_hinh_cham_cong.css') ?>">
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
            <section class="terminal-enrollment-banner" data-terminal-enrollment hidden aria-live="polite">
                <span data-terminal-enrollment-message>Hãy nhìn vào camera.</span>
                <strong data-terminal-enrollment-progress>0/5</strong>
            </section>
            <div class="terminal-camera" data-terminal-camera-wrap>
                <img data-terminal-camera alt="Hình ảnh trực tiếp từ camera chấm công" hidden>
                <canvas data-terminal-result-frame aria-label="Khung hình nhận diện gần nhất" hidden></canvas>
                <svg data-terminal-scan-ring class="terminal-scan-ring" aria-hidden="true" hidden></svg>
                <section class="terminal-result-overlay" data-terminal-result-overlay aria-live="assertive" hidden>
                    <div class="terminal-result-card" data-state="idle">
                        <p class="terminal-result-title" data-terminal-result-title></p>
                        <h2 class="terminal-result-greeting" data-terminal-result-greeting hidden></h2>
                        <p class="terminal-result-message" data-terminal-result-message hidden></p>
                    </div>
                </section>
                <div class="terminal-camera-empty" data-terminal-camera-empty>
                    <?php if ($deviceError !== null): ?>
                        <?= htmlspecialchars($deviceError, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>
                    <?php else: ?>
                        Đang kết nối camera...
                    <?php endif; ?>
                </div>
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
<script src="/public/js/enrollment_ui_helpers.js?v=<?= (int)filemtime(__DIR__ . '/../public/js/enrollment_ui_helpers.js') ?>" defer></script>
<script src="/public/js/kiosk_result_overlay.js?v=<?= (int)filemtime(__DIR__ . '/../public/js/kiosk_result_overlay.js') ?>" defer></script>
<script src="/public/js/man_hinh_cham_cong.js?v=<?= (int)filemtime(__DIR__ . '/../public/js/man_hinh_cham_cong.js') ?>" defer></script>
</body>
</html>
