#!/usr/bin/env python3
"""Drive an Openterface Mini-KVM from a shell.

The unit is a crash cart over USB for one headless machine. Its host-side USB-C presents
a hub with two devices behind it: a UVC capture (the box's HDMI picture) and a CDC-ACM
serial port that speaks WCH's CH9329 protocol and becomes a USB keyboard and mouse on the
box. This file wraps both, with nothing outside the standard library, so it runs under
Apple's /usr/bin/python3 as well as Homebrew's.

    minikvm.py info                      what the unit reports, and where the USB-A port points
    minikvm.py frame /tmp/screen.png     one frame of the box's screen (needs ffmpeg + Camera)
    minikvm.py type 'root' --enter       type text; --layout ch for a box with the Swiss keymap
    minikvm.py type --stdin --layout us  same, text read from stdin (keeps a password off argv);
                                         --layout is required here, a wrong table fails silently
    minikvm.py key ctrl+alt+f2           one chord; names in KEYS below
    minikvm.py mouse abs 960 540         pointer to a pixel of a 1920x1080 screen
    minikvm.py mouse rel 40 -10          relative move
    minikvm.py mouse click [left|right|middle]
    minikvm.py usb status|host|target    the shared USB-A port (eject the stick first)

Procedure and measured behaviour: SKILL.md and references/ beside this script. Protocol
source: WCH's CH9329 datasheet and the vendor's AGPL host app
(TechxArtisanStudio/Openterface_QT, serial/ch9329.h).
"""
import argparse
import glob
import os
import select
import subprocess
import sys
import termios
import time

HEAD = b"\x57\xab\x00"
CMD_GET_INFO = 0x01
CMD_KEYBOARD = 0x02
CMD_MOUSE_ABS = 0x04
CMD_MOUSE_REL = 0x05
CMD_GET_PARA_CFG = 0x08
CMD_USB_SWITCH = 0x17  # Openterface extension, not in WCH's datasheet

STATUS = {
    0x00: "ok", 0xE1: "timeout", 0xE2: "bad header", 0xE3: "unknown command",
    0xE4: "bad checksum", 0xE5: "bad parameter", 0xE6: "operation failed",
}

MOD = {"ctrl": 0x01, "shift": 0x02, "alt": 0x04, "gui": 0x08, "win": 0x08, "cmd": 0x08,
       "rctrl": 0x10, "rshift": 0x20, "ralt": 0x40, "altgr": 0x40, "rgui": 0x80}

KEYS = {"enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B, "space": 0x2C,
        "capslock": 0x39, "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48,
        "insert": 0x49, "home": 0x4A, "pageup": 0x4B, "del": 0x4C, "delete": 0x4C,
        "end": 0x4D, "pagedown": 0x4E, "right": 0x4F, "left": 0x50, "down": 0x51,
        "up": 0x52, "numlock": 0x53}
KEYS.update({"f%d" % n: 0x39 + n for n in range(1, 13)})

# A layout maps a character to the strokes that produce it, each stroke (modifiers, usage id).
# The keyboard sends positions, the box's keymap turns them into characters, so the layout
# to pass is the BOX's console keymap (`grep XKBLAYOUT /etc/default/keyboard` on Debian).
# Firmware setup screens and GRUB usually read the keyboard as us.
SHIFT, ALTGR = 0x02, 0x40
US = {}
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    US[c] = [(0, 0x04 + i)]
    US[c.upper()] = [(SHIFT, 0x04 + i)]
for i, (plain, shifted) in enumerate(zip("1234567890", "!@#$%^&*()")):
    US[plain] = [(0, 0x1E + i)]
    US[shifted] = [(SHIFT, 0x1E + i)]
for usage, plain, shifted in ((0x2D, "-", "_"), (0x2E, "=", "+"), (0x2F, "[", "{"),
                              (0x30, "]", "}"), (0x31, "\\", "|"), (0x33, ";", ":"),
                              (0x34, "'", '"'), (0x35, "`", "~"), (0x36, ",", "<"),
                              (0x37, ".", ">"), (0x38, "/", "?")):
    US[plain] = [(0, usage)]
    US[shifted] = [(SHIFT, usage)]
