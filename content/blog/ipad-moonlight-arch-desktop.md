---
title: "iPad Mini as a Portable Arch Linux Desktop with Moonlight"
date: 2026-02-04
description: "Turning an iPad Mini into a lightweight window into a home Arch desktop with Moonlight and Sunshine."
tags: ["linux", "arch", "ipad", "moonlight", "streaming", "workflow"]
draft: false
---

## Setting up Sunshine on Arch

[Sunshine](https://github.com/LizardByte/Sunshine) is the self-hosted game streaming server that replaces NVIDIA GameStream.

Install from the AUR:

```bash
yay -S sunshine
```

Enable and start the service:

```bash
systemctl --user enable --now sunshine
```

ToDo;

describe my [sunshine PR #4665](https://github.com/LizardByte/Sunshine/pull/4665)

and the config to get ipad working with wayland/niri

---
