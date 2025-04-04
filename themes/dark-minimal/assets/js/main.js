// Smooth scroll effect for internal links
document.addEventListener('DOMContentLoaded', () => {
  // Smooth scrolling for internal links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        target.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });

  // Add subtle fade-in animation for content
  const mainContent = document.querySelector('.main-container');
  if (mainContent) {
    mainContent.style.opacity = '0';
    mainContent.style.transition = 'opacity 0.5s ease-in-out';
    setTimeout(() => {
      mainContent.style.opacity = '1';
    }, 50);
  }
  
  // Add subtle hover effects for links
  const links = document.querySelectorAll('a');
  links.forEach(link => {
    link.addEventListener('mouseenter', () => {
      link.style.transition = 'all 0.2s ease-in-out';
    });
  });
  
  // Toggle dark/light theme (advanced feature)
  const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
  const currentTheme = localStorage.getItem('theme');
  
  // Set the initial theme based on saved preference or system preference
  if (currentTheme === 'light') {
    document.body.classList.add('light-theme');
  } else if (currentTheme === 'dark') {
    document.body.classList.add('dark-theme');
  } else if (prefersDarkScheme.matches) {
    document.body.classList.add('dark-theme');
  }
  
  // Add theme toggle button to footer (optional)
  const footer = document.querySelector('footer');
  if (footer) {
    const themeToggle = document.createElement('div');
    themeToggle.className = 'theme-toggle';
    themeToggle.innerHTML = `
      <button id="theme-toggle" aria-label="Toggle dark/light theme">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      </button>
    `;
    footer.appendChild(themeToggle);
    
    // Toggle theme on button click
    const toggleButton = document.getElementById('theme-toggle');
    if (toggleButton) {
      toggleButton.addEventListener('click', () => {
        document.body.classList.toggle('light-theme');
        
        // Save preference
        if (document.body.classList.contains('light-theme')) {
          localStorage.setItem('theme', 'light');
        } else {
          localStorage.setItem('theme', 'dark');
        }
      });
    }
  }
  
  // Add code highlighting with highlight.js if code blocks are present
  const codeBlocks = document.querySelectorAll('pre code');
  if (codeBlocks.length > 0) {
    // Lazy-load highlight.js only if code blocks are found
    const highlightScript = document.createElement('script');
    highlightScript.src = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/highlight.min.js';
    highlightScript.onload = () => {
      hljs.highlightAll();
    };
    document.head.appendChild(highlightScript);
    
    // Add highlight.js styles
    const highlightCss = document.createElement('link');
    highlightCss.rel = 'stylesheet';
    highlightCss.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/styles/github-dark.min.css';
    document.head.appendChild(highlightCss);
  }
});

// Add reading time calculator
function calculateReadingTime() {
  const content = document.querySelector('.main-container');
  if (!content) return;
  
  const text = content.textContent;
  const wordCount = text.split(/\s+/).length;
  const readingTime = Math.ceil(wordCount / 200); // Average reading speed: 200 wpm
  
  const readingTimeElement = document.createElement('div');
  readingTimeElement.className = 'reading-time';
  readingTimeElement.innerHTML = `<span>${readingTime} min read</span>`;
  
  const titleElement = document.querySelector('h1');
  if (titleElement && titleElement.parentNode) {
    titleElement.parentNode.insertBefore(readingTimeElement, titleElement.nextSibling);
  }
}

// Execute reading time calculation on blog posts
if (window.location.pathname.includes('/blog/')) {
  document.addEventListener('DOMContentLoaded', calculateReadingTime);
}