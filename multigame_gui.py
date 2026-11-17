"""Batch front end for explicit mod conversion routes.

A tabbed, dark Tkinter UI: one tab per source game, each with its own input
queue, a live checklist of the configuration that game needs, a drop zone,
and a shared activity log. Uses only Tk canvases (no extra dependencies).
"""
import ctypes
import datetime
import json
import math
import os
from pathlib import Path
import queue
import re
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font as tkfont

from tkinterdnd2 import TkinterDnD, DND_FILES

from multigame import convert, inspect, ROOT

# --------------------------------------------------------------------------- theme

C = {
    'base': '#0b0f17', 'surface': '#121825', 'raised': '#1a2232', 'field': '#0e131d',
    'border': '#222b3d', 'border_hi': '#334058', 'text': '#e9eef8', 'muted': '#8a95ab',
    'faint': '#5a6479', 'ok': '#3ddc97', 'bad': '#ff5d6c', 'warn': '#ffb648', 'json': '#a7b8d6',
}

GAMES = [
    {'key': 'rivals', 'name': 'Marvel Rivals', 'mark': 'MR', 'accent': '#ff4d5e', 'guide': 'marvel-rivals',
     'blurb': 'Unreal IoStore packages. Every .utoc found in a file or folder becomes its own FBX job, '
              'with textures exported beside it.',
     'accepts': '.utoc  ·  .ucas  ·  .pak  ·  mod folders',
     'needs': [('blender', 'Blender', True), ('game', 'Game Paks', True), ('mappings', 'Mappings', False)],
     'types': [('Rivals packages', '*.pak *.utoc *.ucas')]},
    {'key': 'deadlock', 'name': 'Deadlock', 'mark': 'DL', 'accent': '#e8b04b', 'guide': 'deadlock',
     'blurb': 'Source 2 VPK mods. Compiled models are pulled out with Source 2 Viewer, then rebuilt and '
              'rigged in Blender.',
     'accepts': '.vpk  (keep companion chunks beside it)',
     'needs': [('blender', 'Blender', True), ('vrf', 'Source 2 Viewer CLI', True), ('gameinfo', 'gameinfo.gi', True)],
     'types': [('Deadlock VPK', '*.vpk')]},
    {'key': 'zzz', 'name': 'Zenless Zone Zero', 'mark': 'ZZZ', 'accent': '#b8ef3f', 'guide': 'zzz',
     'blurb': 'INI/buffer mods, rebuilt against a matching reference dump, skeleton and bone map so the '
              'result is properly rigged.',
     'accepts': 'mod folders with the .ini and its buffers',
     'needs': [('blender', 'Blender', True), ('reference', 'Reference dump', True),
               ('base_fbx', 'Base FBX', True), ('bone_map', 'Bone map', True)],
     'types': [('ZZZ mod files', '*.ini *.ib *.vb0 *.fmt')]},
    {'key': 'koikatsu', 'name': 'Koikatsu', 'mark': 'KK', 'accent': '#ff7ac0', 'guide': 'koikatsu', 'card': True,
     'blurb': 'Character cards, KKBP model.pmx exports, prepared .blend files and Studio FBX Bridge '
              'manifests. Sunshine cards can be converted to KK cards.',
     'accepts': '.png card  ·  .pmx  ·  .blend  ·  .studio.json',
     'needs': [('blender', 'Blender', True), ('kkbp_blender', 'KKBP Blender', False),
               ('koikatsu_mods', 'Mods folder', False)],
     'types': [('Koikatsu inputs', '*.png *.pmx *.blend *.studio.json')]},
]
ALL_TYPES = '*.pak *.utoc *.ucas *.vpk *.png *.blend *.pmx *.studio.json *.ini'

FONTS = {}
ICON = {}
S = 1.0


def px(n):
    return int(round(n * S))


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def ease(t):
    return 1 - (1 - t) ** 3


def round_rect(cv, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


def dpi_aware():
    if sys.platform != 'win32':
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def dark_titlebar(win, color=C['base']):
    """Windows 10/11: dark caption and, on 11, a caption colour matching the app."""
    if sys.platform != 'win32':
        return
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), 4)
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
        cref = ctypes.c_int(b << 16 | g << 8 | r)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cref), 4)
    except Exception:
        pass


def load_fonts(root):
    fam = set(tkfont.families(root))
    pick = lambda names, fallback: next((n for n in names if n in fam), fallback)
    ui = pick(('Segoe UI Variable Text', 'Segoe UI'), 'TkDefaultFont')
    disp = pick(('Segoe UI Variable Display', 'Segoe UI'), ui)
    mono = pick(('Cascadia Mono', 'Cascadia Code', 'Consolas'), 'TkFixedFont')
    icon = pick(('Segoe Fluent Icons', 'Segoe MDL2 Assets'), None)
    F = lambda family, size, weight='normal': tkfont.Font(root=root, family=family, size=size, weight=weight)
    FONTS.update(
        title=F(disp, 16, 'bold'), hero=F(disp, 22, 'bold'), mark=F(disp, 64, 'bold'),
        h3=F(ui, 11, 'bold'), body=F(ui, 10), small=F(ui, 9), small_b=F(ui, 9, 'bold'),
        eyebrow=F(ui, 8, 'bold'), tab=F(ui, 10), tab_b=F(ui, 10, 'bold'), badge=F(ui, 8, 'bold'),
        btn=F(ui, 10, 'bold'), mono=F(mono, 9),
        icon=F(icon, 11) if icon else None, icon_lg=F(icon, 22) if icon else None)
    glyphs = {'file': '', 'folder': '', 'search': '', 'play': '',
              'swap': '', 'delete': '', 'clear': '', 'edit': '',
              'open': '', 'upload': '', 'link': '', 'book': ''}
    ICON.update({k: (v if icon else '') for k, v in glyphs.items()})


class Anim:
    """Tiny tween runner: one job per key, a new run on a key replaces the old one."""

    def __init__(self, widget):
        self.w, self.jobs = widget, {}

    def run(self, key, ms, step, done=None):
        self.cancel(key)
        start = time.perf_counter()

        def tick():
            t = min(1.0, (time.perf_counter() - start) * 1000 / ms)
            step(ease(t))
            if t < 1:
                self.jobs[key] = self.w.after(15, tick)
            else:
                self.jobs.pop(key, None)
                if done:
                    done()
        tick()

    def cancel(self, key):
        job = self.jobs.pop(key, None)
        if job:
            self.w.after_cancel(job)

    def active(self, key):
        return key in self.jobs


# --------------------------------------------------------------------------- widgets

