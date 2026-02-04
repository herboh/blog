// This script will transform your raw HTML into Wikipedia-style layout
document.addEventListener("DOMContentLoaded", function () {
  // Wrap existing content
  const body = document.body;
  const originalContent = body.innerHTML;

  // Create Wikipedia-style structure
  body.innerHTML = `
        <div id="wiki-header"><!-- Header content --></div>
        <div id="wiki-container">
            <div id="wiki-sidebar"><!-- Navigation --></div>
            <div id="wiki-content">${originalContent}</div>
        </div>
    `;
});
