<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#f6f7f9">
    <title><?= htmlspecialchars($pageTitle ?? 'Quản lý nhân viên | Smart Attendance', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></title>
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="/public/css/app.css">
</head>
<body>
<header class="topbar">
    <a class="brand" href="<?= (int)($_SESSION['ma_vai_tro'] ?? 0) === 2 ? '/?action=my' : '/?action=dashboard' ?>" aria-label="Smart Attendance">
        <span class="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none">
                <path d="M12 3.5v4M12 16.5v4M3.5 12h4m9 0h4M6 6l2.8 2.8m6.4 6.4L18 18M18 6l-2.8 2.8M8.8 15.2 6 18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                <circle cx="12" cy="12" r="4.1" stroke="currentColor" stroke-width="1.8"/>
            </svg>
        </span>
        <span class="brand-name">Smart Attendance</span>
    </a>
    <?php if (isset($_SESSION['user_id'])): ?>
        <?php if ((int)($_SESSION['ma_vai_tro'] ?? 0) === 1): ?>
            <?php $activeAction = $_GET['action'] ?? 'index'; ?>
            <nav class="topbar-nav" aria-label="Quản lý">
                <a href="/?action=dashboard" <?= $activeAction === 'dashboard' ? 'aria-current="page"' : '' ?>>Tổng quan</a>
                <a href="/" <?= $activeAction === 'index' ? 'aria-current="page"' : '' ?>>Nhân viên</a>
                <a href="/?action=shifts" <?= $activeAction === 'shifts' ? 'aria-current="page"' : '' ?>>Phân ca</a>
                <a href="/?action=attendance" <?= $activeAction === 'attendance' ? 'aria-current="page"' : '' ?>>Chấm công</a>
                <a href="/?action=health" <?= $activeAction === 'health' ? 'aria-current="page"' : '' ?>>Sức khỏe</a>
                <a href="/?action=alerts" <?= $activeAction === 'alerts' ? 'aria-current="page"' : '' ?>>Cảnh báo</a>
                <a href="/?action=ai_camera" <?= $activeAction === 'ai_camera' ? 'aria-current="page"' : '' ?>>Camera AI</a>
            </nav>
        <?php elseif ((int)($_SESSION['ma_vai_tro'] ?? 0) === 2): ?>
            <nav class="topbar-nav" aria-label="Trang cá nhân">
                <a href="/?action=my" <?= ($_GET['action'] ?? '') === 'my' ? 'aria-current="page"' : '' ?>>Trang của tôi</a>
            </nav>
        <?php endif; ?>
        <div class="topbar-account">
            <div class="account-meta">
                <span class="account-name"><?= htmlspecialchars((string)($_SESSION['display_name'] ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></span>
                <span class="account-role"><?= htmlspecialchars((string)($_SESSION['role'] ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></span>
            </div>
            <form class="logout-form" method="post" action="/?action=logout">
                <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars((string)($_SESSION['employee_csrf_token'] ?? ''), ENT_QUOTES, 'UTF-8') ?>">
                <button class="logout-button" type="submit">Đăng xuất</button>
            </form>
        </div>
    <?php endif; ?>
</header>
