---
title: "iPad Mini as a Portable Arch Linux Desktop with Moonlight"
date: 2026-02-04
tags: ["linux", "arch", "ipad", "moonlight", "streaming", "workflow"]
draft: true
---

## Why stream your desktop to an iPad?

Carrying a full laptop isn't always worth it. An iPad Mini fits in a jacket pocket, has a great display, and with [Moonlight](https://moonlight-stream.org/) it becomes a window into a full Arch Linux desktop running at home. This post covers how I set that up and what the day-to-day experience is like.

## Hardware

- **iPad Mini** (6th gen) -- the size is the whole point
- **Home server / desktop** running Arch with an NVIDIA GPU (Sunshine requires hardware encoding)
- A decent internet connection on both ends -- 20 Mbps up at home is enough for 1080p60

> If you're on AMD/Intel, Sunshine still works but check the [encoder support matrix](https://docs.lizardbyte.dev/projects/sunshine/en/latest/) for your GPU.

### Optional accessories

1. A compact Bluetooth keyboard (I use a Keychron K7)
2. A small folding stand
3. USB-C to Ethernet adapter for the home machine if it's on Wi-Fi

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

Then open `https://localhost:47990` in a browser to set a username and password.

### Sunshine config tweaks

The default config lives at `~/.config/sunshine/sunshine.conf`. Here are the settings I changed:

```ini
# Match your monitor resolution
output_name = 0
fps = [60, 30]
min_log_level = info
```

For a **Hyprland** session, you need to set the correct Wayland display:

```bash
export WAYLAND_DISPLAY=wayland-1
```

## Moonlight on iPad

Install [Moonlight](https://apps.apple.com/app/moonlight-game-streaming/id1000551566) from the App Store. Add your host by IP address or hostname. Pair it using the PIN Sunshine shows in its web UI.

**Recommended Moonlight settings:**

- Resolution: *1080p* (matches well with the iPad Mini display)
- FPS: *60*
- Bitrate: *20 Mbps* for local, *10 Mbps* over the internet
- Video codec: *HEVC* if your GPU supports it

## The Arch desktop environment

I run **Hyprland** as my compositor. The key pieces:

- **Hyprland** -- tiling Wayland compositor
- **Waybar** -- status bar
- **fuzzel** -- application launcher
- **foot** -- terminal emulator
- **dunst** -- notifications

### Relevant Hyprland config

```ini
monitor = , 1920x1080@60, auto, 1

input {
    kb_layout = us
    follow_mouse = 1
    sensitivity = 0
}

general {
    gaps_in = 4
    gaps_out = 8
    border_size = 2
    col.active_border = rgb(d79921)
    col.inactive_border = rgb(3c3836)
}
```

### Key tools and dotfiles

The tools I rely on daily:

- **neovim** for editing everything
- **tmux** for session persistence (critical when streaming -- if Moonlight disconnects, your work is still there)
- **eza**, **bat**, **ripgrep**, **fd** -- modern coreutils replacements
- **zoxide** for fast directory jumping

All my dotfiles are managed with a *bare git repo*:

```bash
alias dotfiles='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
dotfiles add ~/.config/hypr/hyprland.conf
dotfiles commit -m "update hyprland gaps"
```

## Results

The experience is surprisingly usable. Text is sharp at 1080p on the iPad Mini's 8.3" display. Latency over LAN is **under 5ms** with HEVC encoding, and around 20-30ms over a WireGuard tunnel from a coffee shop.

![iPad Mini showing Arch desktop](/images/blog/ipad-moonlight-setup.jpg "The full setup: iPad Mini on a folding stand with a Keychron K7")

Things that work *well*:

- **Coding in neovim** -- feels native, latency is imperceptible on LAN
- **Web browsing** -- Firefox with touch input forwarding from Moonlight
- **Terminal workflows** -- tmux + foot is fast and responsive

Things that are **rough**:

- Anything requiring precise mouse input (image editing, CAD)
- Video calls -- the audio routing gets complicated
- On-screen keyboard is terrible; bring a real keyboard

## Conclusion

This setup won't replace a laptop for everyone, but for a *terminal-heavy workflow* it's hard to beat the portability. The iPad Mini fits where a laptop doesn't, and Moonlight's streaming quality has gotten good enough that the compromise is minimal.

If you try this, the two things that matter most are:

1. **Network quality** -- low latency matters more than bandwidth
2. **tmux** -- always have a safety net for disconnections

{{< youtube dQw4w9WgXcQ >}}

---

*Have questions or a similar setup? Reach out on [GitHub](https://github.com/herboh).*
