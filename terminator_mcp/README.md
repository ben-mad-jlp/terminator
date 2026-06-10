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

1. Install the GTK/VTE Python stack Terminator needs (if not already):
   - Linux: your distro's `python3-gi` + `gir1.2-vte-2.91`.
   - macOS (Homebrew): `brew install pygobject3 gtk+3 vte3`.
2. Enable the bridge plugin — either via Terminator's **Preferences →
   Plugins** (tick *MCPBridge*), or in `~/.config/terminator/config`:
   ```ini
   [global_config]
     enabled_plugins = MCPBridge
   ```
   (Also requires `psutil`, a standard Terminator dependency.) Restart
   Terminator. The bridge opens a socket at
   `$XDG_RUNTIME_DIR/terminator-mcp-$UID/bridge.sock` (Linux) or
   `$TMPDIR/terminator-mcp-$UID/bridge.sock` (macOS).
3. Install this package and register it with Claude Code:
   ```sh
   pip install -e .            # from terminator_mcp/
   claude mcp add terminator -- python -m terminator_mcp
   ```

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
