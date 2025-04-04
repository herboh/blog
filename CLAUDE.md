# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands
- Start local development server: `hugo server -D`
- Build site: `hugo`
- New content: `hugo new content [path]/[filename].md`

## Project Structure
- `content/`: All markdown content files
- `themes/dark-minimal/`: Custom theme 
- `assets/`: CSS, JS, and images
- `layouts/`: Custom HTML templates
- `static/`: Static files copied directly to output
- `config.toml` or `hugo.toml`: Site configuration

## Guidelines
- Follow Hugo's content organization conventions
- Use resources.Get for asset pipelines
- Place CSS in theme's assets/css directory
- Maintain dark theme color palette (see main.css)
- Test all pages on both mobile and desktop viewports
- Keep templates DRY by using Hugo partials