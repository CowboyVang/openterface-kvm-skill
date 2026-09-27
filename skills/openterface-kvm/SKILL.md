---
name: openterface-kvm
description: "Use when an agent must see or type on another computer's physical console through an Openterface Mini-KVM, a USB crash cart: a machine with no network or SSH, its BIOS or UEFI setup, GRUB or a boot menu, an OS installer, a Windows or Linux desktop reached only by HDMI and USB or a password entered at a console. Also when minikvm.py, a capture frame or the unit itself misbehaves. This computer's own screen and web-based consoles belong to desktop and browser automation; a machine still reachable over SSH is reached that way first."
license: MIT
compatibility: "An agent that runs shell commands and reads images, such as Claude Code. macOS host with Python 3 and ffmpeg (capture through avfoundation). Tested with the Mini-KVM's CH32V208 generation and the us and ch keymaps."
---

# Openterface Mini-KVM

A crash cart over USB: this computer becomes one other machine's screen, keyboard and mouse,
with no network in between. The helper is `scripts/minikvm.py` in this skill's directory,
standard library only:

    python3 <skill-dir>/scripts/minikvm.py <verb>

Its `--help` lists the verbs (`info`, `frame`, `type`, `key`, `mouse`, `usb`). Write the path
out each time or put it in a two-line wrapper script: zsh does not word-split a variable that
holds a command.

Cabling: HDMI from the target to the unit; one USB-C from the unit to this computer (capture
and the control serial port); the unit's other USB-C to the target (the emulated keyboard and
mouse).

## Before the first key

Each step ends on its done-condition; start the loop only when all six hold.

1. **The network path is gone, or the job is pre-OS.** A machine that answers SSH is driven
   over SSH. The KVM is for firmware, boot menus, installers, a dead network and a desktop with
   no remote access.
2. **The user's targets file is read, if one exists**: the path in `$OPENTERFACE_KVM_TARGETS`,
   else `~/.config/openterface-kvm/targets.md`. It records each machine's console keymap,
   firmware key and how its passwords are fetched. Its shape is `assets/targets.example.md`.
3. **The unit answers.** `minikvm.py info` prints a port and `target_usb True`. No port: the
   cable to this computer is out, or the port needs `--port` (see the README's hardware
   notes). `target_usb False`: the target-side cable is out or the target is off.
4. **`--layout` is the target's console keymap, confirmed by a probe**, never left to the `us`
   default. The unit sends key positions and the target's keymap turns them into characters,
   so a wrong table types a wrong password with no error. Firmware setup and GRUB usually read
   the keyboard as `us`, whatever the installed system says. The targets file, the user or `XKBLAYOUT` in
   `/etc/default/keyboard` (Debian family) says what to expect; before any password, the probe
   decides. At the login or shell prompt the last frame showed, `type 'qwyz-/' --layout us`
   (no Enter), frame and read what arrived: `qwyz-/` is `us`, `qwzy'-` is `ch`, `qwzyß-` is
   `de`, `azyw)!` is `fr` (`us` and `ch` were typed live; `de` and `fr` come from the compiled
   console keymaps). Then `key ctrl+u` and a frame showing the prompt empty again. When
   the probe and the expectation disagree, the probe wins; when it matches none of these, ask
   the user. The helper ships `us` and `ch`; `references/layouts.md` adds
   more.
5. **One frame is on disk and read.** `minikvm.py frame <tmp>/f.png`, then read the PNG. On
   macOS a capture that runs into its 20 s timeout is the Camera permission prompt, waiting on
   this computer's own screen for the app that runs the agent's shell (the terminal or
   multiplexer). Confirm it from the log rather than a screenshot:
   `log show --last 10m --predicate 'subsystem == "com.apple.TCC" AND eventMessage CONTAINS "kTCCServiceCamera"'`.
   Ask the user to click Allow themselves: on macOS 27 an accessibility press from an
   automation tool left the dialog open. An update to that app can re-key the permission, so
   the prompt may return.
6. **For pre-OS work the KVM is the target's only display.** A second monitor on the same card
   can take the POST and firmware screens while the capture stays black.

## The loop

*Frame-gated*: frame, read it, one action, wait, frame again. The done-condition of every
action is the next frame showing the change you expected. The unit acknowledges a key in
0.3 ms whether or not the target received it, so an exit code of 0 proves nothing.

- Wait about 1 s after a key in a menu, 2 to 3 s after Enter on a command. Firmware dialogs can
  take over 2 s to draw: frame again before the next key.
