#!/usr/bin/env python3
"""System Settings: a macOS Sequoia-style settings app for Hyprland (GTK 3).

  system-settings.py [wifi|bluetooth|sound|displays|battery|appearance]

Copyright (c) 2026 Parashar Khangembam. MIT licence, see LICENSE.
Written with help from Claude (Anthropic).
"""
import getpass
import glob
import json
import os
import shutil
import subprocess
import sys
import threading

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

TOKENS = os.path.expanduser("~/.config/macos/tokens.json")
MX_CSS = os.path.expanduser("~/.config/macos/css/system-settings.css")
PIDFILE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "macos-settings.pid")
H = os.path.expanduser("~/.config/hypr")

CSS = b"""
* { font-family: "SF Pro Text", "Inter", "Cantarell", sans-serif; font-size: 13px; }
window.ss { background-color: #1E1E1E; color: rgba(255,255,255,0.88); }
window.ss label { color: rgba(255,255,255,0.88); }
window.ss image { color: rgba(255,255,255,0.80); }
window.ss entry { color: #FFFFFF; caret-color: #FFFFFF; }
.ss-side { background-color: rgba(255,255,255,0.04); border-right: 1px solid rgba(255,255,255,0.08); }
.ss-side list { background: none; }
.ss-side row { padding: 4px 8px; margin: 1px 8px; border-radius: 6px; }
.ss-side row:selected { background-color: #0A84FF; }
window.ss .ss-side row:selected label { color: #FFFFFF; }
.ss-user { padding: 10px 14px; }
.ss-user-name { font-weight: 600; }
.ss-ico { border-radius: 6px; min-width: 22px; min-height: 22px; }
window.ss .ss-ico image, .ss-ico image { color: #FFFFFF; }
.ico-blue { background-color: #0A84FF; } .ico-red { background-color: #FF453A; }
.ico-green { background-color: #30D158; } .ico-grey { background-color: #636366; }
.ico-indigo { background-color: #5E5CE6; } .ico-orange { background-color: #FF9F0A; }
.ss-title { font-size: 17px; font-weight: 700; padding: 14px 20px 6px 20px; }
window.ss .ss-head, .ss-head { color: rgba(255,255,255,0.55); font-size: 11px; font-weight: 600; padding: 12px 24px 4px 24px; }
.ss-group { background-color: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 10px; margin: 4px 20px; }
.ss-row { padding: 8px 12px; min-height: 24px; }
.ss-group separator { background-color: rgba(255,255,255,0.08); min-height: 1px; margin: 0 12px; }
window.ss .ss-sub, .ss-sub { color: rgba(255,255,255,0.55); font-size: 11px; }
button.ss-btn { background-image: none; background-color: rgba(255,255,255,0.12); border: none;
                box-shadow: none; border-radius: 6px; padding: 2px 12px; min-height: 20px; color: #FFFFFF; }
button.ss-btn:hover { background-color: rgba(255,255,255,0.20); }
button.ss-btn.blue { background-color: #0A84FF; }
switch { background-image: none; border-radius: 12px; border: none; background-color: rgba(255,255,255,0.22); }
switch:checked { background-color: #0A84FF; }
switch slider { background-image: none; border-radius: 11px; border: none; background-color: #FFFFFF; min-width: 20px; min-height: 20px; }
scale trough { background-image: none; min-height: 4px; border-radius: 2px; border: none; background-color: rgba(255,255,255,0.18); }
scale highlight { background-image: none; border-radius: 2px; background-color: #0A84FF; }
scale slider { background-image: none; min-width: 18px; min-height: 18px; border-radius: 9px; border: none; background-color: #FFFFFF; box-shadow: 0 1px 3px rgba(0,0,0,0.5); }
entry { background-image: none; background-color: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.15); border-radius: 6px; color: #FFFFFF; }
.swatch { border-radius: 50%; min-width: 18px; min-height: 18px; border: 2px solid transparent; padding: 0; }
.swatch.on { border-color: #FFFFFF; }
"""