class Button(tk.Canvas):
    def __init__(self, master, text, command, style='secondary', icon=None, accent='#4d8dff', height=36, padx=16):
        self.bg = master['bg']
        self.text, self.command, self.style, self.accent = text, command, style, accent
        self.icon = ICON.get(icon) if icon else ''
        f = FONTS['btn']
        iw = FONTS['icon'].measure(self.icon) + px(8) if self.icon else 0
        super().__init__(master, width=f.measure(text) + iw + px(padx) * 2, height=px(height), bg=self.bg,
                         highlightthickness=0, bd=0, cursor='hand2')
        self.enabled, self.h, self.pressed = True, 0.0, False
        self.anim = Anim(self)
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Enter>', lambda e: self._hover(1))
        self.bind('<Leave>', lambda e: (setattr(self, 'pressed', False), self._hover(0)))
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)

    def _hover(self, target):
        if not self.enabled:
            return
        start = self.h
        self.anim.run('h', 140, lambda t: (setattr(self, 'h', start + (target - start) * t), self.draw()))

    def _press(self, _):
        if self.enabled:
            self.pressed = True
            self.draw()

    def _release(self, e):
        was = self.pressed
        self.pressed = False
        self.draw()
        if was and self.enabled and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.command()

    def set_accent(self, color):
        self.accent = color
        self.draw()

    def set_enabled(self, on):
        self.enabled = on
        self.h = 0.0
        self.configure(cursor='hand2' if on else 'arrow')
        self.draw()

    def draw(self):
        self.delete('all')
        w, h = self.winfo_width(), int(self['height'])
        if w < 4:
            w = int(self['width'])
        if self.style == 'primary':
            base, hover, fg, outline = self.accent, mix(self.accent, '#ffffff', .18), C['base'], ''
        elif self.style == 'ghost':
            base, hover, fg, outline = self.bg, C['raised'], mix(C['muted'], C['text'], self.h), ''
        else:
            base, hover, fg, outline = C['raised'], C['border_hi'], C['text'], C['border']
        fill = mix(base, hover, self.h)
        if self.pressed:
            fill = mix(fill, C['base'], .25)
        if not self.enabled:
            fill, fg = mix(base, self.bg, .55), C['faint']
            outline = C['border'] if outline else ''
        round_rect(self, 1, 1, w - 1, h - 1, px(8), fill=fill, outline=outline)
        dy = 1 if self.pressed else 0
        tw = FONTS['btn'].measure(self.text)
        iw = FONTS['icon'].measure(self.icon) + px(8) if self.icon else 0
        x = (w - tw - iw) / 2
        if self.icon:
            self.create_text(x, h / 2 + dy + 1, text=self.icon, font=FONTS['icon'], fill=fg, anchor='w')
        self.create_text(x + iw, h / 2 + dy, text=self.text, font=FONTS['btn'], fill=fg, anchor='w')


class TabBar(tk.Canvas):
    def __init__(self, master, app):
        super().__init__(master, height=px(50), bg=C['base'], highlightthickness=0, bd=0)
        self.app, self.active, self.hover = app, 0, None
        self.counts = [0] * len(GAMES)
        self.busy, self.phase = None, 0.0
        self.slots, self.ind = [], None
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Motion>', self._motion)
        self.bind('<Leave>', lambda e: self._set_hover(None))
        self.bind('<Button-1>', self._click)

    def layout(self):
        x, self.slots = px(20), []
        for i, g in enumerate(GAMES):
            w = px(44) + FONTS['tab_b'].measure(g['name'])
            if self.counts[i]:
                w += FONTS['badge'].measure(str(self.counts[i])) + px(20)
            self.slots.append((x, x + w))
            x += w + px(4)

    def _hit(self, x):
        return next((i for i, (a, b) in enumerate(self.slots) if a <= x <= b), None)

    def _motion(self, e):
        self._set_hover(self._hit(e.x))

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.configure(cursor='hand2' if i is not None else '')
            self.draw()

    def _click(self, e):
        i = self._hit(e.x)
        if i is not None and i != self.active:
            self.app.switch(i)

    def set_count(self, i, n):
        self.counts[i] = n
        self.draw()

    def set_busy(self, i):
        self.busy = i
        if i is not None:
            self._pulse()
        else:
            self.draw()

    def _pulse(self):
        if self.busy is None:
            return
        self.phase += .22
        self.draw()
        self.after(40, self._pulse)

    def select(self, i, animate=True):
        self.layout()
        old, self.active = self.ind, i
        (tx1, tx2), tc = self.slots[i], GAMES[i]['accent']
        if not animate or old is None:
            self.ind = [tx1, tx2, tc]
            self.draw()
            return
        ox1, ox2, oc = old

        def step(t):
            self.ind = [ox1 + (tx1 - ox1) * t, ox2 + (tx2 - ox2) * t, mix(oc, tc, t)]
            self.draw()
        self.app.anim.run('tab', 300, step)

    def draw(self):
        self.delete('all')
        self.layout()
        H, W = int(self['height']), self.winfo_width()
        top, bot = px(6), H - px(8)
        cy = (top + bot) / 2
        self.create_line(0, H - 1, W, H - 1, fill=C['border'])
        if self.ind is None or not self.app.anim.active('tab'):
            a, b = self.slots[self.active]
            self.ind = [a, b, GAMES[self.active]['accent']]
        x1, x2, col = self.ind
        for i, (a, b) in enumerate(self.slots):
            if i == self.hover and i != self.active:
                round_rect(self, a, top, b, bot, px(10), fill=C['surface'], outline='')
        round_rect(self, x1, top, x2, bot, px(10), fill=mix(col, C['base'], .87), outline=mix(col, C['base'], .62))
        self.create_rectangle(x1 + px(16), H - px(3), x2 - px(16), H, fill=col, outline='')
        for i, (a, b) in enumerate(self.slots):
            g, act, hov = GAMES[i], i == self.active, i == self.hover
            r = px(4)
            dx = a + px(18)
            if self.busy == i:
                k = .5 + .5 * math.sin(self.phase)
                halo = px(4) + px(5) * k
                self.create_oval(dx - halo, cy - halo, dx + halo, cy + halo, outline='',
                                 fill=mix(g['accent'], C['base'], .55 + .4 * k))
            dot = g['accent'] if act or hov else mix(g['accent'], C['base'], .5)
            self.create_oval(dx - r, cy - r, dx + r, cy + r, fill=dot, outline='')
            tc = C['text'] if act else (mix(C['muted'], C['text'], .65) if hov else C['muted'])
            self.create_text(a + px(32), cy, text=g['name'], anchor='w', fill=tc,
                             font=FONTS['tab_b'] if act else FONTS['tab'])
            if self.counts[i]:
                n = str(self.counts[i])
                bx = a + px(32) + FONTS['tab_b'].measure(g['name']) + px(8)
                bw = FONTS['badge'].measure(n) + px(12)
                round_rect(self, bx, cy - px(9), bx + bw, cy + px(9), px(9), outline='',
                           fill=mix(g['accent'], C['base'], .35) if act else C['raised'])
                self.create_text(bx + bw / 2, cy, text=n, font=FONTS['badge'],
                                 fill=C['base'] if act else C['muted'])


