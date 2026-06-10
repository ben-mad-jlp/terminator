# Terminator minimap
# GPL v2 only
"""minimap.py - a narrow activity-overview column for a terminal.

Two render modes (toggle from the right-click menu):
  * 'strip' - each scrollback row is classified cheaply (prompt/command,
    error, output) and drawn as a full-width colored band.
  * 'text'  - a VS Code-style scaled overview: each row is a bar whose width
    tracks the line length, so you see the silhouette/shape of the output.

A translucent box shows the current viewport; click or drag to scroll there.
The current selection is highlighted (cyan), and a selection can be turned
into a persistent bookmark (right-click -> Bookmark selection) which draws a
marker you can click to jump back to.

Per-terminal and session-only; hidden by default, toggled via
Terminal.do_minimap_toggle.
"""

import re

from gi.repository import Gtk, Gdk, GLib, Vte

WIDTH = 64                  # column width in px
MAX_SCAN = 5000             # most-recent rows represented (perf bound)
REFRESH_MS = 150            # coalesce rapid contents-changed bursts

ERROR_RE = re.compile(
    r'(?i)\b(error|errors|failed|failure|fatal|exception|traceback'
    r'|denied|not found|no such file|cannot|segmentation fault)\b')
PROMPT_RE = re.compile(r'(\$\s|#\s|%\s|➜|»|\w+@[\w.\-]+[:~])')

_COLORS = {
    'error':  (0.85, 0.25, 0.25),
    'prompt': (0.30, 0.75, 0.42),
    'output': (0.52, 0.52, 0.56),
}
_PRIO = {'error': 3, 'prompt': 2, 'output': 1}
_SELECT_RGBA = (0.30, 0.70, 0.95, 0.35)
_BOOKMARK_RGB = (1.0, 0.80, 0.20)


