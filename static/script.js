const tabs = document.querySelectorAll(".tab");
const urlInput = document.getElementById("urlInput");
const urlLabel = document.getElementById("urlLabel");
const limit = document.getElementById("limit");
const scrapeBtn = document.getElementById("scrapeBtn");
const scrapeText = document.getElementById("scrapeText");
const outputText = document.getElementById("outputText");
const resultState = document.getElementById("resultState");
const stats = document.getElementById("stats");
const sourceStatus = document.getElementById("sourceStatus");
const copyBtn = document.getElementById("copyBtn");
const downloadBtn = document.getElementById("downloadBtn");
const cardsContainer = document.getElementById("cardsContainer");

/* --------------------------------
   Limit Scrubbing
--------------------------------- */
let isDraggingLimit = false;
let startX = 0;
let startLimit = 0;
let limitHasDragged = false;

limit.style.cursor = "ew-resize";

limit.addEventListener("mousedown", (e) => {
  isDraggingLimit = true;
  limitHasDragged = false;
  startX = e.clientX;
  startLimit = parseInt(limit.value, 10) || 0;
});

window.addEventListener("mousemove", (e) => {
  if (!isDraggingLimit) return;
  const dx = e.clientX - startX;
  if (Math.abs(dx) > 2) {
    limitHasDragged = true;
    let newValue = startLimit + Math.floor(dx / 5);
    if (newValue < 0) newValue = 0;
    limit.value = newValue;
    window.getSelection().removeAllRanges();
  }
});

window.addEventListener("mouseup", (e) => {
  if (isDraggingLimit) {
    isDraggingLimit = false;
    if (limitHasDragged) {
      // Prevent focus or click if we were dragging
      e.preventDefault();
    }
  }
});

let mode = "urls";

function escapeHTML(str) {
  if (!str) return "";
  return str.replace(/[&<>'"]/g, 
    tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag)
  );
}

/* --------------------------------
   Source mode tabs
--------------------------------- */

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");

    mode = tab.dataset.mode;

    if (mode === "sitemap") {
      urlLabel.innerHTML = `
        SITEMAP
        <span>XML sitemap URL</span>
      `;

      urlInput.placeholder = "https://example.com/sitemap.xml";
    } else {
      urlLabel.innerHTML = `
        URLs
        <span>one per line</span>
      `;

      urlInput.placeholder = `https://example.com
https://example.com/docs
https://example.com/blog`;
    }
  });
});

/* --------------------------------
   Helpers
--------------------------------- */

function getUrls() {
  return urlInput.value
    .split(/\n+/)
    .map((url) => url.trim())
    .filter(Boolean);
}

function setOutput(markdown, state = "Complete") {
  outputText.textContent = markdown;
  resultState.textContent = state;

  const cleaned = markdown.trim();

  const words = cleaned ? cleaned.split(/\s+/).length : 0;

  stats.textContent =
    `${words.toLocaleString()} words · ` +
    `${markdown.length.toLocaleString()} chars`;
}

function setScrapingState(isLoading) {
  scrapeBtn.classList.toggle("loading", isLoading);

  sourceStatus.textContent = isLoading ? "RUNNING" : "READY";

  sourceStatus.className = isLoading ? "status-pill running" : "status-pill";

  scrapeText.textContent = isLoading ? "Scraping…" : "Start scraping";
}

/* --------------------------------
   Scraping
--------------------------------- */

