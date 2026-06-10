# Terminator minimap
# GPL v2 only
"""minimap.py - a narrow activity-overview column for a terminal.

Phase 1: an "activity strip" — each scrollback row is classified cheaply
(prompt/command, error, output) and drawn as a 1px colored band, the whole
recent scrollback scaled to the column height. A translucent box shows the
current viewport; click or drag to scroll there.

Per-terminal and session-only: it is hidden by default and toggled from the
terminal's right-click menu (Terminal.do_minimap_toggle). A later phase can add
a scaled-text rendering mode behind the same column.
"""

import re

from gi.repository import Gtk, Gdk, GLib, Vte

WIDTH = 64                  # column width in px
MAX_SCAN = 5000             # most-recent rows represented (perf bound)
REFRESH_MS = 150            # coalesce rapid contents-changed bursts

# Cheap, shell-agnostic line classification.
ERROR_RE = re.compile(
    r'(?i)\b(error|errors|failed|failure|fatal|exception|traceback'
    r'|denied|not found|no such file|cannot|segmentation fault)\b')
PROMPT_RE = re.compile(r'(\$\s|#\s|%\s|➜|»|\w+@[\w.\-]+[:~])')

# Band colors and priority (when many rows collapse into one pixel).
_COLORS = {
    'error':  (0.85, 0.25, 0.25),
    'prompt': (0.30, 0.75, 0.42),
    'output': (0.52, 0.52, 0.56),
}
_PRIO = {'error': 3, 'prompt': 2, 'output': 1}


class Minimap(Gtk.DrawingArea):
    """A scrollback activity overview drawn alongside a terminal."""

    def __init__(self, terminal):
        Gtk.DrawingArea.__init__(self)
        self.terminal = terminal
        self.vte = terminal.vte
        self.set_size_request(WIDTH, -1)
        self.set_no_show_all(True)          # hidden until toggled on

        self._bands = []        # per-row classification, oldest..newest
        self._scan_start = 0    # absolute buffer row of bands[0]
        self._scan_total = 0
        self._dirty = True
        self._refresh_id = 0

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.BUTTON1_MOTION_MASK)
        self.connect('draw', self._on_draw)
        self.connect('button-press-event', self._on_button)
        self.connect('motion-notify-event', self._on_motion)

        self._adj = self.vte.get_vadjustment()
        self._cid_contents = self.vte.connect('contents-changed',
                                              self._on_contents_changed)
        self._cid_value = self._adj.connect('value-changed',
                                            lambda *a: self.queue_draw())

    # ---- refresh plumbing ------------------------------------------------

    def _on_contents_changed(self, *_a):
        self._dirty = True
        if self.get_visible() and self._refresh_id == 0:
            self._refresh_id = GLib.timeout_add(REFRESH_MS, self._do_refresh)

    def _do_refresh(self):
        self._refresh_id = 0
        self.queue_draw()
        return False

    def refresh_now(self):
        """Force a recompute + redraw (used when the column is toggled on)."""
        self._dirty = True
        self.queue_draw()

    # ---- data ------------------------------------------------------------

    def _read_text(self, start, end):
        # end is inclusive; get_text_range end row is exclusive (see mcp_bridge).
        try:
            res = self.vte.get_text_range_format(Vte.Format.TEXT,
                                                 start, 0, end + 1, 0)
            if isinstance(res, tuple):
                res = res[0] if res else ''
            return res or ''
        except Exception:
            return ''

    def _recompute(self):
        lower = int(self._adj.get_lower())
        upper = int(self._adj.get_upper())
        start = max(lower, upper - MAX_SCAN)
        text = self._read_text(start, max(start, upper - 1))
        bands = []
        for line in text.split('\n'):
            s = line.strip()
            if not s:
                bands.append(None)
            elif ERROR_RE.search(s):
                bands.append('error')
            elif PROMPT_RE.search(s):
                bands.append('prompt')
            else:
                bands.append('output')
        self._bands = bands
        self._scan_start = start
        self._scan_total = len(bands)
        self._dirty = False

    # ---- drawing ---------------------------------------------------------

    def _on_draw(self, _widget, cr):
        if self._dirty:
            self._recompute()
        alloc = self.get_allocation()
        width, height = alloc.width, alloc.height
        cr.set_source_rgb(0.11, 0.11, 0.13)
        cr.paint()

        n = len(self._bands)
        if n == 0 or height <= 0:
            return False

        for y in range(height):
            i0 = int(y * n / height)
            i1 = max(i0 + 1, int((y + 1) * n / height))
            best, best_p = None, 0
            for band in self._bands[i0:i1]:
                if band and _PRIO[band] > best_p:
                    best, best_p = band, _PRIO[band]
            if best:
                cr.set_source_rgb(*_COLORS[best])
                cr.rectangle(4, y, width - 8, 1)
                cr.fill()

        # current viewport box, mapped into the scanned window
        span = self._scan_total or 1
        value = self._adj.get_value()
        page = self._adj.get_page_size()
        top = (value - self._scan_start) / span * height
        bot = (value + page - self._scan_start) / span * height
        top = max(0, min(height, top))
        bot = max(top + 2, min(height, bot))
        cr.set_source_rgba(1, 1, 1, 0.14)
        cr.rectangle(0, top, width, bot - top)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.55)
        cr.set_line_width(1)
        cr.rectangle(0.5, top + 0.5, width - 1, bot - top - 1)
        cr.stroke()
        return False

    # ---- interaction -----------------------------------------------------

    def _y_to_value(self, y):
        alloc = self.get_allocation()
        height = alloc.height or 1
        page = self._adj.get_page_size()
        span = self._scan_total or 1
        value = self._scan_start + (y / height) * span - page / 2.0
        lo = self._adj.get_lower()
        hi = max(lo, self._adj.get_upper() - page)
        return max(lo, min(hi, value))

    def _on_button(self, _widget, event):
        if event.button == 1:
            self._adj.set_value(self._y_to_value(event.y))
            return True
        return False

    def _on_motion(self, _widget, event):
        if event.state & Gdk.ModifierType.BUTTON1_MASK:
            self._adj.set_value(self._y_to_value(event.y))
            return True
        return False

    # ---- teardown --------------------------------------------------------

    def disconnect_hooks(self):
        """Detach signal handlers (call if the terminal is destroyed)."""
        for owner, cid in ((self.vte, self._cid_contents),
                           (self._adj, self._cid_value)):
            try:
                owner.disconnect(cid)
            except Exception:
                pass
        if self._refresh_id:
            GLib.source_remove(self._refresh_id)
            self._refresh_id = 0
