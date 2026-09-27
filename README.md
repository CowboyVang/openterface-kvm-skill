# openterface-kvm-skill

An agent skill that lets a coding agent work another computer's physical console through an
[Openterface Mini-KVM](https://openterface.com/): the screen through the unit's HDMI capture,
the keyboard and mouse through its serial-controlled USB HID chip. It is for the jobs SSH
cannot reach: firmware setup, boot menus, OS installers and machines whose network is gone.

Unofficial. Not affiliated with TechxArtisan or the Openterface project.

## Why a skill

Sending a key and grabbing a frame are simple. What goes wrong is the loop around them:

- The unit acknowledges a key in 0.3 ms whether or not the target received it. Only the next
  frame shows whether it landed.
- The unit sends key positions and the target's keymap picks the characters. A password typed
  with the wrong keymap fails as "Login incorrect", with no other sign.
- On macOS the first capture waits for a Camera permission prompt on the host's own screen. It
  hangs rather than failing.
- A screensaver eats the first key after a pause, and a second monitor can take the POST screen
  while the capture stays black.
- A password passed as a command argument or tool argument ends up in the agent's transcript.

The skill gives the agent a frame-gated loop (one action, then a frame that proves it), a
keymap probe at the login prompt before any password, a rule for which actions need the user's
approval and a way to pipe a password from a password manager into the target without it
passing through argv or the transcript.

## What is in here

| Path | What |
|------|------|
| `skills/openterface-kvm/SKILL.md` | The procedure the agent follows. |
| `skills/openterface-kvm/scripts/minikvm.py` | The helper: `info`, `frame`, `type`, `key`, `mouse`, `usb`. Python 3 standard library only. |
| `skills/openterface-kvm/references/` | Windows through the KVM, routes into firmware setup, keymaps and how to add one. |
| `skills/openterface-kvm/assets/targets.example.md` | An optional file describing your machines: keymap, firmware key, how a password is fetched. |
| `tests/test_minikvm.py` | Hermetic tests: a fake unit answers on a pseudo-terminal. |

## Requirements

- A macOS host. `frame` captures through ffmpeg's `avfoundation` input. Tested on macOS 27.0
  with ffmpeg 9.0.1.
- Python 3. Apple's `/usr/bin/python3` works.
- ffmpeg, for example `brew install ffmpeg`.
- Camera permission for the app that runs the agent's shell (your terminal or multiplexer).
  macOS asks on the first capture.
- An agent that runs shell commands and reads images. Tested with Claude Code.

## Install

Claude Code:

```sh
git clone https://github.com/CowboyVang/openterface-kvm-skill.git
cp -R openterface-kvm-skill/skills/openterface-kvm ~/.claude/skills/
```

`SKILL.md` follows the [Agent Skills](https://agentskills.io/specification) format, which other
agents read too, but only Claude Code has been tested.

Optionally, describe the machines you plug the KVM into:

```sh
mkdir -p ~/.config/openterface-kvm
cp openterface-kvm-skill/skills/openterface-kvm/assets/targets.example.md ~/.config/openterface-kvm/targets.md
```

The agent reads it before the first key. Without it, the agent asks you for the target's
keymap.

## Using it

Ask for the outcome and the agent loads the skill: "the NAS stopped answering SSH, look at its
console", "get into the mini PC's BIOS and check the boot order", "log in as root at the
console with the password from 1Password". The helper also works by hand:

```sh
H=~/.claude/skills/openterface-kvm/scripts/minikvm.py
python3 $H info                        # port, firmware, whether the target sees the keyboard, lock LEDs
python3 $H frame /tmp/screen.png       # one frame of the target's screen
python3 $H key ctrl+alt+f2             # chords are joined with +
op read 'op://Home/nas/password' | python3 $H type --stdin --layout us --enter
```

## Hardware notes

Tested with the Mini-KVM's CH32V208 generation, firmware `0x02` as `info` reports it:

| Side | Device | VID:PID | Appears as |
|------|--------|---------|------------|
| Host | MACROSILICON MS2109S capture | `345f:2109` | camera `Openterface` |
| Host | WCH CH32V208, speaking the CH9329 protocol | `1a86:fe0c` | `/dev/cu.usbmodem*` (CDC-ACM, baud rate ignored) |
| Target | "KeyMod" HID | `1a86:fe00` | boot keyboard, relative and absolute mouse |

On 27 September 2026 fresh Claude Code sessions, each given a one-paragraph task and nothing
else, ran the procedure end to end against a Linux server. With this public copy and no targets
file, one probed the keymap, logged in as root with a password piped from a password manager,
ran a command and logged out. With the author's private copy (the same procedure plus a table
of the author's machines), others rebooted into UEFI setup and left it without saving, and
typed all 95 printable ASCII characters through a Swiss German console keymap that the probe
found where the table expected a US one.

Measured on one unit in September 2026:

- A 12 ms hold and 12 ms gap typed 41 characters a second intact; 4 ms lost the tail of a line
  with no error.
- Frames arrive as raw `uyvy422` at about 10 per second at 1080p, so a still has no compression
  artefacts and firmware text reads digit for digit. The capture sends full-range YUV; the
  helper tells ffmpeg so, or whites clip.
- From a key press to the character's pixels in a saved frame: 66 to 127 ms.
- The target sees a display (the unit's stock EDID) whether or not anything is capturing.

Not tested:

- **Older units** with a real CH9329 behind a CH340 (`1a86:7523`, `/dev/cu.wchusbserial*`). They
  speak the same frames, but the helper does not probe CH340 ports on its own: opening one
  toggles DTR, which can reset a development board (an ESP32, for example) on the same bridge
  chip. Pass the port with `--port` or `MINIKVM_PORT`.
- **Linux hosts.** The hermetic tests pass on Ubuntu and the helper probes `/dev/ttyACM*`, but
  no unit has been driven from Linux, and `frame` uses `avfoundation` only.
- **Keymaps** other than `us` and `ch` (Swiss German). `references/layouts.md` shows how to add
  one.

The USB-A port's software switch is reported not to move the port on this generation
([Openterface_QT issue 581](https://github.com/TechxArtisanStudio/Openterface_QT/issues/581)).
On the unit tested, `usb target` was acknowledged and the reported state never changed. Use the
physical toggle.

## Alternatives

- **Openterface_QT**, the vendor's host app for Linux and Windows, includes an MCP server
  (stdio, named pipe or SSE) with keyboard, mouse, capture and OCR tools. Its typing tool takes
  the text as an argument, so a password would pass through the transcript; the procedure in
  `SKILL.md` applies to it otherwise.
- **[sunasaji/mcp-serial-hid-kvm](https://github.com/sunasaji/mcp-serial-hid-kvm)**, an MCP
  server for do-it-yourself CH9329 and capture rigs, with target keymaps and OCR.
- **[sjmf/kvm-serial](https://github.com/sjmf/kvm-serial)**, a software KVM for CH9329 and
  CH9350L bridges, run as a GUI or a script.

## Credits

The serial protocol is WCH's CH9329, from its datasheet. The USB-switch command `0x17` and its
payloads were read from Openterface_QT's `serial/ch9329.h` as protocol facts; no code was taken
from that AGPL-3.0 project.

## Licence

MIT. See `LICENSE`.
