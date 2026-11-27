const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const projectRoot = path.resolve(__dirname, '..');

function loadStartHelper() {
    const window = { setTimeout: (callback) => { callback(); return 1; } };
    const source = fs.readFileSync(path.join(projectRoot, 'public/js/kiosk_ai_start.js'), 'utf8');
    vm.runInNewContext(source, { window, URLSearchParams, TypeError, Number });
    return window.KioskAiStart;
}

test('recognition start retries only explicit preparation responses and then starts once', async () => {
    const helper = loadStartHelper();
    const responseCodes = ['AI1_PREPARING', 'AI1_PREPARING', null];
    const delays = [];
    const progress = [];
    let calls = 0;
    const result = await helper.startRecognition({
        csrfToken: 'csrf-test',
        delayMs: 350,
        fetchImpl: async (_url, options) => {
            calls += 1;
            assert.equal(options.method, 'POST');
            assert.equal(new URLSearchParams(options.body).get('_csrf_token'), 'csrf-test');
            return { attempt: calls };
        },
        readJson: async (response) => {
            const code = responseCodes[response.attempt - 1];
            return code
                ? { success: false, code }
                : { success: true, session_id: 'a'.repeat(32) };
        },
        onPreparing: (attempt, total) => progress.push([attempt, total]),
        waitImpl: async (milliseconds) => delays.push(milliseconds),
    });

    assert.equal(result.payload.success, true);
    assert.equal(calls, 3);
    assert.deepEqual(delays, [350, 700]);
    assert.deepEqual(progress, [[1, 3], [2, 3]]);
});

test('busy and offline responses are returned immediately without duplicate starts', async () => {
    const helper = loadStartHelper();
    for (const code of ['AI1_BUSY', 'AI1_UNAVAILABLE', 'AI1_GALLERY_UNAVAILABLE']) {
        let calls = 0;
        const result = await helper.startRecognition({
            fetchImpl: async () => { calls += 1; return {}; },
            readJson: async () => ({ success: false, code }),
            waitImpl: async () => assert.fail('unexpected retry'),
        });
        assert.equal(result.payload.code, code);
        assert.equal(calls, 1);
    }
});

test('preparation retry count is bounded and never creates a recognition session', async () => {
    const helper = loadStartHelper();
    let calls = 0;
    await assert.rejects(helper.startRecognition({
        fetchImpl: async () => { calls += 1; return {}; },
        readJson: async () => ({ success: false, code: 'AI1_PREPARING' }),
        waitImpl: async () => {},
    }), /AI1_PREPARING/);
    assert.equal(calls, helper.DEFAULT_MAX_ATTEMPTS);
});
