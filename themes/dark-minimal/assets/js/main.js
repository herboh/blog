document.documentElement.classList.add("js");

const LANGUAGE_ALIASES = Object.freeze({
  cjs: "javascript",
  conf: "ini",
  console: "shell",
  golang: "go",
  html5: "html",
  jsx: "javascript",
  md: "markdown",
  mjs: "javascript",
  plaintext: "text",
  py: "python",
  rs: "rust",
  sh: "shell",
  text: "text",
  ts: "typescript",
  tsx: "typescript",
  txt: "text",
  yml: "yaml",
});

const LANGUAGE_META = Object.freeze({
  bash: { label: "Bash", short: ">", glyph: "", tone: "sunset" },
  c: { label: "C", short: "C", glyph: "", tone: "sky" },
  cpp: { label: "C++", short: "C++", glyph: "", tone: "sky" },
  css: { label: "CSS", short: "CSS", glyph: "", tone: "gold" },
  diff: { label: "Diff", short: "+/-", glyph: "󰦓", tone: "rose" },
  go: { label: "Go", short: "Go", glyph: "", tone: "sky" },
  html: { label: "HTML", short: "<>", glyph: "", tone: "sunset" },
  ini: { label: "INI", short: "=", glyph: "", tone: "stone" },
  javascript: { label: "JavaScript", short: "JS", glyph: "", tone: "gold" },
  json: { label: "JSON", short: "{}", glyph: "", tone: "stone" },
  lua: { label: "Lua", short: "Lua", glyph: "", tone: "sky" },
  markdown: { label: "Markdown", short: "#", glyph: "", tone: "sage" },
  nix: { label: "Nix", short: "Nix", glyph: "", tone: "sky" },
  python: { label: "Python", short: "Py", glyph: "", tone: "sage" },
  rust: { label: "Rust", short: "Rs", glyph: "", tone: "rose" },
  shell: { label: "Shell", short: ">", glyph: "", tone: "sunset" },
  text: { label: "Code", short: "//", glyph: "󰆍", tone: "stone" },
  toml: { label: "TOML", short: "=", glyph: "", tone: "stone" },
  typescript: { label: "TypeScript", short: "TS", glyph: "", tone: "sky" },
  yaml: { label: "YAML", short: ":", glyph: "", tone: "sage" },
  zsh: { label: "Zsh", short: ">", glyph: "", tone: "sunset" },
});

function humanizeLanguage(language) {
  return language
    .replace(/[-_]+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function buildShortLabel(label) {
  const compact = label.replace(/\s+/g, "");

  if (compact.length <= 3) {
    return compact.toUpperCase();
  }

  return compact.slice(0, 2).toUpperCase();
}

function getLanguageMeta(value) {
  const normalized = (value || "").trim().toLowerCase();
  const key = normalized ? LANGUAGE_ALIASES[normalized] || normalized : "text";
  const known = LANGUAGE_META[key];

  if (known) {
    return { ...known, key };
  }

  const label = humanizeLanguage(key);
  return {
    key,
    label,
    short: buildShortLabel(label),
    tone: "stone",
  };
}

document.addEventListener("DOMContentLoaded", () => {
  const hasNerdFont = [
    '"Symbols Nerd Font Mono"',
    '"Symbols Nerd Font"',
    '"JetBrainsMono Nerd Font"',
    '"MesloLGS Nerd Font Mono"',
  ].some((fontName) => document.fonts?.check?.(`1em ${fontName}`, ""));
  const header = document.querySelector(".site-header");
  const navToggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector(".site-nav");

  if (header && navToggle && nav) {
    navToggle.addEventListener("click", () => {
      const isOpen = header.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", String(isOpen));
    });

    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        header.classList.remove("is-open");
        navToggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  document.querySelectorAll(".highlight").forEach((block) => {
    const pre = block.querySelector("pre");
    const code = block.querySelector("code");

    if (!pre || !code || block.querySelector(".code-block__topbar")) {
      return;
    }

    const classLanguage = Array.from(code.classList).find((name) => name.startsWith("language-"));
    const language = getLanguageMeta(code.dataset.lang || classLanguage?.replace("language-", ""));

    block.dataset.codeLanguage = language.key;
    block.dataset.codeTone = language.tone;

    const topbar = document.createElement("div");
    topbar.className = "code-block__topbar";

    const meta = document.createElement("div");
    meta.className = "code-block__meta";

    const badge = document.createElement("span");
    badge.className = "code-block__badge";

    const icon = document.createElement("span");
    icon.className = "code-block__icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = hasNerdFont && language.glyph ? language.glyph : language.short;

    if (hasNerdFont && language.glyph) {
      icon.classList.add("is-glyph");
    }

    const label = document.createElement("span");
    label.className = "code-block__label";
    label.textContent = language.label;

    badge.append(icon, label);
    meta.append(badge);

    topbar.append(meta);
    block.prepend(topbar);
  });
});
