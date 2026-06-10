# terminator-mcp

An MCP server that lets an LLM (e.g. Claude) observe — and, in later phases,
drive — a running [Terminator](https://github.com/gnome-terminator/terminator)
terminal emulator.

**Status: P0 — read-only.** The server can list terminals and read their
buffer / scrollback / selection. It has **no** ability to type, run commands,
or otherwise change a terminal. Write/send tools arrive in later phases behind
a safety model (password-prompt gate, destructive-command confirmation).

## Architecture

```
Claude  --stdio/JSON-RPC-->  terminator-mcp  (this package, separate process)
                                  |  length-prefixed JSON frames
                                  v  over a per-user Unix-domain socket
   Terminator GTK process  ->  MCPBridge plugin (Gio.SocketService on the
                                  GLib main loop; direct, thread-safe VTE access)
```

The bridge runs **inside** Terminator as a plugin, on the existing GLib main
loop — so it touches the live `Vte.Terminal` objects safely with no extra
threads. The MCP server is a **separate process**: it never imports GTK/VTE and
cannot crash or freeze your terminals. Works on Linux and macOS (no D-Bus
dependency).

## Install & run

There are **two pieces**:

- **(A) the bridge plugin** — runs *inside* Terminator, so it needs the same
  Python that runs Terminator (GTK/VTE). This is the part that differs by OS.
- **(B) the MCP server** (this package) — a standalone process that only needs
  the `mcp` package. **Identical on Linux and macOS**; it never imports GTK/VTE.

They talk over a per-user Unix socket
(`$XDG_RUNTIME_DIR/terminator-mcp-$UID/bridge.sock` on Linux,
`$TMPDIR/terminator-mcp-$UID/bridge.sock` on macOS). Tools return
`{"error":"terminator_not_running"}` until Terminator is up with the plugin.

Replace `/path/to/terminator` below with your checkout path.

### Ubuntu / Linux

**A. Plugin**
```bash
sudo apt install terminator python3-gi gir1.2-vte-2.91 python3-psutil python3-configobj
mkdir -p ~/.config/terminator/plugins
cp /path/to/terminator/terminatorlib/plugins/mcp_bridge.py ~/.config/terminator/plugins/
```
Enable it (Preferences → Plugins → tick **MCPBridge**, or in
`~/.config/terminator/config`):
```ini
[global_config]
  enabled_plugins = MCPBridge
```
Restart Terminator.

**B. MCP server**
```bash
python3 -m venv ~/.local/share/terminator-mcp/venv
~/.local/share/terminator-mcp/venv/bin/pip install mcp
claude mcp add terminator \
  --env PYTHONPATH=/path/to/terminator \
  -- ~/.local/share/terminator-mcp/venv/bin/python -m terminator_mcp
```

### macOS (Homebrew GTK)

Terminator isn't a native Mac app; run it under Homebrew's GTK Python.

**A. Plugin**
```bash
brew install pygobject3 gtk+3 vte3
# a venv that can see Homebrew's gi, plus Terminator's pure-python deps
/opt/homebrew/bin/python3 -m venv --system-site-packages ~/.local/share/terminator-gtk
~/.local/share/terminator-gtk/bin/pip install psutil configobj
mkdir -p ~/.config/terminator/plugins
cp /path/to/terminator/terminatorlib/plugins/mcp_bridge.py ~/.config/terminator/plugins/
```
Enable `MCPBridge` in `~/.config/terminator/config` (same `[global_config]`
stanza). Launch Terminator with that Python from the checkout:
```bash
cd /path/to/terminator
( ulimit -n 1024; ~/.local/share/terminator-gtk/bin/python ./terminator )
```
> **macOS gotcha:** keep `ulimit -n` finite (e.g. `1024`). If it is `unlimited`,
> glib's `fdwalk` fails and new shells won't spawn inside Terminator.

**B. MCP server** — same as Linux (a venv with `mcp` + `claude mcp add … PYTHONPATH=…`).
It is a pure socket client and does **not** need GTK.

### Sanity check (both platforms)

1. Start Terminator — the plugin loads when the first terminal is created.
2. In Claude, call `list_terminals`. You should see your terminal. A
   `terminator_not_running` error means the plugin isn't loaded (check it is in
   `enabled_plugins` and on the plugin path).

The minimap, line-number gutter, and bookmark menus are pure GUI and work
regardless of the MCP server.

## Tools

Read-only (P0):

| Tool | Args | Returns |
|------|------|---------|
| `list_terminals` | — | `{terminals: [{uuid, title, window_title, is_focused, cwd, rows, cols}]}` |
| `get_focused_terminal` | — | `{uuid}` |
| `tail` | `terminal?, lines=40` | `{text, total_rows, cursor_row, range, next_offset}` |
| `read_terminal` | `terminal?, mode='scrollback', max_lines=2000, offset=0, from_end=true` | `{text, total_rows, cursor_row, range, next_offset}` |
| `get_selection` | `terminal?` | `{has_selection, text}` |
| `find_in_scrollback` | `pattern, terminal?, regex=true, case_sensitive=false` | `{count, matches: [{row, line}], truncated}` |
| `read_raw` | `terminal?, start_row, end_row` | `{text, range, total_rows}` |

Write / command (gated — see Safety):

| Tool | Args | Returns |
|------|------|---------|
| `run_command` ⚠ | `command, terminal?, timeout_ms=15000, confirm_token?` | `{ok, output, exit_code, timed_out, command}` / `{requires_confirmation, …}` / `{error:"refused_password_prompt", …}` |
| `send_keys` ⚠ | `text, terminal?, enter=false, raw=false, confirm_token?` | `{ok, sent_bytes, visible_text}` / `{requires_confirmation, …}` |
| `confirm` | `confirm_token` | result of the deferred run/send |
| `focus_terminal` | `terminal` | `{ok, uuid}` |
| `rename` | `terminal, title` | rename one terminal's titlebar (per-pane) |
| `rename_tab` | `terminal, title` | rename the tab containing a terminal |
| `scroll_to` | `terminal?, row, position?` | scroll to a row (or 'top'/'bottom'); row<0 = bottom |
| `add_bookmark` | `terminal?, row \| pattern, label?, regex?, case_sensitive?` | bookmark a row, by number or text search |
| `list_bookmarks` | `terminal?` | minimap bookmarks `[{row, label}]` |

`terminal` accepts a UUID or a friendly title (case-insensitive); empty selects
the focused terminal. If Terminator isn't running / the plugin isn't enabled,
tools return `{"error": "terminator_not_running"}`.

## Safety

- **Reads are free.** list / tail / read_terminal / get_selection /
  find_in_scrollback / read_raw never modify a terminal.
- **Hard password gate (non-overridable).** `run_command` / `send_keys` refuse
  outright if the terminal's last line looks like a password / passphrase /
  sudo / yes-no prompt. No `confirm_token` bypasses this.
- **Destructive denylist → confirmation.** `rm -rf`, `sudo`, `dd of=`, `mkfs`,
  fork bombs, `> /dev/sd*`, `shutdown/reboot`, `git push --force`, `chmod -R`,
  … are not run on first call; they return a single-use `confirm_token`
  (~60 s TTL, bound to the exact command + terminal). Re-call with it, or use
  `confirm`.
- **`send_keys`** does not press Enter by default and rejects control/escape
  bytes unless `raw=true`. It always returns the post-send screen.
- Command-output capture (`run_command`) is best-effort; interactive TUIs can
  defeat it — fall back to `send_keys` + `read_terminal`.
