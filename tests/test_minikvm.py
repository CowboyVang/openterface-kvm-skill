#!/usr/bin/env python3
"""Hermetic test for skills/openterface-kvm/scripts/minikvm.py. No unit attached: a fake one
answers on a pty.

    python3 tests/test_minikvm.py     # exits 0 on pass, 1 on failure

What it pins down: the frame checksum against a reply captured from the real unit, both
layout tables covering printable ASCII with the Swiss differences that bite (y and z, the
AltGr symbols, the dead keys followed by a space), the reply parser skipping a stray frame
and raising on a refusal, and `type` checking the whole text before the first key without
naming a character of piped-in text.
"""
import importlib.util
import os
import string
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER = os.path.join(HERE, "..", "skills", "openterface-kvm", "scripts", "minikvm.py")
spec = importlib.util.spec_from_file_location("minikvm", HELPER)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

failures = []


def check(name, ok):
    print("%s  %s" % ("ok  " if ok else "FAIL", name))
    if not ok:
        failures.append(name)


class FakeUnit(threading.Thread):
    """Reads frames off the pty's master side, records them and answers like the unit."""

    def __init__(self, master, refuse=(), stray=False):
        super().__init__(daemon=True)
        self.master, self.refuse, self.stray, self.seen = master, refuse, stray, []

    def run(self):
        buf = b""
        while True:
            try:
                buf += os.read(self.master, 256)
            except OSError:
                return
            while len(buf) >= 6 and len(buf) >= 6 + buf[4]:
                pkt, buf = buf[:6 + buf[4]], buf[6 + buf[4]:]
                cmd = pkt[3]
                self.seen.append((cmd, pkt[5:-1]))
                if self.stray:
                    os.write(self.master, m.frame(0x81, bytes(8)))
                if cmd in self.refuse:
                    os.write(self.master, m.frame(cmd | 0xC0, b"\xe3"))
                elif cmd == m.CMD_GET_INFO:
                    os.write(self.master, m.frame(0x81, bytes.fromhex("0201020500000000")))
                else:
                    os.write(self.master, m.frame(cmd | 0x80, b"\x00"))


def unit(**kw):
    master, slave = os.openpty()
    fake = FakeUnit(master, **kw)
    fake.start()
    return fake, m.Bridge(os.ttyname(slave))


# frames: GET_INFO and its reply as captured from a real unit on 18 September 2026
check("GET_INFO frame", m.frame(0x01) == bytes.fromhex("57ab00010003"))
check("captured reply checksum", m.frame(0x81, bytes.fromhex("0201000500000000"))[-1] == 0x93)

# layouts
for name, table in m.LAYOUTS.items():
    missing = [c for c in string.printable if c not in table and c not in "\r\x0b\x0c"]
    check("%s covers printable ASCII" % name, not missing)
check("ch swaps y and z", m.CH["y"] == m.US["z"] and m.CH["Z"] == m.US["Y"])
check("ch @ is AltGr+2", m.CH["@"] == [(m.ALTGR, 0x1F)])
check("ch backslash is AltGr on the ISO key", m.CH["\\"] == [(m.ALTGR, 0x64)])
check("ch ~ is a dead key then space", m.CH["~"] == [(m.ALTGR, 0x2E), (0, 0x2C)])

# typing: press and release per stroke, shift carried in the modifier byte
fake, bridge = unit()
bridge.type_text("aB", delay=0)
check("type sends press, release per key",
      fake.seen == [(2, bytes([0, 0, 4, 0, 0, 0, 0, 0])), (2, bytes(8)),
                    (2, bytes([2, 0, 5, 0, 0, 0, 0, 0])), (2, bytes(8))])
info = bridge.info()
check("info decodes the lock LEDs", info["capslock"] and not info["numlock"] and info["target_usb"])

# nothing typed when any character has no key, and a secret is never quoted back
fake.seen.clear()
try:
    bridge.type_text("oké", secret=True)
    check("bad character refused", False)
except m.KvmError as err:
    check("bad character refused before the first key", not fake.seen)
    check("secret error names a position only", "é" not in str(err) and "character 3" in str(err))
bridge.close()

# the parser skips a frame that answers some other command, and raises on a refusal
fake, bridge = unit(stray=True)
bridge.mouse_rel(1, 1)
check("stray frame skipped", fake.seen[-1][0] == m.CMD_MOUSE_REL)
bridge.close()
fake, bridge = unit(refuse=(m.CMD_USB_SWITCH,))
try:
    bridge.usb("status")
    check("refusal raises", False)
except m.KvmError as err:
    check("refusal raises with the unit's reason", "unknown command" in str(err))
bridge.close()

# absolute mouse: centre of a 1920x1080 screen is 2048 of 4096 on both axes
fake, bridge = unit()
bridge.mouse_abs(960, 540, 1920, 1080)
check("absolute centre", fake.seen[-1] == (4, bytes([2, 0, 0x00, 0x08, 0x00, 0x08, 0])))
bridge.close()

# piped text must name the box's keymap: refused before any port is opened
run = subprocess.run([sys.executable, HELPER, "--port", "/nonexistent",
                      "type", "--stdin"], input="x", capture_output=True, text=True)
check("type --stdin without --layout is refused", run.returncode == 2 and "--layout" in run.stderr
      and "nonexistent" not in run.stderr)

# an empty pipe (a failed password fetch) is refused, and no Enter is sent
run = subprocess.run([sys.executable, HELPER, "--port", "/nonexistent", "type", "--stdin",
                      "--layout", "us", "--enter"], input="", capture_output=True, text=True)
check("type --stdin with nothing piped is refused", run.returncode == 2
      and "nothing arrived" in run.stderr and "nonexistent" not in run.stderr)

sys.exit(1 if failures else 0)
