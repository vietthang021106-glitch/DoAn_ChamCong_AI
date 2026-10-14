<?php require __DIR__ . '/layout/header.php'; ?>
<main class="page-container ai-page">
    <div class="page-heading">
        <div>
            <p class="eyebrow">Nhận diện khuôn mặt</p>
            <h1>Camera AI</h1>
            <p class="page-description">Nhận diện thử từ camera hiện tại. Chức năng này không ghi chấm công.</p>
        </div>
        <div class="ai-service-status <?= !empty($health['success']) && !empty($health['model_ready']) && !empty($health['gallery_ready']) ? 'is-online' : 'is-offline' ?>" role="status">
            <span></span>
            <?= !empty($health['success']) ? (!empty($health['model_ready']) ? 'AI service Online' : 'AI service lỗi model') : 'AI service Offline' ?>
        </div>
    </div>

    <section class="ai-layout" aria-label="Camera và kết quả nhận diện">
        <div class="ai-camera-panel">
            <div class="ai-panel-heading">
                <h2>Camera</h2>
                <span><?= htmlspecialchars((string)($health['camera_source'] ?? 'Flask camera singleton'), ENT_QUOTES, 'UTF-8') ?></span>
            </div>
            <div class="ai-camera-frame">
                <img id="ai-camera-image" src="/?action=ai_camera_frame" alt="Hình ảnh từ camera dùng chung">
                <p id="ai-camera-placeholder" hidden>Không nhận được hình ảnh camera.</p>
            </div>
            <div class="ai-camera-actions">
                <button class="button button--primary" id="ai-recognize" type="button" <?= empty($health['success']) || empty($health['model_ready']) || empty($health['gallery_ready']) ? 'disabled' : '' ?>>
                    Nhận diện
                </button>
                <span class="ai-gallery-count">
                    Gallery: <?= (int)($health['embedding_count'] ?? 0) ?> embedding
                </span>
            </div>
        </div>

        <section class="ai-result-panel" aria-live="polite">
            <h2>Kết quả</h2>
            <p class="ai-result-state" id="ai-result-state">Chưa nhận diện</p>
            <dl class="ai-result-details">
                <div><dt>Nhân viên</dt><dd id="ai-result-employee">—</dd></div>
                <div><dt>Mã nhân viên</dt><dd id="ai-result-code">—</dd></div>
                <div><dt>Similarity</dt><dd id="ai-result-score">—</dd></div>
                <div><dt>Trạng thái</dt><dd id="ai-result-match">—</dd></div>
            </dl>
        </section>
    </section>
    <input type="hidden" id="ai-csrf-token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
</main>
<script src="/public/js/ai_camera.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>
