"""Private-display-only XTEST and drawable PNG capture. Deferred Xlib imports."""
from __future__ import annotations
import os
from pathlib import Path
import struct
import zlib


def png_rgb(path, width, height, rgb):
    if width <= 0 or height <= 0 or len(rgb) != width * height * 3:
        raise ValueError('PNG dimensions/data differ')
    def chunk(name, value):
        return struct.pack('!I', len(value)) + name + value + struct.pack('!I', zlib.crc32(name + value) & 0xffffffff)
    scan = b''.join(b'\0' + rgb[row * width * 3:(row + 1) * width * 3] for row in range(height))
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
                           + chunk(b'IDAT', zlib.compress(scan)) + chunk(b'IEND', b''))


class OwnedDisplay:
    def __init__(self, display_name, token):
        if not display_name.startswith(':') or not display_name[1:].isdecimal() or int(display_name[1:]) < 50:
            raise ValueError('Only the explicitly private high-numbered display is allowed')
        if os.environ.get('DISPLAY') != display_name:
            raise ValueError('DISPLAY differs from the frozen private display')
        from Xlib import X, XK, Xatom, display
        from Xlib.ext import xtest
        self.X, self.XK, self.Xatom, self.xtest = X, XK, Xatom, xtest
        self.d = display.Display(display_name)
        self.root = self.d.screen().root
        prop = self.root.get_full_property(self.d.intern_atom('_PHP_GUI_AUDIT_TOKEN'), X.AnyPropertyType)
        if prop is None or bytes(prop.value).decode() != token:
            self.d.close()
            raise ValueError('Private X server ownership token differs; no input allowed')
        if not self.d.has_extension('XTEST') or not self.d.has_extension('RECORD'):
            self.d.close()
            raise RuntimeError('Private display lacks genuine key-down/up extensions')
        self.held = set()

    def windows(self):
        result = []
        def visit(window, depth=0):
            if depth > 5:
                return
            try:
                title = window.get_wm_name()
                pid = window.get_full_property(self.d.intern_atom('_NET_WM_PID'), self.X.AnyPropertyType)
                if title:
                    result.append({'xid': window.id, 'title': title,
                                   'pid': int(pid.value[0]) if pid is not None and len(pid.value) else None})
                for child in window.query_tree().children:
                    visit(child, depth + 1)
            except Exception as error:
                if type(error).__name__ not in ('BadWindow', 'BadDrawable'):
                    raise
        visit(self.root)
        return result

    def mark_pid(self, xid, pid):
        window = self.d.create_resource_object('window', xid)
        # Tk's title-bearing outer wrapper can be a parent of winfo_id().
        # Only walk ancestors of the widget we created, stopping before root.
        for _ in range(8):
            if window.id == self.root.id:
                break
            window.change_property(self.d.intern_atom('_NET_WM_PID'), self.Xatom.CARDINAL, 32, [pid])
            window = window.query_tree().parent
        self.d.sync()

    def focus(self, xid, allowed):
        if xid not in allowed:
            raise ValueError('Input target is not an explicitly owned XID')
        window = self.d.create_resource_object('window', xid)
        window.set_input_focus(self.X.RevertToParent, self.X.CurrentTime)
        self.d.sync()
        if self.d.get_input_focus().focus.id != xid:
            raise RuntimeError('Private display focus did not reach exact owned window')

    def key(self, xid, name, pressed, allowed):
        self.focus(xid, allowed)
        keysym = self.XK.string_to_keysym(name)
        code = self.d.keysym_to_keycode(keysym)
        if not code:
            raise ValueError('Unknown keysym')
        self.xtest.fake_input(self.d, self.X.KeyPress if pressed else self.X.KeyRelease, code)
        self.d.sync()
        if pressed:
            self.held.add(code)
        else:
            self.held.discard(code)

    def place_native_window(self, xid, allowed):
        if xid not in allowed:
            raise ValueError('Geometry target is not explicitly owned')
        window = self.d.create_resource_object('window', xid)
        window.configure(x=0, y=0, width=1100, height=850)
        self.d.sync()
        geom = window.get_geometry()
        return {'xid': xid, 'width': geom.width, 'height': geom.height,
                'scope': 'Owned spectator window placement only; sensor/camera/actor untouched'}

    def release_all(self):
        # Still this exact private display, without changing desktop focus.
        for code in sorted(self.held):
            self.xtest.fake_input(self.d, self.X.KeyRelease, code)
        self.d.sync()
        self.held.clear()

    def capture(self, xid, path, allowed):
        if xid not in allowed:
            raise ValueError('Capture target is not explicitly owned')
        window = self.d.create_resource_object('window', xid)
        geom, attrs = window.get_geometry(), window.get_attributes()
        raw = window.get_image(0, 0, geom.width, geom.height, self.X.ZPixmap, 0xffffffff)
        formats = [v for v in self.d.display.info.pixmap_formats if v.depth == geom.depth]
        visuals = [v for depth in self.d.screen().allowed_depths for v in depth.visuals if v.visual_id == attrs.visual]
        if len(formats) != 1 or len(visuals) != 1 or formats[0].bits_per_pixel not in (24, 32):
            raise RuntimeError('Unsupported private drawable pixel format')
        fmt, visual = formats[0], visuals[0]
        bpp = fmt.bits_per_pixel // 8
        stride = ((geom.width * fmt.bits_per_pixel + fmt.scanline_pad - 1) // fmt.scanline_pad) * (fmt.scanline_pad // 8)
        order = 'little' if self.d.display.info.image_byte_order == 0 else 'big'
        masks = [visual.red_mask, visual.green_mask, visual.blue_mask]
        shifts = [(mask & -mask).bit_length() - 1 for mask in masks]
        rgb = bytearray()
        for row in range(geom.height):
            for col in range(geom.width):
                start = row * stride + col * bpp
                pixel = int.from_bytes(raw.data[start:start + bpp], order)
                rgb.extend(((pixel & mask) >> shift) * 255 // (mask >> shift) for mask, shift in zip(masks, shifts))
        unique = len(set(zip(rgb[0::3], rgb[1::3], rgb[2::3])))
        if unique < 20:
            raise RuntimeError('Native drawable is blank/unpainted')
        png_rgb(path, geom.width, geom.height, rgb)
        return {'xid': xid, 'width': geom.width, 'height': geom.height, 'unique_rgb': unique,
                'capture': 'actual XGetImage of exact owned drawable; lossless PNG, no enhancement'}

    def close(self):
        try:
            self.release_all()
        finally:
            self.d.close()