PANES = [("wifi", "Wi-Fi", "network-wireless-signal-excellent-symbolic", "ico-blue"),
         ("bluetooth", "Bluetooth", "bluetooth-active-symbolic", "ico-blue"),
         ("sound", "Sound", "audio-volume-high-symbolic", "ico-red"),
         ("displays", "Displays", "video-display-symbolic", "ico-blue"),
         ("battery", "Battery", "battery-full-symbolic", "ico-green"),
         ("appearance", "Appearance", "preferences-desktop-appearance-symbolic", "ico-grey")]

ACCENTS = [("Blue", "#0A84FF"), ("Purple", "#BF5AF2"), ("Pink", "#FF375F"), ("Red", "#FF453A"),
           ("Orange", "#FF9F0A"), ("Yellow", "#FFD60A"), ("Green", "#30D158"), ("Graphite", "#8E8E93")]


def sh(cmd, timeout=10):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ""


def secret(args, text, timeout=40):
    """Run a command and type `text` into it, so passwords never appear in `ps`."""
    try:
        return subprocess.run(args, input=text + "\n", capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def spawn(cmd):
    subprocess.Popen(cmd, shell=True, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def q(s):
    return "'" + s.replace("'", "'\\''") + "'"


class Settings(Gtk.Window):
    def __init__(self, pane):
        super().__init__(title="System Settings")
        self.get_style_context().add_class("ss")
        self.set_default_size(820, 580)
        self.set_position(Gtk.WindowPosition.CENTER)
        for data, prio in ((CSS, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1),):
            p = Gtk.CssProvider()
            p.load_from_data(data)
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p, prio)
        if os.path.exists(MX_CSS):
            p = Gtk.CssProvider()
            try:
                p.load_from_path(MX_CSS)
                Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), p,
                                                         Gtk.STYLE_PROVIDER_PRIORITY_USER + 2)
            except GLib.Error:
                pass
        self.connect("destroy", Gtk.main_quit)
        self.connect("key-press-event", lambda w, e: self.destroy() if (
            e.keyval == Gdk.KEY_w and e.state & (Gdk.ModifierType.SUPER_MASK | Gdk.ModifierType.CONTROL_MASK)) else None)

        outer = Gtk.Box()
        self.add(outer)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        side.get_style_context().add_class("ss-side")
        side.set_size_request(220, -1)
        search = Gtk.SearchEntry(placeholder_text="Search", margin=10)
        side.pack_start(search, False, False, 0)
        user = Gtk.Box(spacing=10)
        user.get_style_context().add_class("ss-user")
        av = Gtk.Image.new_from_icon_name("avatar-default-symbolic", Gtk.IconSize.DND)
        av.set_pixel_size(32)
        user.pack_start(av, False, False, 0)
        ub = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        un = Gtk.Label(label=getpass.getuser().title(), xalign=0)
        un.get_style_context().add_class("ss-user-name")
        us = Gtk.Label(label="This Computer", xalign=0)
        us.get_style_context().add_class("ss-sub")
        ub.pack_start(un, False, False, 0)
        ub.pack_start(us, False, False, 0)
        user.pack_start(ub, False, False, 0)
        side.pack_start(user, False, False, 0)
        self.list = Gtk.ListBox()
        self.rows = {}
        for key, name, icon, color in PANES:
            if key == "appearance" and not shutil.which("macos-apply"):
                continue  # Appearance drives the macos-apply theme engine; skip it without one
            row = Gtk.ListBoxRow()
            b = Gtk.Box(spacing=8)
            ico = Gtk.Box()
            ico.get_style_context().add_class("ss-ico")
            ico.get_style_context().add_class(color)
            im = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU)
            im.set_pixel_size(14)
            ico.set_size_request(22, 22)
            ico.set_center_widget(im)
            b.pack_start(ico, False, False, 0)
            b.pack_start(Gtk.Label(label=name, xalign=0), True, True, 0)
            row.add(b)
            row.key, row.name = key, name
            self.list.add(row)
            self.rows[key] = row
        self.list.connect("row-selected", lambda lb, r: r and self.show_pane(r.key))
        search.connect("search-changed", lambda e: self.list.set_filter_func(
            lambda r, t=e.get_text().lower(): t in r.name.lower()))
        side.pack_start(self.list, True, True, 0)
        outer.pack_start(side, False, False, 0)

        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        outer.pack_start(self.scroll, True, True, 0)
        self.pane = None
        self.show_all()
        self.list.select_row(self.rows.get(pane, self.rows["wifi"]))

    # ------------------------------------------------------------ building blocks
    def show_pane(self, key):
        self.pane = key
        for c in self.scroll.get_children():
            self.scroll.remove(c)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_bottom=20)
        t = Gtk.Label(label=dict((k, n) for k, n, *_ in PANES)[key], xalign=0)
        t.get_style_context().add_class("ss-title")
        self.body.pack_start(t, False, False, 0)
        getattr(self, f"pane_{key}")()
        self.scroll.add(self.body)
        self.scroll.show_all()

    def reload(self, ms=600):
        GLib.timeout_add(ms, lambda: (self.show_pane(self.pane), False)[1])

    def head(self, text):
        lab = Gtk.Label(label=text, xalign=0)
        lab.get_style_context().add_class("ss-head")
        self.body.pack_start(lab, False, False, 0)

    def group(self, rows):
        g = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        g.get_style_context().add_class("ss-group")
        for i, r in enumerate(rows):
            if i:
                g.pack_start(Gtk.Separator(), False, False, 0)
            g.pack_start(r, False, False, 0)
        self.body.pack_start(g, False, False, 0)

    def row(self, label, right=None, sub=None, icon=None):
        b = Gtk.Box(spacing=10)
        b.get_style_context().add_class("ss-row")
        if icon:
            im = Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU)
            b.pack_start(im, False, False, 0)
        tb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        lab = Gtk.Label(label=label, xalign=0)
        lab.set_ellipsize(3)
        tb.pack_start(lab, False, False, 0)
        if sub:
            s = Gtk.Label(label=sub, xalign=0)
            s.get_style_context().add_class("ss-sub")
            tb.pack_start(s, False, False, 0)
        b.pack_start(tb, True, True, 0)
        if right is not None:
            if isinstance(right, (list, tuple)):
                for w in reversed(right):
                    b.pack_end(w, False, False, 0)
            else:
                right.set_valign(Gtk.Align.CENTER)
                b.pack_end(right, False, False, 0)
        return b

    def switch(self, on, cb):
        s = Gtk.Switch(active=on, valign=Gtk.Align.CENTER)
        s.connect("notify::active", lambda w, _p: cb(w.get_active()))
        return s

    def button(self, text, cb, blue=False):
        b = Gtk.Button(label=text, valign=Gtk.Align.CENTER)
        b.get_style_context().add_class("ss-btn")
        if blue:
            b.get_style_context().add_class("blue")
        b.connect("clicked", lambda *_: cb())
        return b

    def slider(self, value, cb, lo=0, hi=100, width=240):
        s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
        s.set_draw_value(False)
        s.set_value(value)
        s.set_size_request(width, -1)
        s.connect("value-changed", lambda w: cb(w.get_value()))
        return s

    def note(self, text):
        lab = Gtk.Label(label=text, xalign=0)
        lab.get_style_context().add_class("ss-sub")
        lab.set_line_wrap(True)
        lab.set_margin_start(24)
        lab.set_margin_end(24)
        self.body.pack_start(lab, False, False, 4)

    def busy(self, fn, after_ms=300):
        def work():
            fn()
            GLib.idle_add(lambda: (self.reload(after_ms), False)[1])
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ Wi-Fi
    def pane_wifi(self):
        on = sh("nmcli radio wifi").strip() == "enabled"
        self.group([self.row("Wi-Fi", self.switch(on, lambda v: (sh(f"nmcli radio wifi {'on' if v else 'off'}"),
                                                                  self.reload(900))),
                             icon="network-wireless-signal-excellent-symbolic")])
        if not on:
            return
        nets, seen = [], set()
        for line in sh("nmcli -t -f IN-USE,SSID,SIGNAL,SECURITY dev wifi list --rescan no").splitlines():
            p = [x.replace("\x00", ":") for x in line.replace("\\:", "\x00").split(":")]
            if len(p) >= 4 and p[1] and p[1] not in seen:
                seen.add(p[1])
                nets.append({"ssid": p[1], "on": p[0] == "*", "sig": int(p[2] or 0), "sec": p[3] not in ("", "--")})
        saved = [l.rsplit(":", 1)[0] for l in sh("nmcli -t -f NAME,TYPE con show").splitlines()
                 if l.endswith(":802-11-wireless")]
        cur = [n for n in nets if n["on"]]
        if cur:
            n = cur[0]
            self.group([self.row(n["ssid"], self.button("Disconnect", lambda: self.busy(
                lambda: sh("nmcli dev disconnect $(nmcli -t -f DEVICE,TYPE dev | grep ':wifi$' | cut -d: -f1 | head -1)"))),
                sub="Connected", icon=self.sig(n["sig"]))])
        self.head("Known Networks")
        known = [s for s in saved if not (cur and s == cur[0]["ssid"])]
        self.group([self.row(s, [self.button("Connect", lambda s=s: self.busy(lambda: sh(f"nmcli con up id {q(s)}", 30))),
                                 self.button("Forget", lambda s=s: self.busy(lambda: sh(f"nmcli con delete id {q(s)}")))],
                             icon="network-wireless-symbolic") for s in known] or [self.row("No other known networks")])
        self.head("Other Networks")
        others = [n for n in nets if not n["on"] and n["ssid"] not in saved]
        rows = []
        for n in others[:12]:
            entry = Gtk.Entry(visibility=False, placeholder_text="Password", width_chars=14) if n["sec"] else None
            def go(n=n, e=entry):
                if e:  # the password goes to nmcli on stdin, never on the command line
                    self.busy(lambda: secret(["nmcli", "--ask", "dev", "wifi", "connect", n["ssid"]], e.get_text()), 600)
                else:
                    self.busy(lambda: sh(f"nmcli dev wifi connect {q(n['ssid'])}", 40), 600)
            if entry:
                entry.connect("activate", lambda *_ , g=go: g())
            rows.append(self.row(n["ssid"], [w for w in (entry, self.button("Join", go)) if w],
                                 icon=self.sig(n["sig"])))
        self.group(rows or [self.row("Searching…")])
        bar = Gtk.Box(margin_start=20, margin_top=8)
        bar.pack_start(self.button("Scan", lambda: self.busy(lambda: sh("nmcli dev wifi rescan; sleep 3"), 100)), False, False, 0)
        self.body.pack_start(bar, False, False, 0)

    @staticmethod
    def sig(s):
        return "network-wireless-signal-" + ("excellent" if s >= 75 else "good" if s >= 50 else "ok" if s >= 25 else "weak") + "-symbolic"

    # -------------------------------------------------------------- Bluetooth
    def pane_bluetooth(self):
        on = "Powered: yes" in sh("bluetoothctl show")
        self.group([self.row("Bluetooth", self.switch(on, lambda v: (sh(f"bluetoothctl power {'on' if v else 'off'}"),
                                                                      self.reload(1200))),
                             sub="This computer is discoverable as “" + sh("hostname").strip() + "”" if on else None,
                             icon="bluetooth-active-symbolic")])
        if not on:
            return
        paired = []
        for line in (sh("bluetoothctl devices Paired") or "").splitlines():
            p = line.split(" ", 2)
            if len(p) == 3 and p[0] == "Device":
                info = sh(f"bluetoothctl info {p[1]}")
                batt = next((l.split("(")[-1].rstrip(")") for l in info.splitlines() if "Battery Percentage" in l), None)
                paired.append((p[1], p[2], "Connected: yes" in info, batt))
        self.head("My Devices")
        self.group([self.row(name, [self.button("Disconnect" if c else "Connect", lambda m=mac, c=c: self.busy(
                        lambda: sh(f"bluetoothctl {'disconnect' if c else 'connect'} {m}", 25), 500)),
                                    self.button("Forget", lambda m=mac: self.busy(lambda: sh(f"bluetoothctl remove {m}")))],
                             sub=("Connected" + (f" · {b}%" if b else "")) if c else "Not Connected",
                             icon="audio-headphones-symbolic") for mac, name, c, b in paired]
                   or [self.row("No devices")])
        self.head("Nearby Devices")
        pmacs = {m for m, *_ in paired}
        near = [l.split(" ", 2) for l in sh("bluetoothctl devices").splitlines()]
        near = [(p[1], p[2]) for p in near if len(p) == 3 and p[1] not in pmacs and p[2].replace("-", ":") != p[1]]
        self.group([self.row(n, self.button("Connect", lambda m=m: self.busy(
            lambda: sh(f"bluetoothctl pair {m}; bluetoothctl trust {m}; bluetoothctl connect {m}", 40), 500)),
            icon="bluetooth-symbolic") for m, n in near[:10]] or [self.row("Press Search to look for devices")])
        bar = Gtk.Box(margin_start=20, margin_top=8)
        bar.pack_start(self.button("Search", lambda: self.busy(lambda: sh("bluetoothctl --timeout 8 scan on", 12), 100)), False, False, 0)
        self.body.pack_start(bar, False, False, 0)

    # ------------------------------------------------------------------ Sound
    def pane_sound(self):
        def vol(target):
            out = sh(f"wpctl get-volume {target}")
            try:
                return float(out.split()[1]) * 100, "MUTED" in out
            except (IndexError, ValueError):
                return 50.0, False
        v, m = vol("@DEFAULT_AUDIO_SINK@")
        self.group([self.row("Output volume", self.slider(v, lambda x: spawn(
                        f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {x / 100:.2f}"))),
                    self.row("Mute", self.switch(m, lambda on: sh(f"wpctl set-mute @DEFAULT_AUDIO_SINK@ {int(on)}")))])
        for kind, title, cmd in (("sinks", "Output", "set-default-sink"), ("sources", "Input", "set-default-source")):
            try:
                devs = json.loads(sh(f"pactl -f json list {kind}") or "[]")
            except ValueError:
                devs = []
            default = sh(f"pactl get-default-{kind[:-1]}").strip()
            devs = [d for d in devs if ".monitor" not in d.get("name", "")]
            self.head(title)
            self.group([self.row(d.get("description", d.get("name", "")),
                                 Gtk.Image.new_from_icon_name("object-select-symbolic", Gtk.IconSize.MENU)
                                 if d.get("name") == default else
                                 self.button("Use", lambda n=d.get("name", ""), c=cmd: (sh(f"pactl {c} {q(n)}"), self.reload(300))))
                        for d in devs] or [self.row("No devices")])
        iv, _ = vol("@DEFAULT_AUDIO_SOURCE@")
        self.group([self.row("Input volume", self.slider(iv, lambda x: spawn(
            f"wpctl set-volume @DEFAULT_AUDIO_SOURCE@ {x / 100:.2f}")))])

    # --------------------------------------------------------------- Displays
    def pane_displays(self):
        mon = next((m for m in json.loads(sh("hyprctl monitors -j") or "[]") or [] if m.get("focused")), {})
        if mon:
            self.group([self.row(mon.get("description") or mon.get("name", "Display"),
                                 sub=f"{mon.get('width')} × {mon.get('height')} · {round(mon.get('refreshRate', 60))} Hz · scale {mon.get('scale')}",
                                 icon="video-display-symbolic")])
        rows = []
        b = sh("brightnessctl -m").strip().split(",")
        if len(b) >= 4 and b[3].endswith("%"):
            rows.append(self.row("Brightness", self.slider(float(b[3][:-1]), lambda x: spawn(
                f"brightnessctl -q set {max(1, int(x))}%"))))
        night = f"{H}/toggle-nightshift.sh"
        if os.path.exists(night) or shutil.which("wlsunset"):
            def toggle(on):
                if os.path.exists(night):
                    spawn(night)
                elif on:
                    spawn("wlsunset -t 4000 -T 6500")
                else:
                    sh("pkill -x wlsunset")
                self.reload(900)
            rows.append(self.row("Night Shift", self.switch(bool(sh("pgrep -x wlsunset").strip()), toggle),
                                 sub="Warmer colours after sunset"))
        if rows:
            self.group(rows)

    # ---------------------------------------------------------------- Battery
    def pane_battery(self):
        bats = glob.glob("/sys/class/power_supply/BAT*")
        if bats:
            cap = (open(f"{bats[0]}/capacity").read().strip() if os.path.exists(f"{bats[0]}/capacity") else "?")
            st = (open(f"{bats[0]}/status").read().strip() if os.path.exists(f"{bats[0]}/status") else "")
            self.group([self.row("Battery Level", Gtk.Label(label=f"{cap}%"), sub=st, icon="battery-full-symbolic")])
        prof = sh("powerprofilesctl get").strip()
        if prof:
            self.head("Energy Mode")
            names = [("power-saver", "Low Power"), ("balanced", "Automatic"), ("performance", "High Power")]
            self.group([self.row(n, Gtk.Image.new_from_icon_name("object-select-symbolic", Gtk.IconSize.MENU)
                                 if k == prof else self.button("Use", lambda k=k: (sh(f"powerprofilesctl set {k}"), self.reload(300))))
                        for k, n in names])

    # ------------------------------------------------------------- Appearance
    def tokens(self):
        try:
            return json.load(open(TOKENS))
        except (OSError, ValueError):
            return {}

    def set_token(self, sec, key, val):
        t = self.tokens()
        t.setdefault(sec, {})[key] = val
        json.dump(t, open(TOKENS, "w"), indent=2, ensure_ascii=False)
        self.applying.set_text("Applying…")
        def done():
            sh("macos-apply >/dev/null 2>&1", 120)
            GLib.idle_add(lambda: (self.applying.set_text("Applied to the whole desktop"), False)[1])
        threading.Thread(target=done, daemon=True).start()

    def pane_appearance(self):
        t = self.tokens()
        cur = t.get("color", {}).get("accent", "#0A84FF").upper()
        sw = Gtk.Box(spacing=8)
        for name, col in ACCENTS:
            b = Gtk.Button(tooltip_text=name)
            b.set_size_request(22, 22)
            b.set_valign(Gtk.Align.CENTER)
            b.get_style_context().add_class("swatch")
            if col.upper() == cur:
                b.get_style_context().add_class("on")
            prov = Gtk.CssProvider()
            prov.load_from_data(f"button {{ background-image: none; background-color: {col}; }}".encode())
            b.get_style_context().add_provider(prov, Gtk.STYLE_PROVIDER_PRIORITY_USER + 3)
            b.connect("clicked", lambda *_, c=col: (self.set_token("color", "accent", c), self.reload(200)))
            sw.pack_start(b, False, False, 0)
        size = int(t.get("dock", {}).get("icon_size", 48))
        dock = self.slider(size, lambda x: None, 32, 80, 200)
        dock.connect("button-release-event", lambda w, e: (self.set_token("dock", "icon_size", int(w.get_value())), False)[1])
        self.group([self.row("Accent colour", sw), self.row("Dock size", dock, sub=f"{size} px icons")])
        self.applying = Gtk.Label(label="", xalign=0)
        self.applying.get_style_context().add_class("ss-sub")
        self.applying.set_margin_start(24)
        self.body.pack_start(self.applying, False, False, 6)
        self.note("Changes are saved to ~/.config/macos/tokens.json and applied by macos-apply.")


def main():
    pane = sys.argv[1] if len(sys.argv) > 1 else "wifi"
    try:
        os.kill(int(open(PIDFILE).read()), 15)          # one window: reopen on the asked pane
    except (OSError, ValueError):
        pass
    open(PIDFILE, "w").write(str(os.getpid()))
    Settings(pane)
    Gtk.main()


if __name__ == "__main__":
    main()
