class GWiki {
  constructor() {
    this.currentPage = null;
    this.chatOpen = false;
    this.init();
  }

  init() {
    this.bindEvents();
    this.loadInitialPage();
  }

  bindEvents() {
    // Handle browser back/forward
    window.addEventListener("popstate", (e) => {
      this.loadPageFromUrl();
    });

    // Search functionality
    document.getElementById("search-btn").addEventListener("click", () => {
      this.handleSearch();
    });

    document.getElementById("wiki-search").addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        this.handleSearch();
      }
    });

    // Chat toggle
    document.getElementById("chat-toggle").addEventListener("click", (e) => {
      e.preventDefault();
      this.toggleChat();
    });

    document.getElementById("chat-close").addEventListener("click", () => {
      this.toggleChat();
    });

    document.getElementById("chat-send").addEventListener("click", () => {
      this.sendChatMessage();
    });

    document.getElementById("chat-input").addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        this.sendChatMessage();
      }
    });
  }

  // Helper: don't force lowercase; Wikipedia-ish behavior is case-sensitive on first char.
  // Keep your format rules simple first; you can get fancy later.
  pageToCleanUrl(pagePath) {
    // "Germany.html" -> "Germany"
    return pagePath.replace(/\.html$/i, "");
  }

  cleanUrlToPage(cleanUrl) {
    // "germany" -> "Germany.html"
    if (!cleanUrl) return null;
    return cleanUrl.charAt(0).toUpperCase() + cleanUrl.slice(1) + ".html";
  }

  loadInitialPage() {
    // Prefer path /wiki/<slug>
    const path = window.location.pathname;
    const prefix = "/wiki/";

    if (path.startsWith(prefix)) {
      const slug = path.slice(prefix.length).replace(/\/+$/, ""); // remove trailing slash
      if (slug) {
        // Convert clean URL to page file: /wiki/Germany -> Germany.html
        const page = this.cleanUrlToPage(slug);
        if (page) return this.loadPage(page, false);
      }
    }

    // Fallback: ?p=Foo.html
    const urlParams = new URLSearchParams(window.location.search);
    const p = urlParams.get("p");
    if (p) {
      return this.loadPage(p, true);
    }

    // Default to main page
    this.loadMainPage(true);
  }

  loadPageFromUrl() {
    // same logic as loadInitialPage, but do not update history
    const path = window.location.pathname;
    const prefix = "/wiki/";

    if (path.startsWith(prefix)) {
      const slug = path.slice(prefix.length).replace(/\/+$/, "");
      if (slug) {
        const page = this.cleanUrlToPage(slug);
        if (page) return this.loadPage(page, false);
      }
    }

    const urlParams = new URLSearchParams(window.location.search);
    const p = urlParams.get("p");
    if (p) {
      return this.loadPage(p, false);
    }

    this.loadMainPage(false);
  }

  async loadPage(pagePath, updateHistory = true) {
    this.showLoading();

    try {
      // If your raw dump is always under /wiki-raw/A/, keep it:
      const rawPath = `/wiki-raw/A/${pagePath}`;
      const response = await fetch(rawPath);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const html = await response.text();
      const processedContent = this.processWikipediaHTML(html);
      document.getElementById("article-content").innerHTML = processedContent;

      // Update history with canonical clean path: /wiki/<Slug>
      if (updateHistory) {
        const clean = this.pageToCleanUrl(pagePath);
        const newUrl = `/wiki/${clean}`;
        window.history.pushState({ page: pagePath }, "", newUrl);
      }

      this.currentPage = pagePath;
      this.rewriteInternalLinks();

      const title = this.extractTitle(processedContent);
      document.title = title ? `${title} - G-Wiki` : "G-Wiki";
      this.hideLoading();
    } catch (err) {
      console.error("Failed to load page:", err);
      this.showError();
    }
  }

  rewriteInternalLinks() {
    const article = document.getElementById("article-content");
    const links = article.querySelectorAll("a[href]");

    links.forEach((link) => {
      const href = link.getAttribute("href");
      if (!href || href.startsWith("http") || href.startsWith("#")) return;
      if (href.startsWith("/wiki/File:") || href.startsWith("/wiki/Category:"))
        return;

      // Convert Wikipedia-style links to your SPA routes
      if (href.startsWith("/wiki/")) {
        const slug = href.replace(/^\/wiki\//, "");
        const pageName = slug.endsWith(".html") ? slug : `${slug}.html`;
        const clean = this.pageToCleanUrl(pageName);

        link.setAttribute("data-wiki-link", pageName);
        link.setAttribute("href", `/wiki/${clean}`);
        link.addEventListener("click", (e) => {
          e.preventDefault();
          this.loadPage(pageName);
        });
        return;
      }

      // Local html links like "Germany.html"
      if (/\.(html?)$/i.test(href)) {
        const pageName = href;
        const clean = this.pageToCleanUrl(pageName);

        link.setAttribute("data-wiki-link", pageName);
        link.setAttribute("href", `/wiki/${clean}`);
        link.addEventListener("click", (e) => {
          e.preventDefault();
          this.loadPage(pageName);
        });
      }
    });
  }

  async loadMainPage(updateHistory = true) {
    // Try to load a main page or show a welcome message
    const welcomeContent = `
            <h1>Welcome to G-Wiki</h1>
            <p>G-Wiki contains Wikipedia articles that start with the letter "G".</p>
            <p>Use the search box above to find articles, or browse through the collection.</p>
            <h2>Featured Articles</h2>
            <ul>
                <li><a href="#" data-wiki-link="Giraffe.html">Giraffe</a></li>
                <li><a href="#" data-wiki-link="Germany.html">Germany</a></li>
                <li><a href="#" data-wiki-link="Guitar.html">Guitar</a></li>
            </ul>
        `;

    document.getElementById("article-content").innerHTML = welcomeContent;
    this.hideLoading();

    if (updateHistory) {
      window.history.pushState({}, "G-Wiki", "/wiki/");
    }

    document.title = "G-Wiki";
    this.rewriteInternalLinks();
  }

  processWikipediaHTML(html) {
    // Create a temporary container to parse the HTML
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = html;

    // Try to find the main content area
    let content =
      tempDiv.querySelector("#mw-content-text") ||
      tempDiv.querySelector(".mw-parser-output") ||
      tempDiv.querySelector("body") ||
      tempDiv;

    // Remove navigation elements, headers, footers that we don't want
    const unwantedSelectors = [
      "#mw-navigation",
      "#mw-head",
      "#mw-panel",
      ".navbox",
      ".metadata",
      ".printfooter",
      ".catlinks",
      "#footer",
    ];

    unwantedSelectors.forEach((selector) => {
      const elements = content.querySelectorAll(selector);
      elements.forEach((el) => el.remove());
    });

    return content.innerHTML;
  }

  extractTitle(html) {
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = html;
    const h1 = tempDiv.querySelector("h1");
    return h1 ? h1.textContent : null;
  }

  rewriteInternalLinks() {
    const article = document.getElementById("article-content");
    const links = article.querySelectorAll("a[href]");

    links.forEach((link) => {
      const href = link.getAttribute("href");

      // Skip external links, anchors, and special links
      if (
        href.startsWith("http") ||
        href.startsWith("#") ||
        href.startsWith("/wiki/File:") ||
        href.startsWith("/wiki/Category:")
      ) {
        return;
      }

      // Convert Wikipedia links to our clean URL format
      if (href.startsWith("/wiki/")) {
        const pageName = href.replace("/wiki/", "") + ".html";
        const cleanUrl = this.pageToCleanUrl(pageName);

        link.setAttribute("data-wiki-link", pageName);
        link.setAttribute("href", `/wiki/${cleanUrl}`);
        link.addEventListener("click", (e) => {
          e.preventDefault();
          this.loadPage(pageName);
        });
      } else if (href.endsWith(".html")) {
        // Direct HTML links
        const cleanUrl = this.pageToCleanUrl(href);

        link.setAttribute("data-wiki-link", href);
        link.setAttribute("href", `/wiki/${cleanUrl}`);
        link.addEventListener("click", (e) => {
          e.preventDefault();
          this.loadPage(href);
        });
      }
    });
  }

  showLoading() {
    document.getElementById("loading").style.display = "block";
    document.getElementById("error").style.display = "none";
    document.getElementById("article-content").style.display = "none";
  }

  hideLoading() {
    document.getElementById("loading").style.display = "none";
    document.getElementById("error").style.display = "none";
    document.getElementById("article-content").style.display = "block";
  }

  showError() {
    document.getElementById("loading").style.display = "none";
    document.getElementById("error").style.display = "block";
    document.getElementById("article-content").style.display = "none";
  }

  handleSearch() {
    const query = document.getElementById("wiki-search").value.trim();
    if (query) {
      // For now, just try to navigate to the page directly
      // Later this will integrate with search API
      const pageName = query.charAt(0).toUpperCase() + query.slice(1) + ".html";
      this.loadPage(pageName);
    }
  }

  toggleChat() {
    this.chatOpen = !this.chatOpen;
    const chatPanel = document.getElementById("chat-panel");

    if (this.chatOpen) {
      chatPanel.classList.add("open");
    } else {
      chatPanel.classList.remove("open");
    }
  }

  sendChatMessage() {
    const input = document.getElementById("chat-input");
    const message = input.value.trim();

    if (message) {
      this.addChatMessage(message, "user");
      input.value = "";

      // For now, just echo back
      // Later this will integrate with chat API
      setTimeout(() => {
        this.addChatMessage(
          "I'm not quite ready yet! This will be a real chatbot soon.",
          "bot",
        );
      }, 1000);
    }
  }

  addChatMessage(message, sender) {
    const messagesContainer = document.getElementById("chat-messages");
    const messageDiv = document.createElement("div");
    messageDiv.className = `chat-message ${sender}`;

    const messageP = document.createElement("p");
    messageP.textContent = message;
    messageDiv.appendChild(messageP);

    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }
}

// Initialize the app when DOM is loaded
document.addEventListener("DOMContentLoaded", () => {
  new GWiki();
});