class Hero(tk.Canvas):
    def __init__(self, master, app):
        super().__init__(master, height=px(206), bg=C['surface'], highlightthickness=1,
                         highlightbackground=C['border'], bd=0)
        self.app, self.game, self.prev, self.t = app, None, None, 1.0
        self.chips, self.link_box, self.link_hover = [], None, False
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Motion>', self._motion)
        self.bind('<Leave>', lambda e: self._set_link(False))
        self.bind('<Button-1>', self._click)

    def show(self, game, animate=True):
        self.prev, self.game = self.game, game
        if animate:
            self.app.anim.run('hero', 460, lambda t: (setattr(self, 't', t), self.draw()))
        else:
            self.t = 1.0
            self.draw()

    def _inside(self, box, e):
        return box and box[0] <= e.x <= box[2] and box[1] <= e.y <= box[3]

    def _motion(self, e):
        over_chip = any(self._inside(b, e) for b in self.chips)
        self._set_link(self._inside(self.link_box, e))
        self.configure(cursor='hand2' if self.link_hover or over_chip else '')

    def _set_link(self, on):
        if on != self.link_hover:
            self.link_hover = on
            self.draw()

    def _click(self, e):
        if self._inside(self.link_box, e):
            self.app.open_guide()
        elif any(self._inside(b, e) for b in self.chips):
            self.app.edit_config()

    def draw(self):
        self.delete('all')
        g, W, H, t = self.game, self.winfo_width(), int(self['height']), self.t
        if not g or W < 20:
            return
        acc = g['accent']
        old = self.prev['accent'] if self.prev else acc
        tint = mix(mix(old, acc, t), C['surface'], .8)
        n = 56
        for k in range(n):
            f = min(1.0, (k / (n - 1)) / .7)
            self.create_rectangle(W * k / n, 0, W * (k + 1) / n + 1, H, outline='',
                                  fill=mix(tint, C['surface'], f ** .8))
        self.create_text(W - px(24) + (1 - t) * px(40), H / 2 + px(6), text=g['mark'], anchor='e',
                         font=FONTS['mark'], fill=mix(C['surface'], acc, .13 * t))
        half = H * t / 2
        self.create_rectangle(0, H / 2 - half, px(4), H / 2 + half, fill=acc, outline='')

        x = px(28) + (1 - t) * px(22)
        self.create_text(x, px(22), text='SOURCE GAME', anchor='nw', font=FONTS['eyebrow'],
                         fill=mix(C['surface'], acc, t))
        title = self.create_text(x, px(38), text=g['name'], anchor='nw', font=FONTS['hero'],
                                 fill=mix(C['surface'], C['text'], t))
        y = self.bbox(title)[3] + px(4)
        blurb = self.create_text(x, y, text=g['blurb'], anchor='nw', font=FONTS['body'],
                                 width=max(px(200), W * .72), fill=mix(C['surface'], C['muted'], t))
        y = self.bbox(blurb)[3] + px(6)
        self.create_text(x, y, text='Accepts   ' + g['accepts'], anchor='nw', font=FONTS['small_b'],
                         fill=mix(C['surface'], mix(C['muted'], acc, .35), t))

        lc = acc if self.link_hover else C['muted']
        link = self.create_text(W - px(22), px(22), text='Game instructions  ↗', anchor='ne',
                                font=FONTS['small_b'], fill=mix(C['surface'], lc, t))
        b = self.bbox(link)
        self.link_box = (b[0] - px(6), b[1] - px(4), b[2] + px(6), b[3] + px(4))
        if self.link_hover:
            self.create_line(b[0], b[3], b[2], b[3], fill=acc)

        self.chips = []
        cx, cy = px(28), H - px(38)
        for k, (key, label, required) in enumerate(g['needs']):
            state = self.app.need_state(key, required)
            col, sym = {'ok': (C['ok'], '✓'), 'missing': (C['bad'], '✕'),
                        'optional': (C['warn'], '–'), 'unknown': (C['faint'], '?')}[state]
            text = f'{sym}  {label}' + ('  (optional)' if state == 'optional' else '')
            ct = max(0.0, min(1.0, (t - k * .1) / .55))
            tw = FONTS['small_b'].measure(text) + px(22)
            ox = cx + (1 - ct) * px(10)
            round_rect(self, ox, cy, ox + tw, cy + px(24), px(12),
                       fill=mix(C['surface'], mix(col, C['surface'], .84), ct),
                       outline=mix(C['surface'], mix(col, C['surface'], .5), ct))
            self.create_text(ox + tw / 2, cy + px(12), text=text, font=FONTS['small_b'],
                             fill=mix(C['surface'], col, ct))
            self.chips.append((cx, cy, cx + tw, cy + px(24)))
            cx += tw + px(8)