class Minimap(Gtk.DrawingArea):
    """A scrollback activity overview drawn alongside a terminal."""

    def __init__(self, terminal):
        Gtk.DrawingArea.__init__(self)
        self.terminal = terminal
        self.vte = terminal.vte
        self.set_size_request(WIDTH, -1)
        self.set_no_show_all(True)          # hidden until toggled on

        self.mode = 'strip'                 # 'strip' | 'text'
        self.show_hex_lines = False         # overlay hex row numbers
        self._lines = []                    # raw row text, oldest..newest
        self._kinds = []                    # classification per row
        self._lengths = []                  # visible length per row
        self._scan_start = 0                # absolute buffer row of index 0
        self._scan_total = 0
        self._dirty = True
        self._refresh_id = 0
        self._sel_rows = None               # (start, end) absolute rows
        self._bookmarks = []                # [{'row': int, 'label': str}]

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
        self._cid_sel = self.vte.connect('selection-changed',
                                         self._on_selection_changed)

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
        self._dirty = True
        self.queue_draw()

    def set_mode(self, mode):
        if mode in ('strip', 'text') and mode != self.mode:
            self.mode = mode
            self.queue_draw()

    def toggle_mode(self):
        self.set_mode('text' if self.mode == 'strip' else 'strip')

    def toggle_hex_lines(self):
        self.show_hex_lines = not self.show_hex_lines
        self.queue_draw()

    # ---- data ------------------------------------------------------------

    def _read_text(self, start, end):
        # end inclusive; get_text_range end row is exclusive (see mcp_bridge).
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
        lines = text.split('\n')
        kinds, lengths = [], []
        for line in lines:
            s = line.strip()
            length = len(line.rstrip())
            if not s:
                kinds.append(None)
            elif ERROR_RE.search(s):
                kinds.append('error')
            elif PROMPT_RE.search(s):
                kinds.append('prompt')
            else:
                kinds.append('output')
            lengths.append(length)
        self._lines = lines
        self._kinds = kinds
        self._lengths = lengths
        self._scan_start = start
        self._scan_total = len(kinds)
        self._dirty = False

    def _ensure_fresh(self):
        if self._dirty:
            self._recompute()

    # ---- selection + bookmarks -------------------------------------------

    def _on_selection_changed(self, *_a):
        if not self.vte.get_has_selection():
            if self._sel_rows is not None:
                self._sel_rows = None
                self.queue_draw()
            return
        try:
            sel = self.vte.get_text_selected(Vte.Format.TEXT)
            if isinstance(sel, tuple):
                sel = sel[0]
        except Exception:
            sel = None
        rows = self.locate_text(sel) if sel else None
        self._sel_rows = rows
        self.queue_draw()

    def locate_text(self, text):
        """Best-effort absolute (start, end) rows of `text` in the scan window.

        VTE 2.91 exposes selected text but not its grid coordinates, so we
        locate the selection by matching its lines against the scanned buffer.
        Returns None if not found.
        """
        self._ensure_fresh()
        if not text:
            return None
        sel_lines = [ln for ln in text.split('\n')]
        first = next((ln.strip() for ln in sel_lines if ln.strip()), '')
        if not first:
            return None
        for i, line in enumerate(self._lines):
            if first in line:
                n = max(1, len([ln for ln in sel_lines if ln.strip()]))
                return (self._scan_start + i,
                        self._scan_start + min(len(self._lines) - 1, i + n - 1))
        return None

    def bookmark_selection(self):
        """Turn the current selection into a persistent bookmark."""
        try:
            sel = self.vte.get_text_selected(Vte.Format.TEXT)
            if isinstance(sel, tuple):
                sel = sel[0]
        except Exception:
            sel = None
        rows = self.locate_text(sel) if sel else None
        if rows is None:
            return False
        label = (sel.strip().splitlines() or [''])[0][:40]
        self._bookmarks.append({'row': rows[0], 'label': label})
        self.queue_draw()
        return True

    def add_bookmark(self, row, label=''):
        """Add a bookmark at an absolute buffer row (used by the MCP bridge)."""
        self._bookmarks.append({'row': int(row), 'label': str(label)[:60]})
        self.queue_draw()
        return self._bookmarks[-1]

    def get_bookmarks(self):
        """Bookmarks as plain dicts, most-recent last."""
        return [dict(b) for b in self._bookmarks]

    def clear_bookmarks(self):
        if self._bookmarks:
            self._bookmarks = []
            self.queue_draw()

    # ---- geometry --------------------------------------------------------

    def _row_to_y(self, row, height):
        span = self._scan_total or 1
        return (row - self._scan_start) / span * height

    def _y_to_value(self, y):
        alloc = self.get_allocation()
        height = alloc.height or 1
        page = self._adj.get_page_size()
        span = self._scan_total or 1
        value = self._scan_start + (y / height) * span - page / 2.0
        lo = self._adj.get_lower()
        hi = max(lo, self._adj.get_upper() - page)
        return max(lo, min(hi, value))

    # ---- drawing ---------------------------------------------------------

    def _on_draw(self, _widget, cr):
        self._ensure_fresh()
        alloc = self.get_allocation()
        width, height = alloc.width, alloc.height
        cr.set_source_rgb(0.11, 0.11, 0.13)
        cr.paint()

        n = self._scan_total
        if n == 0 or height <= 0:
            return False

        cols = max(20, self.vte.get_column_count())
        for y in range(height):
            i0 = int(y * n / height)
            i1 = max(i0 + 1, int((y + 1) * n / height))
            best, best_p, max_len = None, 0, 0
            for k in range(i0, i1):
                kind = self._kinds[k]
                if kind and _PRIO[kind] > best_p:
                    best, best_p = kind, _PRIO[kind]
                if self._lengths[k] > max_len:
                    max_len = self._lengths[k]
            if not best:
                continue
            cr.set_source_rgb(*_COLORS[best])
            if self.mode == 'text':
                bar = (width - 8) * min(1.0, max_len / float(cols))
                cr.rectangle(4, y, max(1.0, bar), 1)
            else:
                cr.rectangle(4, y, width - 8, 1)
            cr.fill()

        # selection highlight
        if self._sel_rows is not None:
            top = max(0, min(height, self._row_to_y(self._sel_rows[0], height)))
            bot = max(top + 2,
                      min(height, self._row_to_y(self._sel_rows[1] + 1, height)))
            cr.set_source_rgba(*_SELECT_RGBA)
            cr.rectangle(0, top, width, bot - top)
            cr.fill()

        # bookmark markers
        for bm in self._bookmarks:
            by = self._row_to_y(bm['row'], height)
            if by < 0 or by > height:
                continue
            cr.set_source_rgb(*_BOOKMARK_RGB)
            cr.move_to(0, by - 4)
            cr.line_to(7, by)
            cr.line_to(0, by + 4)
            cr.close_path()
            cr.fill()
            cr.rectangle(0, by - 0.5, width, 1)
            cr.fill()

        # current viewport box
        span = n or 1
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

        # optional hex row-number overlay
        if self.show_hex_lines:
            cr.select_font_face('monospace', 0, 0)
            cr.set_font_size(8)
            step = max(12, height // 12)
            for y in range(2, height, step):
                idx = int(y * n / height)
                cr.set_source_rgba(0, 0, 0, 0.55)
                cr.rectangle(1, y, 38, 9)
                cr.fill()
                cr.set_source_rgba(0.85, 0.85, 0.9, 0.9)
                cr.move_to(2, y + 8)
                cr.show_text('0x%X' % (self._scan_start + idx))
        return False

    # ---- interaction -----------------------------------------------------

    def _click_bookmark(self, y, height):
        """Return a bookmark whose marker is within 5px of y, else None."""
        for bm in self._bookmarks:
            if abs(self._row_to_y(bm['row'], height) - y) <= 5:
                return bm
        return None

    def _on_button(self, _widget, event):
        if event.button != 1:
            return False
        alloc = self.get_allocation()
        bm = self._click_bookmark(event.y, alloc.height or 1)
        if bm is not None:
            page = self._adj.get_page_size()
            lo = self._adj.get_lower()
            hi = max(lo, self._adj.get_upper() - page)
            self._adj.set_value(max(lo, min(hi, bm['row'] - page / 2.0)))
        else:
            self._adj.set_value(self._y_to_value(event.y))
        return True

    def _on_motion(self, _widget, event):
        if event.state & Gdk.ModifierType.BUTTON1_MASK:
            self._adj.set_value(self._y_to_value(event.y))
            return True
        return False

    # ---- teardown --------------------------------------------------------

    def disconnect_hooks(self):
        for owner, cid in ((self.vte, self._cid_contents),
                           (self._adj, self._cid_value),
                           (self.vte, self._cid_sel)):
            try:
                owner.disconnect(cid)
            except Exception:
                pass
        if self._refresh_id:
            GLib.source_remove(self._refresh_id)
            self._refresh_id = 0
