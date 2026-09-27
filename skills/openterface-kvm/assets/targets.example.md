# Targets

Copy to `~/.config/openterface-kvm/targets.md` (or point `$OPENTERFACE_KVM_TARGETS` at your
copy) and describe the machines you plug the KVM into. The skill reads this file before the
first key. Record how a password is fetched, never the password itself.

## nas-01

- Console keymap: `de`, which the helper does not ship yet (see `references/layouts.md`)
- Firmware: F2 at POST; the boot menu is F11
- Password: `pass show servers/nas-01/root`
- Avoid: GRUB entry 2 boots the rescue image

## media-pc (Windows 11)

- Keyboard in Windows: English (US), so `--layout us`
- Firmware: Del at POST; F10 saves, Ctrl+Alt+Del leaves without saving
- Password: `op read 'op://Home/media-pc/password'`
- Notes: the TV on the second HDMI port takes the POST screen; unplug it for firmware work
