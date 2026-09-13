document.addEventListener("DOMContentLoaded", () => {
    const modeButtons = document.querySelectorAll(".mode-toggle button");
    const urlLabel = document.getElementById("url-label");
    const urlPlaceholder = document.getElementById("url-input");
    const scrapeBtn = document.getElementById("scrape-btn");
    const progressContainer = document.getElementById("progress-container");
    const progressFill = document.getElementById("progress-fill");
    const progressText = document.getElementById("progress-text");
    const statusMessage = document.getElementById("status-message");
    const resultsSection = document.getElementById("results-section");
    const resultsContainer = document.getElementById("results-container");

    let currentMode = "urls";

    // ── Mode Toggle ────────────────────────────────────
    modeButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            modeButtons.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            currentMode = btn.dataset.mode;

            if (currentMode === "sitemap") {
                urlLabel.textContent = "Sitemap URL";
                urlPlaceholder.placeholder = "https://example.com/sitemap.xml";
                urlPlaceholder.rows = 1;
            } else {
                urlLabel.textContent = "URLs (one per line)";
                urlPlaceholder.placeholder = "https://example.com/page1\nhttps://example.com/page2";
                urlPlaceholder.rows = 6;
            }
        });
    });

    // ── Scrape ─────────────────────────────────────────
    scrapeBtn.addEventListener("click", () => {
        const rawInput = urlPlaceholder.value.trim();
        const limit = parseInt(document.getElementById("limit-input").value) || 0;

        if (!rawInput) {
            showStatus("Please enter at least one URL.", "error");
            return;
        }

        const urls = rawInput
            .split("\n")
            .map((u) => u.trim())
            .filter((u) => u.length > 0);

        if (urls.length === 0) {
            showStatus("No valid URLs found.", "error");
            return;
        }

        startScrape({ urls, sitemap: currentMode === "sitemap", limit });
    });

    // ── Start Scrape (SSE) ─────────────────────────────
    function startScrape(payload) {
        // Reset UI
        scrapeBtn.disabled = true;
        scrapeBtn.textContent = "⏳ Scraping...";
        resultsContainer.innerHTML = "";
        resultsSection.style.display = "none";
        hideStatus();
        showProgress(0, 1, "Starting...");

        fetch("/scrape", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        }).then((response) => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            function read() {
                reader.read().then(({ done, value }) => {
                    if (done) {
                        scrapeBtn.disabled = false;
                        scrapeBtn.textContent = "🚀 Start Scraping";
                        return;
                    }

                    buffer += decoder.decode(value, { stream: true });

                    // Parse SSE events from buffer
                    const lines = buffer.split("\n");
                    buffer = lines.pop(); // Keep incomplete line in buffer

                    let dataLine = "";
                    for (const line of lines) {
                        if (line.startsWith("data: ")) {
                            dataLine = line.slice(6);
                            try {
                                const event = JSON.parse(dataLine);
                                handleEvent(event);
                            } catch {
                                // Incomplete JSON, skip
                            }
                        }
                    }

                    read();
                });
            }

            read();
        }).catch((err) => {
            showStatus(`Connection error: ${err.message}`, "error");
            scrapeBtn.disabled = false;
            scrapeBtn.textContent = "🚀 Start Scraping";
        });
    }

    // ── Handle SSE Events ──────────────────────────────
    function handleEvent(event) {
        switch (event.type) {
            case "progress":
                showProgress(event.current, event.total, `Scraping (${event.current}/${event.total}): ${truncateUrl(event.url)}`);
                break;

            case "result":
                resultsSection.style.display = "block";
                appendCard(event.data);
                break;

            case "info":
                showStatus(event.message, "info");
                break;

            case "error":
                showStatus(event.message, "error");
                scrapeBtn.disabled = false;
                scrapeBtn.textContent = "🚀 Start Scraping";
                break;

            case "done":
                showProgress(event.total, event.total, "Complete!");
                showStatus(
                    `✅ Done! Scraped ${event.successful}/${event.total} URLs in ${event.response_time}s` +
                    (event.failed > 0 ? ` (${event.failed} failed)` : ""),
                    event.failed > 0 ? "info" : "success"
                );
                scrapeBtn.disabled = false;
                scrapeBtn.textContent = "🚀 Start Scraping";
                break;
        }
    }

    // ── Create Result Card ─────────────────────────────
    function appendCard(data) {
        const card = document.createElement("div");
        card.className = "card" + (data.error ? " error-card" : "");

        if (data.error) {
            card.innerHTML = `
                <div class="card-body">
                    <div class="card-title">❌ Error</div>
                    <div class="card-meta"><a href="${escapeHtml(data.url)}" target="_blank">${escapeHtml(data.url)}</a></div>
                    <div class="card-description" style="color: var(--error);">${escapeHtml(data.error)}</div>
                </div>
            `;
        } else {
            const contentId = "content-" + Math.random().toString(36).slice(2);
            const hasImage = data.image && data.image.startsWith("http");
            card.innerHTML = `
                ${hasImage ? `<div class="card-image"><img src="${escapeHtml(data.image)}" alt="${escapeHtml(data.title)}" onerror="this.parentElement.remove()"></div>` : ""}
                <div class="card-body">
                    <div class="card-title">${escapeHtml(data.title || "Untitled")}</div>
                    <div class="card-meta">
                        ${data.sitename ? escapeHtml(data.sitename) : ""}
                        ${data.date ? "&nbsp;·&nbsp;" + escapeHtml(data.date) : ""}
                        ${data.word_count ? "&nbsp;·&nbsp;" + data.word_count + " words" : ""}
                    </div>
                    ${data.description ? `<div class="card-description">${escapeHtml(data.description)}</div>` : ""}
                    <div class="card-actions">
                        <a href="${escapeHtml(data.url)}" target="_blank" class="card-link">Read more →</a>
                        <button class="card-toggle" onclick="toggleContent('${contentId}', this)">
                            <span class="arrow">▶</span> View Scraped Content
                        </button>
                    </div>
                    <div class="card-content" id="${contentId}">
                        <div class="markdown-body">${renderMarkdown(data.content || "")}</div>
                    </div>
                </div>
            `;
        }

        resultsContainer.appendChild(card);
        card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // ── Make toggleContent global ──────────────────────
    window.toggleContent = function (id, btn) {
        const el = document.getElementById(id);
        if (!el) return;
        const isVisible = el.classList.toggle("visible");
        btn.classList.toggle("open", isVisible);
        btn.querySelector(".arrow").textContent = isVisible ? "▼" : "▶";

        // Highlight code blocks on first open
        if (isVisible) {
            el.querySelectorAll("pre code").forEach((block) => {
                if (!block.dataset.highlighted) {
                    hljs.highlightElement(block);
                    block.dataset.highlighted = "true";
                }
            });
        }
    };

    // ── Helpers ────────────────────────────────────────
    function renderMarkdown(text) {
        if (typeof marked !== "undefined") {
            return marked.parse(text);
        }
        // Fallback: just wrap in <pre>
        return `<pre>${escapeHtml(text)}</pre>`;
    }

    function showProgress(current, total, text) {
        progressContainer.classList.add("visible");
        const pct = total > 0 ? Math.round((current / total) * 100) : 0;
        progressFill.style.width = pct + "%";
        progressText.textContent = text;
    }

    function showStatus(msg, type) {
        statusMessage.textContent = msg;
        statusMessage.className = "status-message visible " + type;
    }

    function hideStatus() {
        statusMessage.className = "status-message";
    }

    function truncateUrl(url) {
        return url.length > 60 ? url.slice(0, 57) + "..." : url;
    }

    function escapeHtml(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
});
