(() => {
    const DISPLAY_MS = 2000;

    const mount = ({ overlay, card, title, greeting, message, onHidden }) => {
        let timer = null;
        let generation = 0;

        const clearTimer = () => {
            if (timer !== null) window.clearTimeout(timer);
            timer = null;
        };

        const clearContent = () => {
            title.textContent = '';
            greeting.textContent = '';
            greeting.hidden = true;
            message.textContent = '';
            message.hidden = true;
            card.dataset.state = 'idle';
        };

        const hide = () => {
            generation += 1;
            clearTimer();
            overlay.hidden = true;
            clearContent();
        };

        const show = ({ state, titleText, greetingText = '', messageText = '' }) => {
            clearTimer();
            const currentGeneration = ++generation;
            card.dataset.state = state || 'idle';
            title.textContent = titleText || '';
            greeting.textContent = greetingText;
            greeting.hidden = !greetingText;
            message.textContent = messageText;
            message.hidden = !messageText;
            overlay.hidden = false;

            timer = window.setTimeout(() => {
                if (currentGeneration !== generation) return;
                timer = null;
                overlay.hidden = true;
                clearContent();
                if (typeof onHidden === 'function') onHidden();
            }, DISPLAY_MS);
        };

        return { show, hide, displayMs: DISPLAY_MS };
    };

    window.KioskResultOverlay = { mount, DISPLAY_MS };
})();