async function scrape() {
  const input = urlInput.value.trim();

  if (!input) {
    resultState.textContent = "Add at least one URL";
    urlInput.focus();
    return;
  }

  setScrapingState(true);

  resultState.textContent =
    mode === "sitemap" ? "Fetching sitemap…" : "Fetching and cleaning content…";
    
  cardsContainer.innerHTML = '';

  try {
    const urls = mode === "sitemap" ? [input] : getUrls();

    const response = await fetch("/scrape", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        urls: urls,
        limit: Number(limit.value) || 0,
        sitemap: mode === "sitemap",
        response_format: "sse",
      }),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.error || "Failed to scrape");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");

    let done = false;
    let markdownOutput = "";
    let buffer = "";

    while (!done) {
      const { value, done: readerDone } = await reader.read();
      done = readerDone;
      if (value) {
        buffer += decoder.decode(value, { stream: true });

        let match = buffer.match(/\r?\n\r?\n/);
        while (match) {
          const boundaryLength = match[0].length;
          const boundaryIndex = match.index;
          const message = buffer.slice(0, boundaryIndex);
          buffer = buffer.slice(boundaryIndex + boundaryLength);

          const lines = message.split(/\r?\n/);
          let dataStr = "";
          for (const line of lines) {
            if (line.startsWith("data:")) {
              dataStr = line.substring(5).trim();
              break;
            }
          }

          if (dataStr) {
            try {
              const payload = JSON.parse(dataStr);
              if (payload.type === "progress") {
                resultState.textContent = `Scraping ${payload.current} / ${payload.total}...`;
              } else if (payload.type === "result") {
                let preContent = '';
                let title = payload.data.title || payload.data.url;
                
                if (payload.data.error) {
                  preContent = `Failed to scrape ${payload.data.url}:\n${payload.data.error}`;
                  markdownOutput += `Failed to scrape ${payload.data.url}: ${payload.data.error}\n\n---\n\n`;
                } else {
                  preContent = `# ${payload.data.title}\n\nSource: ${payload.data.url}\n\n${payload.data.content}`;
                  markdownOutput += `# ${payload.data.title}\n\nSource: ${payload.data.url}\n\n${payload.data.content}\n\n---\n\n`;
                }
                
                let innerContent = '';
                if (payload.data.error) {
                    innerContent = `
                      <div class="window-bar">
                        <div class="window-dots"><i></i><i></i><i></i></div>
                        <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 80%;">${escapeHTML(title)}.md</span>
                      </div>
                      <div class="card-snippet" style="padding: 18px; flex: 1; font-size: 13px; color: #ff6b6b; line-height: 1.6;">${escapeHTML(payload.data.error)}</div>
                    `;
                } else {
                    const { url, image, author, date, description, content } = payload.data;
                    const snippet = description || (content ? content.substring(0, 150) + '...' : 'No preview available.');
                    const imgHTML = image ? `<div class="card-img" style="height: 110px; background-image: url('${escapeHTML(image)}'); background-size: cover; background-position: center; border-bottom: 1px solid var(--line-soft);"></div>` : '';
                    
                    const metaArr = [];
                    if (date) metaArr.push(escapeHTML(date));
                    if (author) metaArr.push(`By ${escapeHTML(author)}`);
                    const metaHTML = metaArr.length ? `<div style="font-size: 10px; color: #888; margin-bottom: 8px;">${metaArr.join(' • ')}</div>` : '';

                    innerContent = `
                      ${imgHTML}
                      <div style="padding: 14px; display: flex; flex-direction: column; flex: 1; background: #0c0c0c;">
                         <h3 style="margin: 0 0 6px 0; font-size: 14px; color: #fff; line-height: 1.3;">${escapeHTML(title)}</h3>
                         ${metaHTML}
                         <div style="font-size: 12px; color: #b0b0b0; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; flex: 1; margin-bottom: 12px;">${escapeHTML(snippet)}</div>
                         
                         <div style="display: flex; justify-content: space-between; align-items: center; margin-top: auto; border-top: 1px solid var(--line-soft); padding-top: 10px;">
                            <a href="${escapeHTML(url)}" target="_blank" rel="noopener noreferrer" style="font-size: 11px; color: #4da6ff; text-decoration: none; font-weight: 500;" onclick="event.stopPropagation();">Read original ↗</a>
                            <span style="font-size: 11px; color: #888; background: #222; padding: 4px 8px; border-radius: 4px;">View Markdown</span>
                         </div>
                      </div>
                    `;
                }

                const card = document.createElement('div');
                card.className = 'code-window interactive-card';
                card.style.display = 'flex';
                card.style.flexDirection = 'column';
                card.style.cursor = 'pointer';
                card.style.transition = 'transform 0.15s, border-color 0.15s';
                card.innerHTML = innerContent;
                
                card.addEventListener('click', () => openModal(title, preContent));
                card.addEventListener('mouseenter', () => {
                   card.style.transform = 'translateY(-2px)';
                   card.style.borderColor = '#444';
                });
                card.addEventListener('mouseleave', () => {
                   card.style.transform = 'none';
                   card.style.borderColor = 'var(--line)';
                });
                
                cardsContainer.appendChild(card);

                setOutput(markdownOutput.trim(), resultState.textContent);
              } else if (payload.type === "done") {
                resultState.textContent =
                  mode === "sitemap"
                    ? "Sitemap scrape complete"
                    : "Scrape complete";
                sourceStatus.textContent = "DONE";
                sourceStatus.className = "status-pill success";
                scrapeText.textContent = "Scrape again";
              } else if (payload.type === "error") {
                throw new Error(payload.message);
              }
            } catch (e) {
              if (
                e.message !== "Unexpected end of JSON input" &&
                !e.message.includes("Unexpected token")
              ) {
                throw e;
              }
            }
          }

          match = buffer.match(/\r?\n\r?\n/);
        }
      }
    }
  } catch (error) {
    console.error("Scrape failed:", error);

    resultState.textContent = error?.message || "Something went wrong";

    sourceStatus.textContent = "ERROR";
    sourceStatus.className = "status-pill running";
  } finally {
    scrapeBtn.classList.remove("loading");
  }
}