class DropZone(tk.Canvas):
    def __init__(self, master, app):
        super().__init__(master, height=px(122), bg=master['bg'], highlightthickness=0, bd=0, cursor='hand2')
        self.app, self.h, self.phase, self.dx = app, 0.0, 0.0, 0
        self.hover = self.drag = self.looping = False
        self.link_hover, self.links = None, {}
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self._drop)
        self.dnd_bind('<<DropEnter>>', lambda e: self._drag(True))
        self.dnd_bind('<<DropPosition>>', lambda e: 'copy')
        self.dnd_bind('<<DropLeave>>', lambda e: self._drag(False))
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Enter>', lambda e: self._set(hover=True))
        self.bind('<Leave>', lambda e: (setattr(self, 'link_hover', None), self._set(hover=False)))
        self.bind('<Motion>', self._motion)
        self.bind('<Button-1>', self._click)

    def _drag(self, on):
        self._set(drag=on)
        return 'copy'

    def _drop(self, e):
        self._set(drag=False)
        self.app.add_paths(self.tk.splitlist(e.data))
        return 'copy'

    def _set(self, hover=None, drag=None):
        if hover is not None:
            self.hover = hover
        if drag is not None:
            self.drag = drag
        target = 1.0 if self.drag else (.45 if self.hover else 0.0)
        start = self.h
        self.app.anim.run('dz', 220, lambda t: (setattr(self, 'h', start + (target - start) * t), self.draw()))
        if target > 0 and not self.looping:
            self.looping = True
            self._bob()

    def _bob(self):
        if self.h <= 0.01 and not (self.hover or self.drag):
            self.looping = False
            self.draw()
            return
        self.phase += .16
        self.draw()
        self.after(30, self._bob)

    def shake(self):
        self.app.anim.run('shake', 450, lambda t: (setattr(self, 'dx', math.sin(t * math.pi * 6) * (1 - t) * px(8)),
                                                   self.draw()))

    def draw(self):
        self.delete('all')
        W, H, h, dx = self.winfo_width(), int(self['height']), self.h, self.dx
        if W < 20:
            return
        acc = self.app.accent
        round_rect(self, 1 + dx, 1, W - 2 + dx, H - 2, px(14),
                   fill=mix(C['surface'], mix(acc, C['surface'], .86), h),
                   outline=mix(C['border_hi'], acc, h), dash=(6, 4) if h < .99 else None)
        cx = W / 2 + dx
        bob = math.sin(self.phase) * px(3) * h
        ic = mix(C['muted'], acc, h)
        if ICON['upload']:
            self.create_text(cx, px(34) + bob, text=ICON['upload'], font=FONTS['icon_lg'], fill=ic)
        else:
            self.create_text(cx, px(34) + bob, text='⇩', font=FONTS['hero'], fill=ic)
        main = f'Release to add to {self.app.game["name"]}' if self.drag else 'Drop files or folders here'
        self.create_text(cx, px(70), text=main, font=FONTS['h3'], fill=mix(C['text'], acc, h * .5 if self.drag else 0))
        parts = [('or  ', None), ('Add files', 'files'), ('   ·   ', None), ('Add mod folder', 'folder')]
        total = sum(FONTS['small_b'].measure(p) for p, _ in parts)
        x = cx - total / 2
        self.links = {}
        for text, tag in parts:
            item = self.create_text(x, px(96), text=text, anchor='w', font=FONTS['small_b'],
                                    fill=(mix(acc, '#ffffff', .25) if self.link_hover == tag else acc) if tag else C['muted'])
            x += FONTS['small_b'].measure(text)
            if tag:
                b = self.bbox(item)
                self.links[tag] = (b[0] - px(4), b[1] - px(4), b[2] + px(4), b[3] + px(4))
                if self.link_hover == tag:
                    self.create_line(b[0], b[3] - 1, b[2], b[3] - 1, fill=acc)

    def _motion(self, e):
        hit = next((t for t, (a, b, c, d) in self.links.items() if a <= e.x <= c and b <= e.y <= d), None)
        if hit != self.link_hover:
            self.link_hover = hit
            self.draw()

    def _click(self, e):
        self._motion(e)
        if self.link_hover == 'folder':
            self.app.add_folder()
        else:
            self.app.add_files()


class Progress(tk.Canvas):
    def __init__(self, master, app):
        super().__init__(master, height=px(6), bg=master['bg'], highlightthickness=0, bd=0)
        self.app, self.frac, self.busy, self.phase, self.color = app, 0.0, False, 0.0, None
        self.bind('<Configure>', lambda e: self.draw())

    def set(self, frac):
        start = self.frac
        self.app.anim.run('prog', 450, lambda t: (setattr(self, 'frac', start + (frac - start) * t), self.draw()))

    def start(self):
        self.frac, self.busy = 0.0, True
        self._loop()

    def stop(self, color=None):
        self.busy, self.color = False, color
        self.draw()

    def _loop(self):
        if not self.busy:
            return
        self.phase = (self.phase + .012) % 1
        self.draw()
        self.after(16, self._loop)

    def draw(self):
        self.delete('all')
        W, H = self.winfo_width(), int(self['height'])
        acc = self.color or self.app.accent
        round_rect(self, 0, 0, W, H, H / 2, fill=C['raised'], outline='')
        if self.frac > 0:
            round_rect(self, 0, 0, max(H, W * self.frac), H, H / 2, fill=mix(acc, C['raised'], .15), outline='')
        if self.busy:
            seg = W * .22
            x = self.phase * (W + seg) - seg
            round_rect(self, max(0, x), 0, min(W, x + seg), H, H / 2, fill=mix(acc, '#ffffff', .3), outline='')


class StatusPill(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, width=px(280), height=px(32), bg=master['bg'], highlightthickness=0, bd=0)
        self.text, self.color, self.pulsing, self.phase = 'Ready', C['ok'], False, 0.0
        self.draw()

    def set(self, text, color, pulse=False):
        self.text, self.color = text, color
        if pulse and not self.pulsing:
            self.pulsing = True
            self._loop()
        self.pulsing = pulse
        self.draw()

    def _loop(self):
        if not self.pulsing:
            return
        self.phase = (self.phase + .03) % 1
        self.draw()
        self.after(30, self._loop)

    def draw(self):
        self.delete('all')
        W, H = int(self['width']), int(self['height'])
        tw = FONTS['small_b'].measure(self.text)
        x1 = W - tw - px(40)
        round_rect(self, x1, 1, W - 1, H - 1, H / 2, fill=C['surface'], outline=C['border'])
        cx, cy, r = x1 + px(16), H / 2, px(4)
        if self.pulsing:
            rr = r + px(7) * self.phase
            self.create_oval(cx - rr, cy - rr, cx + rr, cy + rr, outline=mix(self.color, C['surface'], self.phase), width=2)
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=self.color, outline='')
        self.create_text(cx + px(12), cy, text=self.text, anchor='w', font=FONTS['small_b'], fill=C['text'])


class Logo(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, width=px(42), height=px(42), bg=master['bg'], highlightthickness=0, bd=0)

    def draw(self, acc):
        self.delete('all')
        s = int(self['width'])
        round_rect(self, 1, 1, s - 1, s - 1, px(11), fill=C['raised'], outline=mix(acc, C['raised'], .55))
        cx, cy, r = s / 2, s / 2 + px(1), px(11)
        top = [cx, cy - r, cx + r * .87, cy - r / 2, cx, cy, cx - r * .87, cy - r / 2]
        left = [cx - r * .87, cy - r / 2, cx, cy, cx, cy + r, cx - r * .87, cy + r / 2]
        right = [cx + r * .87, cy - r / 2, cx, cy, cx, cy + r, cx + r * .87, cy + r / 2]
        self.create_polygon(top, fill=mix(acc, '#ffffff', .35), outline='')
        self.create_polygon(left, fill=acc, outline='')
        self.create_polygon(right, fill=mix(acc, '#000000', .35), outline='')


# --------------------------------------------------------------------------- app

