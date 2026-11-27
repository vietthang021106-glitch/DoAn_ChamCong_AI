const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const projectRoot = path.resolve(__dirname, '..');

function fakeNode() {
    return { hidden: true, textContent: '', dataset: {} };
}

function loadOverlay() {
    let now = 0;
    let nextTimerId = 1;
    const timers = new Map();
    const window = {
        setTimeout(callback, delay) {
            const id = nextTimerId++;
            timers.set(id, { callback, at: now + delay });
            return id;
        },
        clearTimeout(id) { timers.delete(id); },
    };
    const source = fs.readFileSync(path.join(projectRoot, 'public/js/kiosk_result_overlay.js'), 'utf8');
    vm.runInNewContext(source, { window });

    const elements = {
        overlay: fakeNode(), card: fakeNode(), title: fakeNode(),
        greeting: fakeNode(), message: fakeNode(),
    };
    const advance = (milliseconds) => {
        const target = now + milliseconds;
        while (true) {
            const due = [...timers.entries()]
                .filter(([, timer]) => timer.at <= target)
                .sort((left, right) => left[1].at - right[1].at)[0];
            if (!due) break;
            const [id, timer] = due;
            timers.delete(id);
            now = timer.at;
            timer.callback();
        }
        now = target;
    };
    return { api: window.KioskResultOverlay, elements, advance };
}

test('result card stays for exactly 2000 ms and clears employee text after hiding', () => {
    const { api, elements, advance } = loadOverlay();
    let hiddenCount = 0;
    const ui = api.mount({ ...elements, onHidden: () => { hiddenCount += 1; } });

    ui.show({
        state: 'success', titleText: 'CHẤM CÔNG THÀNH CÔNG',
        greetingText: 'Chào mừng, Nguyễn Văn A!', messageText: 'Đã ghi nhận giờ vào.',
    });
    assert.equal(api.DISPLAY_MS, 2000);
    assert.equal(elements.overlay.hidden, false);
    advance(1999);
    assert.equal(elements.overlay.hidden, false);
    advance(1);
    assert.equal(elements.overlay.hidden, true);
    assert.equal(elements.greeting.textContent, '');
    assert.equal(hiddenCount, 1);
});

test('a newer result cancels the prior hide timer and replaces all old content safely', () => {
    const { api, elements, advance } = loadOverlay();
    let hiddenCount = 0;
    const ui = api.mount({ ...elements, onHidden: () => { hiddenCount += 1; } });

    ui.show({ state: 'success', titleText: 'OK', greetingText: 'Chào mừng, Nhân viên cũ!', messageText: 'Đã ghi nhận.' });
    advance(1500);
    ui.show({ state: 'error', titleText: 'CHƯA THỂ CHẤM CÔNG', greetingText: 'Xin chào, <script>alert(1)</script>!', messageText: 'Chưa được phân ca.' });
    assert.equal(elements.card.dataset.state, 'error');
    assert.equal(elements.greeting.textContent, 'Xin chào, <script>alert(1)</script>!');
    advance(500);
    assert.equal(elements.overlay.hidden, false, 'old timer must not hide the newer card');
    advance(1499);
    assert.equal(elements.overlay.hidden, false);
    advance(1);
    assert.equal(elements.overlay.hidden, true);
    assert.equal(hiddenCount, 1, 'only the newest result completes its timer');

    ui.show({ state: 'unknown', titleText: 'UNKNOWN', messageText: 'Không nhận diện được.' });
    assert.equal(elements.greeting.hidden, true);
    assert.equal(elements.greeting.textContent, '');
});

test('kiosk result presentation leaves the live preview running and does not rescan on hide', () => {
    const source = fs.readFileSync(path.join(projectRoot, 'public/js/man_hinh_cham_cong.js'), 'utf8');
    const styles = fs.readFileSync(path.join(projectRoot, 'public/css/man_hinh_cham_cong.css'), 'utf8');
    const finishStart = source.indexOf('const finish =');
    const finishEnd = source.indexOf('const readJson =', finishStart);
    const finish = source.slice(finishStart, finishEnd);
    assert.match(finish, /resultUi\?\.show/);
    assert.doesNotMatch(finish, /stopPreview\s*\(/);
    assert.doesNotMatch(finish, /recordAttendance\s*\(/);
    assert.match(source, /payload\.employee_name/);
    assert.doesNotMatch(source, /presentAttendance\(payload,\s*recognitionResult\)/);
    assert.match(source, /await recordAttendance\(start\.session_id\)/);
    assert.match(styles, /\.terminal-result-overlay\s*\{[^}]*place-items:\s*center/s);
    assert.match(styles, /\.terminal-result-overlay\[hidden\]\s*\{\s*display:\s*none/s);
});