for c, usage in ((" ", 0x2C), ("\n", 0x28), ("\t", 0x2B)):
    US[c] = [(0, usage)]

# Swiss German, read off a live Linux console keymap with `dumpkeys -f -n` on 18 September 2026.
# y and z trade places, 0x64 is the extra ISO key left of y, and ^ ` ~ sit on dead keys, which
# the Linux console turns into the bare character when a space follows.
CH = {c: strokes for c, strokes in US.items() if c.isalnum() or c in " \n\t"}
for c, other in (("y", "z"), ("z", "y"), ("Y", "Z"), ("Z", "Y")):
    CH[c] = US[other]
SPACE = (0, 0x2C)
CH.update({
    "!": [(SHIFT, 0x30)], '"': [(SHIFT, 0x1F)], "#": [(ALTGR, 0x20)], "$": [(0, 0x31)],
    "%": [(SHIFT, 0x22)], "&": [(SHIFT, 0x23)], "'": [(0, 0x2D)], "(": [(SHIFT, 0x25)],
    ")": [(SHIFT, 0x26)], "*": [(SHIFT, 0x20)], "+": [(SHIFT, 0x1E)], ",": [(0, 0x36)],
    "-": [(0, 0x38)], ".": [(0, 0x37)], "/": [(SHIFT, 0x24)], ":": [(SHIFT, 0x37)],
    ";": [(SHIFT, 0x36)], "<": [(0, 0x64)], "=": [(SHIFT, 0x27)], ">": [(SHIFT, 0x64)],
    "?": [(SHIFT, 0x2D)], "@": [(ALTGR, 0x1F)], "[": [(ALTGR, 0x2F)], "\\": [(ALTGR, 0x64)],
    "]": [(ALTGR, 0x30)], "_": [(SHIFT, 0x38)], "{": [(ALTGR, 0x34)], "|": [(ALTGR, 0x24)],
    "}": [(ALTGR, 0x31)], "^": [(0, 0x2E), SPACE], "`": [(SHIFT, 0x2E), SPACE],
    "~": [(ALTGR, 0x2E), SPACE],
})
LAYOUTS = {"us": US, "ch": CH}
CHARS = US  # chord() names keys by their US legend

BUTTONS = {"left": 0x01, "right": 0x02, "middle": 0x04}


class KvmError(Exception):
    pass


def wait(seconds):
    """Spin, do not sleep. Inside an agent harness or terminal multiplexer on macOS a
    time.sleep(0.02) measured 80 to 160 ms (timer coalescing on a background process),
    which turns 41 characters a second into four."""
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pass


def frame(cmd, data=b""):
    body = HEAD + bytes([cmd, len(data)]) + data
    return body + bytes([sum(body) & 0xFF])


