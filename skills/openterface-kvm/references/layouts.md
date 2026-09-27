# Keymaps

## Why `--layout` names the target's keymap

The unit is a USB keyboard. It sends key positions (HID usage ids); the target's own keymap
turns a position into a character. So `--layout` is the keymap of the console the target is
running, never this computer's. Firmware setup and GRUB usually read the keyboard as US,
whatever the installed system uses. A password typed with the wrong table arrives with letters
swapped and symbols moved, and the target answers "Login incorrect" with nothing else to go on.

## How `ch` was built

The `ch` (Swiss German) table in `scripts/minikvm.py` was read off a live Linux console keymap
with `dumpkeys -f -n` on 18 September 2026. It typed all 95 printable ASCII characters intact
into a console carrying that keymap, compared over SSH. On it `^`, `` ` `` and `~` are dead
keys; the helper sends each followed by a space, which the Linux console turns into the bare
character. A Windows setup set to Deutsch (Schweiz) was typed with `--layout ch`, but only the
Linux console was checked character by character.

## Adding a layout

1. On a machine running the target keymap: `dumpkeys -f -n > keymap.txt` and read which keycode
   and modifier gives each printable character.
2. Translate each to `(modifiers, usage id)` strokes in a new table beside `US` and `CH` in
   `scripts/minikvm.py`, and register it in `LAYOUTS`.
3. Prove it: type all 95 printable characters into a file at the console, then compare that
   file over SSH with the source string. Add the table's differences to
   `tests/test_minikvm.py` in the repository.

## Restoring a Linux console keymap

A `loadkeys` of a `dumpkeys` dump merges into the running keymap rather than replacing it. To
put a Debian console back exactly, load the cached original:

    loadkeys /etc/console-setup/cached_UTF-8_del.kmap.gz