class App(TkinterDnD.Tk):
    def __init__(self):
        global S
        dpi_aware()
        super().__init__()
        S = self.winfo_fpixels('1i') / 96
        load_fonts(self)
        self.title('Game Model To FBX')
        self.configure(bg=C['base'])
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(px(1220), int(sw * .92)), min(px(880), int(sh * .88))
        self.geometry(f'{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 3)}')
        self.minsize(min(px(980), w), min(px(720), h))

        self.anim = Anim(self)
        self.index = 0
        self.accent = GAMES[0]['accent']
        self.queues = {g['key']: [] for g in GAMES}
        local = ROOT / 'multigame.local.json'
        self.config_path = tk.StringVar(value=str(local) if local.is_file() else '')
        self.output = tk.StringVar(value=str(Path.home() / 'Documents' / 'ConvertedMods'))
        self.config_data, self.config_error = None, None
        self.messages = queue.Queue()
        self.busy, self._deb, self._editor = False, {}, None
        self.entries = []

        self._style()
        self._build()
        self.config_path.trace_add('write', lambda *a: self._debounce('cfg', 250, self.load_config))
        self.load_config()
        self.switch(0, animate=False)
        self.log_line('Pick a game tab, drop in your mods, then Inspect or Convert.', 'muted')
        self.after(60, self.poll)
        self.after(20, lambda: dark_titlebar(self))
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        for i in range(len(GAMES)):
            self.bind_all(f'<Control-Key-{i + 1}>', lambda e, i=i: self.switch(i))
        self.bind_all('<Control-o>', lambda e: self.add_files())
        self.bind_all('<Control-Return>', lambda e: self.start('convert'))

    @property
    def game(self):
        return GAMES[self.index]

    # ---- construction

    def _style(self):
        st = ttk.Style(self)
        st.theme_use('clam')
        st.configure('Q.Treeview', background=C['field'], fieldbackground=C['field'], foreground=C['text'],
                     rowheight=px(30), borderwidth=0, font=FONTS['body'])
        st.layout('Q.Treeview', [('Q.Treeview.treearea', {'sticky': 'nswe'})])
        st.configure('Q.Treeview.Heading', background=C['surface'], foreground=C['muted'], relief='flat',
                     font=FONTS['small_b'], padding=(px(2), px(6)), bordercolor=C['surface'],
                     lightcolor=C['surface'], darkcolor=C['surface'])
        st.map('Q.Treeview.Heading', background=[('active', C['raised'])])
        st.configure('D.Vertical.TScrollbar', gripcount=0, background=C['raised'], troughcolor=C['field'],
                     bordercolor=C['field'], lightcolor=C['raised'], darkcolor=C['raised'],
                     arrowcolor=C['muted'], arrowsize=px(12), relief='flat')
        st.map('D.Vertical.TScrollbar', background=[('active', C['border_hi'])])
        self.st = st

    def _card(self, parent, title, sub=None):
        outer = tk.Frame(parent, bg=C['surface'], highlightthickness=1, highlightbackground=C['border'])
        head = tk.Frame(outer, bg=C['surface'])
        head.pack(fill='x', padx=px(16), pady=(px(14), px(8)))
        tk.Label(head, text=title, font=FONTS['h3'], bg=C['surface'], fg=C['text']).pack(side='left')
        label = None
        if sub is not None:
            label = tk.Label(head, text=sub, font=FONTS['small'], bg=C['surface'], fg=C['muted'])
            label.pack(side='left', padx=(px(10), 0), pady=(px(2), 0))
        return outer, head, label

    def _entry(self, parent, var):
        e = tk.Entry(parent, textvariable=var, bg=C['field'], fg=C['text'], insertbackground=C['text'],
                     relief='flat', font=FONTS['body'], highlightthickness=1, highlightbackground=C['border'],
                     highlightcolor=self.accent, disabledbackground=C['field'],
                     selectbackground=C['border_hi'], selectforeground=C['text'])
        self.entries.append(e)
        return e

    def _build(self):
        root = tk.Frame(self, bg=C['base'])
        root.pack(fill='both', expand=True)

        hdr = tk.Frame(root, bg=C['base'])
        hdr.pack(fill='x', padx=px(24), pady=(px(18), px(8)))
        self.logo = Logo(hdr)
        self.logo.pack(side='left')
        titles = tk.Frame(hdr, bg=C['base'])
        titles.pack(side='left', padx=(px(12), 0))
        tk.Label(titles, text='Game Model To FBX', font=FONTS['title'], bg=C['base'], fg=C['text']).pack(anchor='w')
        tk.Label(titles, text='Choose a game  ·  Add your models  ·  Export rigged FBX',
                 font=FONTS['small'], bg=C['base'], fg=C['muted']).pack(anchor='w')
        self.status = StatusPill(hdr)
        self.status.pack(side='right')

        foot = tk.Label(root, text='Ctrl+1–4  switch game     Ctrl+O  add files     Ctrl+Enter  convert     '
                                   'Del  remove from queue', font=FONTS['small'], bg=C['base'], fg=C['faint'])
        foot.pack(side='bottom', anchor='w', padx=px(24), pady=px(10))

        self.tabs = TabBar(root, self)
        self.tabs.pack(fill='x', padx=px(4))

        body = tk.Frame(root, bg=C['base'])
        body.pack(fill='both', expand=True, padx=px(24), pady=(px(16), 0))
        body.columnconfigure(0, weight=11, uniform='col')
        body.columnconfigure(1, weight=9, uniform='col')
        body.rowconfigure(0, weight=1)
        left = tk.Frame(body, bg=C['base'])
        left.grid(row=0, column=0, sticky='nsew', padx=(0, px(16)))
        right = tk.Frame(body, bg=C['base'])
        right.grid(row=0, column=1, sticky='nsew')

        # left: hero, drop zone, queue
        self.hero = Hero(left, self)
        self.hero.pack(fill='x')
        self.drop = DropZone(left, self)
        self.drop.pack(fill='x', pady=px(14))
        qcard, qhead, self.qcount = self._card(left, 'Queue', '')
        qcard.pack(fill='both', expand=True)
        Button(qhead, 'Remove selected', self.remove, 'ghost', 'delete', height=28, padx=10).pack(side='right')
        Button(qhead, 'Clear', self.clear, 'ghost', 'clear', height=28, padx=10).pack(side='right')
        qwrap = tk.Frame(qcard, bg=C['field'])
        qwrap.pack(fill='both', expand=True, padx=1, pady=(0, 1))
        self.tree = ttk.Treeview(qwrap, style='Q.Treeview', columns=('name', 'type', 'where'),
                                 show='headings', selectmode='extended', height=4)
        for col, text, width, stretch in [('name', 'Name', 220, False), ('type', 'Type', 80, False),
                                          ('where', 'Location', 200, True)]:
            self.tree.heading(col, text=text, anchor='w')
            self.tree.column(col, width=px(width), stretch=stretch, anchor='w')
        qbar = ttk.Scrollbar(qwrap, orient='vertical', style='D.Vertical.TScrollbar', command=self.tree.yview)
        self.tree.configure(yscrollcommand=qbar.set)
        qbar.pack(side='right', fill='y')
        self.tree.pack(side='left', fill='both', expand=True)
        self.tree.drop_target_register(DND_FILES)
        self.tree.dnd_bind('<<Drop>>', lambda e: (self.add_paths(self.tk.splitlist(e.data)), 'copy')[1])
        self.tree.bind('<Delete>', lambda e: self.remove())
        self.empty = tk.Label(qwrap, text='Nothing queued yet — drop files above or press Ctrl+O',
                              font=FONTS['small'], bg=C['field'], fg=C['faint'])

        # right: paths, run, log
        pcard, _, _ = self._card(right, 'Paths')
        pcard.pack(fill='x')
        inner = tk.Frame(pcard, bg=C['surface'])
        inner.pack(fill='x', padx=px(16), pady=(0, px(14)))
        tk.Label(inner, text='CONFIGURATION JSON', font=FONTS['eyebrow'], bg=C['surface'], fg=C['muted']).pack(anchor='w')
        row = tk.Frame(inner, bg=C['surface'])
        row.pack(fill='x', pady=(px(4), 0))
        self._entry(row, self.config_path).pack(side='left', fill='x', expand=True, ipady=px(6), padx=(0, px(6)))
        Button(row, 'Browse', lambda: self.browse(self.config_path, False), height=32, padx=12).pack(side='left')
        row = tk.Frame(inner, bg=C['surface'])
        row.pack(fill='x', pady=(px(6), px(12)))
        Button(row, 'Create / Edit configuration', self.edit_config, 'ghost', 'edit', height=28, padx=10) \
            .pack(side='right')
        self.cfg_status = tk.Label(row, text='', font=FONTS['small'], bg=C['surface'], fg=C['muted'], anchor='w')
        self.cfg_status.pack(side='left', fill='x', expand=True)
        tk.Label(inner, text='OUTPUT FOLDER', font=FONTS['eyebrow'], bg=C['surface'], fg=C['muted']).pack(anchor='w')
        row = tk.Frame(inner, bg=C['surface'])
        row.pack(fill='x', pady=(px(4), 0))
        self._entry(row, self.output).pack(side='left', fill='x', expand=True, ipady=px(6), padx=(0, px(6)))
        Button(row, 'Browse', lambda: self.browse(self.output, True), height=32, padx=12).pack(side='left')
        Button(row, 'Open', self.open_output, icon='open', height=32, padx=12).pack(side='left', padx=(px(6), 0))

        rcard, _, self.run_sub = self._card(right, 'Run', '')
        rcard.pack(fill='x', pady=px(14))
        inner = tk.Frame(rcard, bg=C['surface'])
        inner.pack(fill='x', padx=px(16), pady=(0, px(16)))
        brow = tk.Frame(inner, bg=C['surface'])
        brow.pack(fill='x')
        self.b_inspect = Button(brow, 'Inspect / Read Mods', lambda: self.start('inspect'), icon='search', height=40)
        self.b_inspect.pack(side='left')
        self.b_convert = Button(brow, 'Convert Batch to FBX', lambda: self.start('convert'), 'primary', 'play',
                                accent=self.accent, height=40)
        self.b_convert.pack(side='left', fill='x', expand=True, padx=(px(8), 0))
        self.b_card = Button(inner, 'Sunshine to KK card', lambda: self.start('convert-card'), icon='swap', height=34)
        self.buttons = [self.b_inspect, self.b_convert, self.b_card]
        self.progress = Progress(inner, self)
        self.progress.pack(fill='x', pady=(px(14), px(6)))
        self.prog_label = tk.Label(inner, text='Idle', font=FONTS['small'], bg=C['surface'], fg=C['muted'], anchor='w')
        self.prog_label.pack(fill='x')

        lcard, lhead, _ = self._card(right, 'Activity')
        lcard.pack(fill='both', expand=True)
        Button(lhead, 'Clear', self.clear_log, 'ghost', 'clear', height=28, padx=10).pack(side='right')
        lwrap = tk.Frame(lcard, bg=C['field'])
        lwrap.pack(fill='both', expand=True, padx=1, pady=(0, 1))
        self.log = tk.Text(lwrap, bg=C['field'], fg=C['text'], font=FONTS['mono'], relief='flat', wrap='word',
                           padx=px(14), pady=px(10), insertbackground=C['text'], highlightthickness=0,
                           selectbackground=C['border_hi'], state='disabled', height=6, spacing1=px(2))
        lbar = ttk.Scrollbar(lwrap, orient='vertical', style='D.Vertical.TScrollbar', command=self.log.yview)
        self.log.configure(yscrollcommand=lbar.set)
        lbar.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        for tag, color in [('time', C['faint']), ('muted', C['muted']), ('ok', C['ok']), ('bad', C['bad']),
                           ('warn', C['warn']), ('json', C['json']), ('step', C['text'])]:
            self.log.tag_configure(tag, foreground=color)
        self.log.tag_configure('json', lmargin1=px(24), lmargin2=px(24))
        for g in GAMES:
            self.log.tag_configure('g_' + g['key'], foreground=g['accent'], font=FONTS['small_b'])


    # ---- state

    def _debounce(self, key, ms, fn):
        if self._deb.get(key):
            self.after_cancel(self._deb[key])
        self._deb[key] = self.after(ms, fn)

    def load_config(self):
        p = self.config_path.get().strip()
        data, err = None, None
        if not p:
            err = 'No configuration selected — create one or browse to an existing JSON'
        else:
            try:
                data = json.loads(Path(p).read_text(encoding='utf-8-sig'))
                if not isinstance(data, dict):
                    raise ValueError('Configuration must be a JSON object')
            except Exception as exc:
                data, err = None, str(exc)
        self.config_data, self.config_error = data, err
        if err:
            self.cfg_status.configure(text='✕  ' + (err if len(err) < 90 else err[:87] + '…'), fg=C['bad'])
        else:
            self.cfg_status.configure(text=f'✓  Loaded {len(data)} settings', fg=C['ok'])
        self.hero.draw()

    def need_state(self, key, required):
        if self.config_data is None:
            return 'unknown'
        value = self.config_data.get(key)
        if value and Path(str(value)).exists():
            return 'ok'
        return 'missing' if required else 'optional'

    def switch(self, i, animate=True):
        old = self.accent
        self.index = i
        g = self.game
        self.accent = g['accent']
        self.tabs.select(i, animate)
        self.hero.show(g, animate)
        if animate:
            self.anim.run('accent', 300, lambda t: self._apply_accent(mix(old, g['accent'], t)))
        else:
            self._apply_accent(g['accent'])
        self.st.map('Q.Treeview', background=[('selected', mix(g['accent'], C['field'], .72))],
                    foreground=[('selected', C['text'])])
        if g.get('card'):
            self.b_card.pack(fill='x', pady=(px(8), 0), before=self.progress)
        else:
            self.b_card.pack_forget()
        self.refresh_queue()

    def _apply_accent(self, c):
        self.logo.draw(c)
        self.b_convert.set_accent(c)
        self.progress.draw()
        self.drop.draw()
        for e in self.entries:
            e.configure(highlightcolor=c)

    def refresh_queue(self, flash=()):
        q = self.queues[self.game['key']]
        self.tree.delete(*self.tree.get_children())
        for n, path in enumerate(q):
            p = Path(path)
            if p.is_dir():
                kind = 'Folder'
            elif p.name.lower().endswith('.studio.json'):
                kind = 'STUDIO.JSON'
            else:
                kind = p.suffix.lstrip('.').upper() or 'File'
            self.tree.insert('', 'end', iid=str(n), values=(p.name, kind, str(p.parent)),
                             tags=('flash',) if path in flash else ())
        if q:
            self.empty.place_forget()
        else:
            self.empty.place(relx=.5, rely=.55, anchor='center')
        self.tabs.set_count(self.index, len(q))
        self.qcount.configure(text=f'{len(q)} item' + ('' if len(q) == 1 else 's') if q else 'empty')
        self.run_sub.configure(text=f'{len(q)} queued for {self.game["name"]}' if q else self.game['name'])
        if flash:
            start = mix(self.accent, C['field'], .6)
            self.anim.run('flash', 900, lambda t: self.tree.tag_configure('flash', background=mix(start, C['field'], t)))

    # ---- queue actions

    def add_paths(self, paths):
        q = self.queues[self.game['key']]
        added = []
        for raw in paths:
            p = str(Path(raw))
            if Path(p).exists() and p not in q:
                q.append(p)
                added.append(p)
        if added:
            self.refresh_queue(flash=set(added))
            self.log_line(f'Added {len(added)} to the {self.game["name"]} queue', 'muted')
        skipped = len(paths) - len(added)
        if skipped:
            self.log_line(f'Skipped {skipped} already queued or missing', 'warn')

    def add_files(self):
        g = self.game
        files = filedialog.askopenfilenames(parent=self, filetypes=g['types'] + [
            ('Supported inputs', ALL_TYPES), ('All files', '*.*')])
        if files:
            self.add_paths(files)

    def add_folder(self):
        p = filedialog.askdirectory(parent=self)
        if p:
            self.add_paths([p])

    def remove(self):
        q = self.queues[self.game['key']]
        for i in sorted((int(x) for x in self.tree.selection()), reverse=True):
            del q[i]
        self.refresh_queue()

    def clear(self):
        self.queues[self.game['key']].clear()
        self.refresh_queue()

    def browse(self, variable, folder):
        p = filedialog.askdirectory(parent=self) if folder else filedialog.askopenfilename(
            parent=self, filetypes=[('JSON', '*.json')])
        if p:
            variable.set(p)

    def open_output(self):
        p = Path(self.output.get())
        try:
            p.mkdir(parents=True, exist_ok=True)
            os.startfile(str(p))
        except (OSError, AttributeError) as exc:
            self.log_line(f'Cannot open output folder: {exc}', 'bad')

    def open_guide(self):
        webbrowser.open('https://github.com/ClubVixen/Game-Model-To-FBX/blob/main/docs/games/'
                        + self.game['guide'] + '.md')

    # ---- configuration editor

    def edit_config(self):
        if self._editor is not None and self._editor.winfo_exists():
            self._editor.lift()
            return
        win = tk.Toplevel(self, bg=C['base'])
        self._editor = win
        win.title('Configuration — paths and advanced game options')
        win.geometry(f'{px(900)}x{px(660)}')
        win.minsize(px(600), px(400))
        win.transient(self)
        win.after(20, lambda: dark_titlebar(win))
        accent = self.accent

        head = tk.Frame(win, bg=C['base'])
        head.pack(fill='x', padx=px(22), pady=(px(18), px(10)))
        tk.Label(head, text='Configuration', font=FONTS['title'], bg=C['base'], fg=C['text']).pack(anchor='w')
        tk.Label(head, text='Edit paths for your game. Use forward slashes in JSON paths. '
                            'Fields for games you don’t use can be left as they are.',
                 font=FONTS['small'], bg=C['base'], fg=C['muted']).pack(anchor='w')

        frame = tk.Frame(win, bg=C['field'], highlightthickness=1, highlightbackground=C['border'])
        frame.pack(fill='both', expand=True, padx=px(22))
        editor = tk.Text(frame, wrap='none', bg=C['field'], fg=C['text'], insertbackground=accent,
                         font=FONTS['mono'], relief='flat', padx=px(14), pady=px(12), undo=True,
                         selectbackground=C['border_hi'], highlightthickness=0, spacing1=px(2))
        bar = ttk.Scrollbar(frame, orient='vertical', style='D.Vertical.TScrollbar', command=editor.yview)
        editor.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        editor.pack(fill='both', expand=True)
        for tag, color in [('key', accent), ('str', '#9ee6a8'), ('num', '#ffb27a'), ('lit', '#c79bff')]:
            editor.tag_configure(tag, foreground=color)

        path = Path(self.config_path.get()) if self.config_path.get() else ROOT / 'multigame.example.json'
        try:
            editor.insert('1.0', path.read_text(encoding='utf-8-sig'))
        except OSError as exc:
            editor.insert('1.0', '{}')
            messagebox.showwarning('Configuration', str(exc), parent=win)

        foot = tk.Frame(win, bg=C['base'])
        foot.pack(fill='x', padx=px(22), pady=px(14))
        state = tk.Label(foot, font=FONTS['small_b'], bg=C['base'], anchor='w')
        state.pack(side='left', fill='x', expand=True)

        def check():
            text = editor.get('1.0', 'end-1c')
            for tag in ('key', 'str', 'num', 'lit'):
                editor.tag_remove(tag, '1.0', 'end')
            for m in re.finditer(r'"(?:[^"\\\n]|\\.)*"(\s*:)?|-?\b\d+(?:\.\d+)?\b|\b(?:true|false|null)\b', text):
                tag = 'key' if m.group(1) else 'str' if m.group(0).startswith('"') else \
                    'num' if m.group(0)[0] in '-0123456789' else 'lit'
                end = m.end(0) - (len(m.group(1)) if m.group(1) else 0)
                editor.tag_add(tag, f'1.0+{m.start()}c', f'1.0+{end}c')
            try:
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError('Configuration must be a JSON object')
                state.configure(text=f'✓  Valid JSON  ·  {len(data)} settings', fg=C['ok'])
                frame.configure(highlightbackground=C['border'])
                return data
            except json.JSONDecodeError as exc:
                state.configure(text=f'✕  Line {exc.lineno}, column {exc.colno}: {exc.msg}', fg=C['bad'])
            except ValueError as exc:
                state.configure(text='✕  ' + str(exc), fg=C['bad'])
            frame.configure(highlightbackground=mix(C['bad'], C['base'], .4))
            return None

        editor.bind('<KeyRelease>', lambda e: self._debounce('editor', 200, check))
        check()

        def write(dest):
            data = check()
            if data is None:
                messagebox.showerror('Cannot save configuration', 'Fix the JSON error first.', parent=win)
                return
            try:
                Path(dest).write_text(json.dumps(data, indent=2), encoding='utf-8')
            except OSError as exc:
                messagebox.showerror('Cannot save configuration', str(exc), parent=win)
                return
            self.config_path.set(dest)
            self.load_config()
            self.log_line(f'Saved configuration to {dest}', 'ok')
            win.destroy()

        def save_as():
            dest = filedialog.asksaveasfilename(parent=win, initialdir=str(ROOT), initialfile='multigame.local.json',
                                                defaultextension='.json', filetypes=[('JSON', '*.json')])
            if dest:
                write(dest)

        current = self.config_path.get().strip()
        if current:
            Button(foot, 'Save', lambda: write(current), 'primary', accent=accent, height=36).pack(side='right')
        Button(foot, 'Save configuration as…', save_as, 'primary' if not current else 'secondary',
               accent=accent, height=36).pack(side='right', padx=px(8))
        Button(foot, 'Cancel', win.destroy, 'ghost', height=36).pack(side='right')

    # ---- running

    def start(self, action):
        if self.busy:
            return
        g = self.game
        sources = list(self.queues[g['key']])
        if not sources:
            self.log_line(f'Add at least one input to the {g["name"]} queue first', 'bad')
            self.drop.shake()
            return
        try:
            if not self.config_path.get().strip():
                raise ValueError('Choose or create a configuration JSON first')
            config = json.loads(Path(self.config_path.get()).read_text(encoding='utf-8-sig'))
        except Exception as exc:
            self.log_line(f'Configuration: {exc}', 'bad')
            self.status.set('Configuration problem', C['bad'])
            return
        kind, output = g['key'], self.output.get()
        verb = {'inspect': 'Inspecting', 'convert': 'Converting', 'convert-card': 'Converting cards'}[action]
        self.busy = True
        for b in self.buttons:
            b.set_enabled(False)
        self.tabs.set_busy(self.index)
        self.progress.start()
        self.log_line(f'{g["name"]}  ·  {verb.lower()} {len(sources)} item' + ('' if len(sources) == 1 else 's'),
                      'g_' + kind, gap=True)
        put = self.messages.put

        def work():
            ok = failed = 0
            for n, source in enumerate(sources):
                put(('progress', n, len(sources), verb, Path(source).name, g['name']))
                put(('log', 'Reading ' + source, 'step'))
                try:
                    if action == 'convert-card':
                        if kind != 'koikatsu':
                            raise ValueError('Choose Koikatsu for card conversion')
                        from koikatsu_card import prepare_card
                        result = prepare_card(source, output, config)
                    elif action == 'inspect':
                        result = inspect(source, kind, config)
                    else:
                        result = str(convert(source, kind, output, config, log=lambda m: put(('log', str(m), None))))
                    put(('result', result, action))
                    ok += 1
                except Exception as exc:
                    put(('log', 'FAILED: ' + str(exc), 'bad'))
                    failed += 1
            put(('done', ok, failed, verb))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                msg = self.messages.get_nowait()
                kind = msg[0]
                if kind == 'log':
                    text, tag = msg[1], msg[2]
                    if tag is None:
                        tag = 'bad' if 'FAILED' in text or text.lower().startswith('error') else 'muted'
                    self.log_line(text, tag)
                elif kind == 'result':
                    result, action = msg[1], msg[2]
                    if action == 'convert':
                        self.log_line('✓  Exported to ' + str(result), 'ok')
                    else:
                        self.log_line('✓  Done', 'ok')
                        self.log_block(json.dumps(result, indent=2))
                elif kind == 'progress':
                    n, total, verb, name, game = msg[1:]
                    self.progress.set(n / total)
                    self.prog_label.configure(text=f'{game}  ·  {n + 1} of {total}  ·  {name}')
                    self.status.set(f'{verb} {n + 1} of {total}', self.accent, pulse=True)
                elif kind == 'done':
                    ok, failed, verb = msg[1:]
                    self._finish(ok, failed)
        except queue.Empty:
            pass
        self.after(60, self.poll)

    def _finish(self, ok, failed):
        self.busy = False
        for b in self.buttons:
            b.set_enabled(True)
        self.tabs.set_busy(None)
        self.progress.set(1.0)
        color = C['bad'] if failed else C['ok']
        self.progress.stop(color)
        summary = f'{ok} succeeded' + (f'  ·  {failed} failed' if failed else '')
        self.prog_label.configure(text='Finished  ·  ' + summary)
        self.status.set('Finished  ·  ' + summary, color)
        self.log_line('Finished  ·  ' + summary, 'bad' if failed else 'ok')
        self.after(6000, lambda: None if self.busy else self.status.set('Ready', C['ok']))

    # ---- log

    def log_line(self, text, tag='muted', gap=False):
        self.log.configure(state='normal')
        if gap and self.log.index('end-1c') != '1.0':
            self.log.insert('end', '\n')
        self.log.insert('end', datetime.datetime.now().strftime('%H:%M:%S') + '  ', 'time')
        self.log.insert('end', text + '\n', tag)
        self.log.see('end')
        self.log.configure(state='disabled')

    def log_block(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', text + '\n', 'json')
        self.log.see('end')
        self.log.configure(state='disabled')

    def clear_log(self):
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')

    def on_close(self):
        if self.busy and not messagebox.askyesno(
                'Conversion running', 'A job is still running. Quit anyway?', parent=self):
            return
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
