(() => {
    const chatMain = document.querySelector(".chat-main[data-generate-url]");
    if (!chatMain) {
        initConfirmForms();
        return;
    }

    const form = document.getElementById("prompt-form");
    const prompt = document.getElementById("prompt-input");
    const files = document.getElementById("file-input");
    const send = document.getElementById("send-button");
    const list = document.getElementById("message-list");
    const scroller = document.getElementById("chat-scroller");
    const error = document.getElementById("composer-error");
    const picker = document.getElementById("model-picker");
    const effortPicker = document.getElementById("thinking-effort");
    const effortStatus = document.getElementById("thinking-effort-status");
    const costHint = document.getElementById("cost-hint");
    const executionLabel = chatMain.dataset.providerMode === "litechat" ? "LITECHAT" : "MOCK";
    let retryRequestId = null;
    let retrySignature = null;

    document.querySelectorAll("[data-prompt]").forEach((button) => {
        button.addEventListener("click", () => {
            prompt.value = button.dataset.prompt || "";
            prompt.focus();
        });
    });

    picker.addEventListener("change", () => {
        const option = picker.selectedOptions[0];
        const cost = Number(option.dataset.cost || 0);
        costHint.textContent = `${cost} ${cost === 1 ? "credit" : "credits"} per response`;
        updateThinkingEffortState();
    });

    effortPicker.addEventListener("change", updateThinkingEffortState);
    updateThinkingEffortState();

    function updateThinkingEffortState() {
        const supported = chatMain.dataset.providerMode === "litechat"
            && picker.selectedOptions[0].dataset.thinkingEffort === "true";
        effortPicker.disabled = !supported;
        if (!supported) {
            effortStatus.textContent = chatMain.dataset.providerMode === "litechat"
                ? "Thinking effort: Not supported"
                : "Thinking effort: Mock mode";
            return;
        }
        const effort = effortPicker.value;
        effortStatus.textContent = `Thinking effort: ${effort[0].toUpperCase()}${effort.slice(1)}`;
    }

    files.addEventListener("change", () => {
        const target = document.getElementById("selected-files");
        target.textContent = Array.from(files.files).map((file) => file.name).join(", ");
    });

    prompt.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const text = prompt.value.trim();
        if (!text || send.disabled) return;

        error.textContent = "";
        send.disabled = true;
        send.classList.add("sending");
        form.setAttribute("aria-busy", "true");
        const signature = JSON.stringify([
            text,
            picker.value,
            effortPicker.value,
            Array.from(files.files).map((file) => [file.name, file.size, file.lastModified]),
        ]);
        if (!retryRequestId || retrySignature !== signature) {
            retryRequestId = crypto.randomUUID();
            retrySignature = signature;
        }
        const data = new FormData(form);
        data.set("request_id", retryRequestId);
        data.set("model_key", picker.value);
        data.set("thinking_effort", effortPicker.value || "medium");
        appendUserMessage(text, Array.from(files.files).map((file) => file.name));
        appendPendingMessage();
        scrollToBottom();

        try {
            const response = await fetch(chatMain.dataset.generateUrl, {
                method: "POST",
                body: data,
                headers: { "X-Requested-With": "XMLHttpRequest" },
            });
            retryRequestId = null;
            retrySignature = null;
            const result = await response.json();
            removePendingMessage();
            if (!response.ok || !result.ok) {
                throw new Error(result.error || "The response could not be created.");
            }
            appendAssistantMessage(result.message);
            updateBalances(result.balance);
            prompt.value = "";
            files.value = "";
            document.getElementById("selected-files").textContent = "";
            const title = document.querySelector(".chat-title-area h1");
            if (title && title.textContent === "New conversation") title.textContent = text.slice(0, 54);
        } catch (requestError) {
            removePendingMessage();
            error.textContent = requestError.message;
        } finally {
            send.disabled = false;
            send.classList.remove("sending");
            form.removeAttribute("aria-busy");
            prompt.focus();
            scrollToBottom();
        }
    });

    function appendUserMessage(text, attachmentNames) {
        const row = document.createElement("article");
        row.className = "message-row user";
        const avatar = document.createElement("div");
        avatar.className = "message-avatar";
        avatar.textContent = chatMain.dataset.userInitial || "Y";
        const body = document.createElement("div");
        body.className = "message-body";
        const meta = document.createElement("div");
        meta.className = "message-meta";
        const name = document.createElement("strong");
        name.textContent = "You";
        meta.append(name);
        const content = document.createElement("div");
        content.className = "message-content";
        content.textContent = text;
        body.append(meta, content);
        if (attachmentNames.length) {
            const attachmentList = document.createElement("div");
            attachmentList.className = "attachment-list";
            attachmentNames.forEach((filename) => {
                const chip = document.createElement("span");
                chip.className = "attachment-chip";
                chip.textContent = `↧ ${filename}`;
                attachmentList.append(chip);
            });
            body.append(attachmentList);
        }
        row.append(avatar, body);
        list.append(row);
    }

    function appendPendingMessage() {
        const row = document.createElement("article");
        row.id = "pending-message";
        row.className = "message-row assistant pending-row";
        row.innerHTML = `<div class="message-avatar assistant-avatar">L</div><div class="message-body"><div class="message-meta"><strong>LightChat</strong><span class="mock-tag">${executionLabel}</span></div><div class="typing-dots"><i></i><i></i><i></i><span>Thinking through your prompt</span></div></div>`;
        list.append(row);
    }

    function removePendingMessage() {
        document.getElementById("pending-message")?.remove();
    }

    function appendAssistantMessage(message) {
        const row = document.createElement("article");
        row.className = "message-row assistant";
        row.dataset.messageId = message.id;
        const avatar = document.createElement("div");
        avatar.className = "message-avatar assistant-avatar";
        avatar.textContent = "L";
        const body = document.createElement("div");
        body.className = "message-body";
        const meta = document.createElement("div");
        meta.className = "message-meta";
        const name = document.createElement("strong");
        name.textContent = "LightChat";
        const tag = document.createElement("span");
        tag.className = "mock-tag";
        tag.textContent = (message.execution_mode || "mock").toUpperCase();
        const provider = document.createElement("span");
        provider.textContent = `${message.provider} target`;
        meta.append(name, tag, provider);
        const content = document.createElement("div");
        content.className = "message-content";
        content.textContent = message.content;
        const feedback = document.createElement("div");
        feedback.className = "feedback-row";
        const csrf = form.querySelector('input[name="csrfmiddlewaretoken"]')?.value || "";
        [["up", "↑ Helpful"], ["down", "↓ Not helpful"]].forEach(([rating, label]) => {
            const feedbackForm = document.createElement("form");
            feedbackForm.method = "post";
            feedbackForm.action = message.feedback_url;
            const csrfInput = document.createElement("input");
            csrfInput.type = "hidden";
            csrfInput.name = "csrfmiddlewaretoken";
            csrfInput.value = csrf;
            const ratingInput = document.createElement("input");
            ratingInput.type = "hidden";
            ratingInput.name = "rating";
            ratingInput.value = rating;
            const button = document.createElement("button");
            button.className = "feedback-button";
            button.type = "submit";
            button.textContent = label;
            feedbackForm.append(csrfInput, ratingInput, button);
            feedback.append(feedbackForm);
        });
        body.append(meta, content, feedback);
        row.append(avatar, body);
        list.append(row);
    }

    function updateBalances(balance) {
        document.querySelectorAll("[data-credit-balance]").forEach((node) => {
            node.textContent = balance;
        });
    }

    function scrollToBottom() {
        scroller.scrollTop = scroller.scrollHeight;
    }

    scrollToBottom();
    initConfirmForms();

    function initConfirmForms() {
        document.querySelectorAll("form[data-confirm]").forEach((confirmForm) => {
            confirmForm.addEventListener("submit", (event) => {
                if (!window.confirm(confirmForm.dataset.confirm)) event.preventDefault();
            });
        });
    }
})();