class Bridge:
    """The serial side. CDC-ACM, so the baud rate set here is ignored by the unit."""

    def __init__(self, port):
        self.port = port
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[4] = attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def close(self):
        os.close(self.fd)

    def xfer(self, cmd, data=b"", timeout=0.5):
        """Send one frame, return the reply's payload. Raises on a bad or missing reply."""
        os.write(self.fd, frame(cmd, data))
        buf = b""
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([self.fd], [], [], 0.02)
            if not ready:
                continue
            try:
                buf += os.read(self.fd, 256)
            except BlockingIOError:
                continue
            while True:
                start = buf.find(HEAD)
                if start < 0 or len(buf) < start + 5:
                    break
                need = start + 5 + buf[start + 4] + 1
                if len(buf) < need:
                    break
                reply, buf = buf[start:need], buf[need:]
                if sum(reply[:-1]) & 0xFF != reply[-1]:
                    raise KvmError("reply failed its checksum: " + reply.hex(" "))
                if reply[3] == (cmd | 0xC0):
                    raise KvmError("unit refused command 0x%02x: %s" % (
                        cmd, STATUS.get(reply[5], hex(reply[5]))))
                if reply[3] == (cmd | 0x80):
                    return reply[5:-1]
                # a frame answering some other command: drop it and keep parsing
        raise KvmError("no reply to command 0x%02x on %s" % (cmd, self.port))

    def ack(self, cmd, data):
        payload = self.xfer(cmd, data)
        if payload and payload[0] != 0x00:
            raise KvmError("command 0x%02x: %s" % (cmd, STATUS.get(payload[0], hex(payload[0]))))

    # keyboard -----------------------------------------------------------------
    def press(self, mods, usages, hold=0.012):
        """Measured against a box polling the keyboard every 10 ms: 12 ms hold and gap is
        intact at 41 characters a second, 8 ms still is, 4 ms overruns the unit and the
        tail of the line is lost. The unit acks in 0.3 ms whether or not the key lands."""
        keys = bytes(usages[:6]).ljust(6, b"\x00")
        self.ack(CMD_KEYBOARD, bytes([mods, 0]) + keys)
        wait(hold)
        self.ack(CMD_KEYBOARD, bytes(8))

    def type_text(self, text, delay=0.012, secret=False, layout="us"):
        """Checks the whole text before the first key, so a bad character never leaves half
        a password on the box, and names a position rather than a character of a secret."""
        table = LAYOUTS[layout]
        for at, ch in enumerate(text):
            if ch not in table:
                raise KvmError("no %s-layout key for %s; nothing was typed" % (
                    layout, "character %d of the input" % (at + 1) if secret else repr(ch)))
        for ch in text:
            for mods, usage in table[ch]:
                self.press(mods, [usage])
                wait(delay)

    def chord(self, spec):
        mods, usages = 0, []
        for part in spec.lower().split("+"):
            if part in MOD:
                mods |= MOD[part]
            elif part in KEYS:
                usages.append(KEYS[part])
            elif len(part) == 1 and part in CHARS:
                usages.append(CHARS[part][0][1])
            else:
                raise KvmError("unknown key %r in %r" % (part, spec))
        self.press(mods, usages, hold=0.05)

    # mouse --------------------------------------------------------------------
    def mouse_abs(self, x, y, width, height, buttons=0):
        ax = max(0, min(4095, int(x * 4096 / width)))
        ay = max(0, min(4095, int(y * 4096 / height)))
        self.ack(CMD_MOUSE_ABS, bytes([0x02, buttons, ax & 0xFF, ax >> 8, ay & 0xFF, ay >> 8, 0]))

    def mouse_rel(self, dx, dy, buttons=0, wheel=0):
        clamp = lambda v: max(-127, min(127, v)) & 0xFF
        self.ack(CMD_MOUSE_REL, bytes([0x01, buttons, clamp(dx), clamp(dy), clamp(wheel)]))

    def click(self, button="left"):
        self.mouse_rel(0, 0, BUTTONS[button])
        wait(0.05)
        self.mouse_rel(0, 0, 0)

    # unit state -----------------------------------------------------------------
    def info(self):
        p = self.xfer(CMD_GET_INFO)
        leds = p[2]
        return {"firmware": "0x%02x" % p[0], "target_usb": bool(p[1]),
                "numlock": bool(leds & 1), "capslock": bool(leds & 2),
                "scrolllock": bool(leds & 4), "raw": p.hex(" ")}

    def config(self):
        p = self.xfer(CMD_GET_PARA_CFG)
        return {"baud": int.from_bytes(p[3:7], "big"),
                "vid": "%04x" % int.from_bytes(p[11:13], "little"),
                "pid": "%04x" % int.from_bytes(p[13:15], "little"), "raw": p.hex(" ")}

    def usb(self, action):
        code = {"host": 0x00, "target": 0x01, "status": 0x03}[action]
        p = self.xfer(CMD_USB_SWITCH, bytes([0, 0, 0, 0, code]))
        return p


def find_port():
    env = os.environ.get("MINIKVM_PORT")
    if env:
        return env
    for port in sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*")):
        try:
            bridge = Bridge(port)
        except OSError:
            continue
        try:
            bridge.xfer(CMD_GET_INFO, timeout=0.3)
            return port
        except KvmError:
            continue
        finally:
            bridge.close()
    raise KvmError("no Mini-KVM serial bridge found (looked at /dev/cu.usbmodem*); "
                   "set MINIKVM_PORT or pass --port")


