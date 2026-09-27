# Driving Windows through the KVM

Measured on a Windows 11 desktop at 1920x1080 in September 2026, driven from macOS.

## A shell to work in

1. Frame first: someone may be at the same machine (Duplicate display), and a window they open
   takes the focus.
2. `key gui+r`, wait about 1 s, `type powershell --layout <x> --enter`, wait about 3 s,
   `key gui+up` to maximise. A maximised console shows about 50 lines, readable in a frame.
3. Every command goes into a local file and is sent with `type --stdin --layout <x> --enter`.
   Start it with `cls;` so the frame shows only the new output.
4. Shape output for the frame: `ft -a` with computed columns, sizes rounded to GB,
   `-join ', '` for name lists, `select -First 15`.

## Traps

- Win+R `powershell` is not elevated. BitLocker state is still readable without admin:
  `(New-Object -ComObject Shell.Application).NameSpace('C:').Self.ExtendedProperty('System.Volume.BitLockerProtection')`
  (it printed 2, BitLocker off, on the machine measured). `manage-bde` needs admin.
- The screensaver eats the first keystrokes after a pause (`cls` arrived as `s`). `mouse abs`
  did not wake the Bubbles screensaver; `mouse rel` plus `key shift` did. For a long session,
  with the owner's say-so, turn it and sleep off from a non-admin shell and record the old
  values first (`powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE`):
  `SystemParametersInfo(17, 0, 0, 3)` via `Add-Type`, `ScreenSaveActive=0` under
  `HKCU:\Control Panel\Desktop`, `powercfg /change standby-timeout-ac 0` and
  `monitor-timeout-ac 0`. A long job also calls `SetThreadExecutionState(0x80000001)`.
- Script execution can be disabled even where `Start-Process powershell -ExecutionPolicy Bypass
  -File` works. Run a typed file as `& ([scriptblock]::Create((gc x.ps1 -Raw)))`.
- Win+X did nothing through the KVM; a right-click on the Start button opens the same menu.
- A display change shows a keep-or-revert dialog for 10 s. Click "Keep" in the same shell
  command as the change, not after reading a frame.

## Long scripts

- Type the script into a single-quoted here-string (`$s=@'` ... `'@`), then `Set-Content` it to
  a file. PSReadLine takes each newline as a continuation, so a 42-line script (3.7 kB) arrived
  intact in about 90 s. A literal tab triggers completion: use `` `t `` inside strings.
- Prove the typed file matches the local one: on Windows, SHA256 of the UTF-8 bytes of
  `(gc file) -join "`n"`; on the Mac, the same over `text.rstrip('\n')`. Compare the first 16
  hex characters from the frame.
- Run it detached with `Start-Process powershell -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File',<path> -WindowStyle Maximized`,
  logging through `Tee-Object -Append`, and poll the log from the first console.

## Installing Windows

- Before any firmware or install step, the KVM is the only display on the graphics card.
- Build the stick on the Mac: `diskutil eraseDisk MS-DOS WIN11 GPT diskN`, rsync the ISO minus
  `sources/install.wim`, split the WIM with `wimlib-imagex split ... 3800` on the Mac's own
  disk (straight onto FAT32 crawled at 240 kB/s), then copy the parts across. Verify with
  `rsync -rcn` against the mounted ISO and `wimlib-imagex verify`.
- In the boot menu the Mac-built stick appears twice: partition 2 holds the installer.
- The new install's keyboard is the one chosen in setup: Deutsch (Schweiz) means `--layout ch`.
- Shift+F10 opens an elevated cmd, which takes keystrokes only after a mouse click into it.
- `start ms-cxh:localonly` at Shift+F10 on the region screen opens a local-account dialog on
  25H2. German Windows refuses the account name "Benutzer" (a group name).
- Setup can put the EFI system partition on the installer stick when the target disk is blank,
  leaving a PC that boots only with the stick in. Repair without reinstalling: shrink C: in
  diskpart, `create partition efi size=260`, `format quick fs=fat32`, `assign letter=S`, then
  `bcdboot C:\Windows /s S: /f UEFI`. Prevent it by unplugging every other disk, or build the
  stick MBR.

## Filming a demo

Glide the mouse in about 20 steps 30 ms apart and type at `--delay 0.05`; every window and value
then stays legible on a phone video.