- Keep one wait plus its frame inside the agent's timeout for a single shell call.
- To act on a moment rather than a timer (a short GRUB countdown), watch the stream; recipe in
  `references/firmware.md`.

Risk decides who acts:

- **Free**: reading, moving through menus, typing at a prompt the last frame showed.
- **Checked in a frame first**: changing any setting. Read the new value on screen before
  saving, and read the save dialog's list of changes before confirming it.
- **The user decides**: erasing or partitioning a disk, installing an OS, saving firmware
  settings, rebooting a machine that serves others and anything on a machine someone is using
  at the same time.

Enter, F10 and Save follow a frame that shows what they will do. A boot menu can hold a
network-boot entry beside the one you want.

## Typing

- `type 'text' --layout <x> [--enter]` types text. `key` takes chords joined with `+`:
  `key ctrl+alt+f2` is one chord, and `key ctrl t` is Ctrl, then T, as two taps.
- A password goes from a password manager's CLI straight into the unit, never through argv or
  the transcript. `type --stdin` requires `--layout`, and it refuses an empty pipe (a failed
  fetch) before any key. A CLI fetch can take 10 s or more while a Linux login waits 60 s for
  the password by default, so type the user name first, then run the pipe. `--stdin` drops the
  trailing newline such a CLI prints:

      <password-manager-cli> | python3 <skill-dir>/scripts/minikvm.py type --stdin --layout us --enter

  where the CLI is, for example, `op read 'op://<vault>/<item>/password'`,
  `bw get password '<item>'` or `pass show '<item>'`.
- Text with quotes, backslashes or several lines goes into a temporary file first, written with
  a quoted heredoc or `printf '%s\n'` (zsh `echo` turns `\U` into a control character). Check
  `LC_ALL=C grep -c '[^ -~]' file` prints 0, then `type --stdin --layout <x> < file`.
- `type` checks every character before the first key. A refusal means nothing was typed, and
  with `--stdin` it names a position, never the character.
- A dark screen eats the first key. Send `key shift`, frame, then type. Start commands with
  a space so a lost key costs nothing.
- Pacing is 12 ms hold and 12 ms gap, 41 characters a second; 4 ms loses the tail of a line
  with no error. `--delay 0.05` makes typing legible on a video.
- Waits of a second or more are a plain `sleep 1`. Only pacing under about 100 ms needs a spin
  on `time.perf_counter()`, which the helper already does: inside an agent harness or terminal
  multiplexer on macOS, `time.sleep(0.02)` measured 80 to 160 ms.

## Reading output

- Fit output to one 1920x1080 frame: clear the screen first (`clear`, `cls;`), keep tables
  short, cap long lists. Output that wraps or scrolls off is lost.
- If SSH comes back, `ssh root@<host> 'fold -w 240 /dev/vcs1'` reads tty1's text exactly (240
  columns is tty1 at 1920x1080). Use it to confirm what a keystroke did.
- Liveness with no picture: `key numlock`, then `info`. A lock LED that toggles means firmware
  or a kernel is reading the keyboard; none after a shutdown means the target is off.
- A black 1080p frame is about 8.6 kB as PNG. Anything much larger is a picture.

## Secrets

Every frame you read enters the transcript and reaches the model provider. Frame no screen
that shows a password, key, recovery code or wallet; report counts and labels instead of
contents. Close password managers and wallet apps before a desktop session. A typed secret goes
only through `--stdin`. The same holds for this computer's own screen: capture one window,
never the whole desktop, which shows everything the user has open.

## Limits

- The unit cannot press a power button. The user powers a machine on; software reboots work
  (`systemctl reboot`, `shutdown /r /t 0`).
- On the CH32V208 generation the unit's USB-A port is reported to move only with its physical
  toggle (Openterface_QT issue 581); on the unit tested, `minikvm.py usb target` was
  acknowledged and the reported state never changed. The port is USB 2.0, and flipping it
  mid-read pulls the stick out.
- About 10 frames a second of raw `uyvy422` at 1080p; one `frame` call takes 1.2 to 1.5 s,
  mostly opening the device. Key to pixels measured 66 to 127 ms.
- The target sees a display (the unit's stock EDID) whether or not anything is capturing.

## References

- Windows desktops, PowerShell, installing Windows: `references/windows.md`
- Getting into firmware and out without saving, and the stream watcher: `references/firmware.md`
- Why `--layout` is the target's keymap, how `ch` was measured, adding a layout, restoring a
  Linux console keymap: `references/layouts.md`