def grab_frame(path, device, size, timeout):
    """One frame through ffmpeg. The first frames after open are often stale, so skip some.

    The MS2109 sends full-range YUV; ffmpeg assumes limited range and stretches it, which
    clipped 6.4 per cent of a Windows desktop to white and 5.5 per cent to black
    (measured 25 September 2026), so the range is set explicitly."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "avfoundation",
           "-framerate", "30", "-video_size", size, "-i", device,
           "-vf", "select=gte(n\\,5),scale=in_range=full:out_range=full",
           "-frames:v", "1", path]
    started = time.time()
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise KvmError("ffmpeg gave no frame in %ds. A capture that hangs rather than fails "
                       "is a Camera consent prompt waiting on the Mac's own screen." % timeout)
    if done.returncode != 0:
        raise KvmError("ffmpeg: " + done.stderr.strip())
    return time.time() - started


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", help="serial device; default: probe /dev/cu.usbmodem*")
    sub = ap.add_subparsers(dest="verb", required=True)
    sub.add_parser("info")
    p = sub.add_parser("frame")
    p.add_argument("path")
    p.add_argument("--device", default="Openterface")
    p.add_argument("--size", default="1920x1080")
    p.add_argument("--timeout", type=int, default=20)
    p = sub.add_parser("type")
    p.add_argument("text", nargs="?")
    p.add_argument("--stdin", action="store_true", help="read the text from stdin")
    p.add_argument("--enter", action="store_true")
    p.add_argument("--layout", choices=sorted(LAYOUTS),
                   help="the BOX's console keymap, default us, required with --stdin; "
                        "firmware setup and GRUB usually read it as us")
    p.add_argument("--delay", type=float, default=0.012, help="seconds between keys")
    p = sub.add_parser("key")
    p.add_argument("chord", nargs="+")
    p = sub.add_parser("mouse")
    p.add_argument("action", choices=["abs", "rel", "click"])
    p.add_argument("args", nargs="*")
    p.add_argument("--screen", default="1920x1080")
    p = sub.add_parser("usb")
    p.add_argument("action", choices=["status", "host", "target"])
    args = ap.parse_args()
    if args.verb == "type" and args.stdin and not args.layout:
        # Piped text is usually a password, and one typed with the wrong keymap fails as
        # "Login incorrect" with nothing to show why. Make the caller name the box's keymap.
        ap.error("type --stdin needs --layout (the box's console keymap: %s)" % ", ".join(sorted(LAYOUTS)))
    text = None
    if args.verb == "type":
        text = sys.stdin.read().rstrip("\n") if args.stdin else args.text
        if text is None:
            ap.error("type needs text or --stdin")
        if args.stdin and not text:
            # A password fetch that failed pipes nothing, and typing "" then Enter would
            # submit an empty password. Refuse before the port is opened.
            ap.error("nothing arrived on stdin; nothing was typed")

    try:
        if args.verb == "frame":
            took = grab_frame(args.path, args.device, args.size, args.timeout)
            print("%s  %.2fs" % (args.path, took))
            return 0
        bridge = Bridge(args.port or find_port())
        try:
            if args.verb == "info":
                print("port      ", bridge.port)
                for name, value in list(bridge.info().items()) + list(bridge.config().items()):
                    print("%-10s %s" % (name, value))
                print("usb-a      %s" % bridge.usb("status").hex(" "))
            elif args.verb == "type":
                bridge.type_text(text, args.delay, secret=args.stdin, layout=args.layout or "us")
                if args.enter:
                    bridge.chord("enter")
            elif args.verb == "key":
                for chord in args.chord:
                    bridge.chord(chord)
            elif args.verb == "mouse":
                if args.action == "click":
                    bridge.click(args.args[0] if args.args else "left")
                else:
                    x, y = int(args.args[0]), int(args.args[1])
                    if args.action == "abs":
                        w, h = (int(v) for v in args.screen.split("x"))
                        bridge.mouse_abs(x, y, w, h)
                    else:
                        bridge.mouse_rel(x, y)
            elif args.verb == "usb":
                print(bridge.usb(args.action).hex(" "))
        finally:
            bridge.close()
    except KvmError as err:
        print("minikvm: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
