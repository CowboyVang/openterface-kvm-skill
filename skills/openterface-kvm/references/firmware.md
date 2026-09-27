# Into firmware and out without saving

Frame before every Enter. A USB stick present at boot gets its own firmware boot entry and
leaves with the stick.

## Routes

- With a shell on a UEFI Linux machine (the console or SSH), `systemctl reboot --firmware-setup`
  asks the firmware to open setup on the next boot, with no key timing. It is the route to
  take when a shell is available.
- GRUB on a UEFI install often lists "UEFI Firmware Settings" as its last entry: `key down`
  until a frame shows it selected, then `key enter`. It needs no timing. Read the frame first:
  custom entries such as a network boot loader can sit next to it.
- A setup key at POST: press it every 0.5 s from a few seconds after the reboot, then frame. A
  POST splash may show no key hint at all.

## Measured on two machines (September 2026)

A mini PC with AMI Aptio setup, Linux installed:

- `systemctl reboot --firmware-setup`, typed at the console, skipped GRUB and drew the setup
  34 s later.
- Without it, `systemctl reboot` reached the GRUB menu in 31 to 44 s. GRUB waited 5 s and took
  keys from the unit, so the keyboard is enumerated by then.
- GRUB's "UEFI Firmware Settings" opened Aptio setup about 14 s later.
- Left and Right changed tabs and nothing else. The Boot tab opened with the cursor in an
  editable number field: type nothing there.
- `key esc` raised "Quit without saving?" with Yes selected; read it in a frame, then
  `key enter`. SSH answered 33 s later.

An ASUS desktop board, Windows 11:

- POST and setup drew only on the first display. With a second monitor attached the capture
  stayed black: make the KVM the only display.
- `shutdown /r /t 0` works from a non-admin shell. `key del` every 0.5 s from about 6 s after
  it caught the setup key.
- Mouse clicks land in the ASUS UEFI (tabs, dropdowns, dialogs).
- `key f10` opens Save and reset, a dialog listing every changed value; it took over 2 s to
  draw. Read the list before OK.
- Ctrl+Alt+Del restarts without writing anything: the way out when the screen is unread.
- F8 is the boot menu. A stick built on a Mac is listed twice: partition 1 is the empty EFI
  partition macOS creates, partition 2 holds the installer.

## Watching the stream for a moment

When a key has to land inside a short window (a 5 s GRUB countdown), watch a thumbnail stream
instead of sleeping:

    ffmpeg -hide_banner -loglevel error -f avfoundation -framerate 30 -pixel_format uyvy422 \
      -video_size 1920x1080 -i Openterface -vf fps=5,scale=64:36 -f rawvideo -pix_fmt rgb24 -

Each frame is 6,912 bytes (64 x 36 x 3). Read them in a small Python loop and act when the
region you care about changes: GRUB is the moment the middle of the frame turns blue, and a
`key down` sent then stops its countdown. A blue centre also matches some firmware setup
screens, so a watcher can fire in the wrong one: take a full frame before any key that
changes something.