/* --------------------------------
   Scrape button
--------------------------------- */

scrapeBtn.addEventListener("click", scrape);

/* --------------------------------
   Copy Markdown
--------------------------------- */

copyBtn.addEventListener("click", async () => {
  const value = outputText.textContent.trim();

  if (!value) {
    return;
  }

  try {
    await navigator.clipboard.writeText(value);

    const originalText = copyBtn.textContent;

    copyBtn.textContent = "Copied";

    setTimeout(() => {
      copyBtn.textContent = originalText;
    }, 1200);
  } catch (error) {
    console.error("Copy failed:", error);

    copyBtn.textContent = "Copy failed";

    setTimeout(() => {
      copyBtn.textContent = "Copy";
    }, 1200);
  }
});

/* --------------------------------
   Download Markdown
--------------------------------- */

downloadBtn.addEventListener("click", () => {
  const value = outputText.textContent.trim();

  if (!value) {
    return;
  }

  const blob = new Blob([value], {
    type: "text/markdown;charset=utf-8",
  });

  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");

  link.href = url;
  link.download = "scraped-content.md";

  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(url);
});

/* --------------------------------
   GitHub button
--------------------------------- */

const githubBtn = document.getElementById("githubBtn");

if (githubBtn) {
  githubBtn.addEventListener("click", () => {
    window.open(
      "https://github.com/SouravKAgarwal/web-scraper",
      "_blank",
      "noopener,noreferrer",
    );
  });
}

/* --------------------------------
   Keyboard shortcut

   Ctrl/Cmd + Enter → Scrape
--------------------------------- */

urlInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    scrape();
  }
});

/* --------------------------------
   Modal Logic
--------------------------------- */

const modal = document.getElementById("previewModal");
const modalTitle = document.getElementById("modalTitle");
const modalMarkdownContent = document.getElementById("modalMarkdownContent");
const modalHtmlPreview = document.getElementById("modalHtmlPreview");
const modalCloseBtn = document.getElementById("modalCloseBtn");
const modalCopyBtn = document.getElementById("modalCopyBtn");
const modalDownloadBtn = document.getElementById("modalDownloadBtn");

let currentModalTitle = "";
let currentModalMarkdown = "";
let isSyncingLeft = false;
let isSyncingRight = false;

if (modalMarkdownContent && modalHtmlPreview) {
  modalMarkdownContent.addEventListener('scroll', function(e) {
    if (!isSyncingLeft) {
      isSyncingRight = true;
      const percentage = this.scrollTop / (this.scrollHeight - this.clientHeight);
      modalHtmlPreview.scrollTop = percentage * (modalHtmlPreview.scrollHeight - modalHtmlPreview.clientHeight);
    }
    isSyncingLeft = false;
  });

  modalHtmlPreview.addEventListener('scroll', function(e) {
    if (!isSyncingRight) {
      isSyncingLeft = true;
      const percentage = this.scrollTop / (this.scrollHeight - this.clientHeight);
      modalMarkdownContent.scrollTop = percentage * (modalMarkdownContent.scrollHeight - modalMarkdownContent.clientHeight);
    }
    isSyncingRight = false;
  });
}

function openModal(title, markdown) {
  currentModalTitle = title;
  currentModalMarkdown = markdown;

  modalTitle.textContent = title + ".md";
  modalMarkdownContent.textContent = markdown;
  
  if (typeof marked !== 'undefined') {
    modalHtmlPreview.innerHTML = marked.parse(markdown);
  } else {
    modalHtmlPreview.textContent = "Preview not available.";
  }

  modal.showModal();
}

if (modalCloseBtn) {
  modalCloseBtn.addEventListener("click", () => {
    modal.close();
  });
}

if (modal) {
  modal.addEventListener("click", (e) => {
    const dialogDimensions = modal.getBoundingClientRect();
    if (
      e.clientX < dialogDimensions.left ||
      e.clientX > dialogDimensions.right ||
      e.clientY < dialogDimensions.top ||
      e.clientY > dialogDimensions.bottom
    ) {
      modal.close();
    }
  });
}

if (modalCopyBtn) {
  modalCopyBtn.addEventListener("click", async () => {
    if (!currentModalMarkdown) return;
    try {
      await navigator.clipboard.writeText(currentModalMarkdown);
      const originalText = modalCopyBtn.textContent;
      modalCopyBtn.textContent = "Copied";
      setTimeout(() => {
        modalCopyBtn.textContent = originalText;
      }, 1200);
    } catch (error) {
      console.error("Copy failed:", error);
    }
  });
}

if (modalDownloadBtn) {
  modalDownloadBtn.addEventListener("click", () => {
    if (!currentModalMarkdown) return;
    const blob = new Blob([currentModalMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = (currentModalTitle || "scraped-content") + ".md";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  });
}
