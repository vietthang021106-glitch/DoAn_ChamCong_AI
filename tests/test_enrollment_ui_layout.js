'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const read = (relative) => fs.readFileSync(path.join(__dirname, '..', relative), 'utf8');

test('kiosk enrollment uses one compact banner above the camera, without debug/list overlay', () => {
    const view = read('View/man_hinh_cham_cong.php');
    const css = read('public/css/man_hinh_cham_cong.css');
    const js = read('public/js/man_hinh_cham_cong.js');
    const banner = view.indexOf('data-terminal-enrollment');
    const camera = view.indexOf('data-terminal-camera-wrap');
    assert.ok(banner >= 0 && camera > banner, 'The instruction banner must precede the camera element.');
    assert.match(view, /data-terminal-enrollment-message/);
    assert.match(view, /data-terminal-enrollment-progress/);
    assert.doesNotMatch(view, /data-terminal-enrollment-(?:diagnostics|steps|pose|employee)/);
    assert.match(css, /\.terminal-enrollment-banner[\s\S]*?min-height:\s*56px/);
    assert.match(js, /Đã đủ 5 góc · Chờ quản lý xác nhận lưu\./);
    assert.doesNotMatch(js, /diagnosticsFor\(payload\)/);
});

test('admin confirmation state hides the empty camera but keeps captured thumbnails', () => {
    const js = read('public/js/face_enrollment.js');
    assert.match(js, /const showCompletedReview = \(duplicateCheck, demoBypassEnabled = false\) =>/);
    assert.match(js, /cameraWrap\.hidden = true/);
    assert.match(js, /cameraEmpty\.hidden = true/);
    assert.match(js, /showCapturedThumbnails\(captured, captured, true\)/);
    assert.match(js, /completeButton\.disabled = !canSaveCurrentBatch\(\)/);
    assert.match(js, /Kết quả vẫn là CHECK_UNAVAILABLE, không phải CLEAR/);
});

test('local demo save requires the exact uncalibrated reason and an explicit confirmation', () => {
    const js = read('public/js/face_enrollment.js');
    assert.match(js, /check\?\.reason === 'THRESHOLD_NOT_CALIBRATED'/);
    assert.match(js, /window\.confirm\(/);
    assert.match(js, /confirm_demo_unverified: '1'/);
    assert.doesNotMatch(js, /CALIBRATION_REPORT_MISSING'[\s\S]{0,100}demoReasonAllowed/);
});
