Terminator (terminator-mcp fork)
================================

> **This is the `terminator-mcp` fork.** It runs side-by-side with an
> unmodified system Terminator and adds an MCP bridge plugin so Claude
> (and other MCP clients) can read from and drive the running terminals.
> See [`terminator_mcp/README.md`](terminator_mcp/README.md) for install
> steps, tools, and fork notes (config dir, D-Bus bus name, etc.).
>
> Visible additions: minimap, line-number gutter, bookmarks, auto-assigned
> `term-N` titles, Claude-sparkle launcher icon.
>
> Push policy: this fork lives at `ben-mad-jlp/terminator_mcp`; nothing
> goes upstream to `gnome-terminator/terminator`.

The rest of this README is the upstream Terminator documentation, kept
as-is for reference.

---

Started by Chris Jones <cmsj@tenshu.net> in 2007, maintained from 2014 to 2020 by Stephen Boddy, currently maintained by Matt Rose. Terminator has had contributions from countless others listed in the [AUTHORS](AUTHORS) file

## Description

Terminator was originally developed by Chris Jones in 2007 as a simple, 300-ish line python script.  Since then, it has become The Robot Future of Terminals.  Originally inspired by projects like quadkonsole and gnome-multi-term and more recently by projects like Iterm2, and Tilix, It lets you combine and recombine terminals to suit the style you like.  If you live at the command-line, or are logged into 10 different remote machines at once, you should definitely try out Terminator.

When you run **`Terminator`**, you will get a terminal in a window, just like almost 
every other terminal emulator available. There is also a titlebar which will
update as shells/programs inside the terminal tell it to. Also on the titlebar
is a small button that opens the grouping menu. From here you can put terminals
into groups, which allows you to control multiple terminals simultaneously.

## New home on GitHub

In April of 2020 we started moving **`Terminator`** to GitHub. A new team wanted to continue the work of the original authors.

You can find the project on https://github.com/gnome-terminator/terminator

## Installing

Terminator is available for most (if not all) Linux distributions from the distribution's repository of binary packages.  It is also available on FreeBSD.   Please search your repository for `terminator`  If you want to find information on how to enable an updated package repository for your OS, build from source, or want to run the bleeding-edge master version, you can follow the instructions in [INSTALL.md](https://github.com/gnome-terminator/terminator/blob/master/INSTALL.md)


#### Quick Start:

Create more terminals by:  
 - horizontal split: `Ctrl-Shift-o`
 - vertical split: `Ctrl-Shift-e`

Shift focus to:  
 - next terminal: `Ctrl-Shift-n`
 - previous terminal: `Ctrl-Shift-p`

New tab: `Ctrl-Shift-t`

New window: `Ctrl-Shift-i`

Close terminal or tab:  
 - `Ctrl-Shift-w`
 - or right mouse click -> Close  

Close window with all it's terminals and tabs: `Ctrl-Shift-q`

Reset zoom: `Ctrl-0`

Terminator Preferences menu:  
 - right mouse click -> Preferences  

These and more modifiable shortcuts in:  
 - right mouse click -> Preferences -> Keybindings tab  

Web Documentation: 
 - press `F1` or at https://gnome-terminator.readthedocs.io/en/latest/

More info about shortcuts and cli config in man pages:  
 - `man terminator`
 - `man terminator_config`

## Contributing

Any help is welcome with the Terminator project.

* [Open issues for bugs or enhancements](https://github.com/gnome-terminator/terminator/issues/new)
* [Join our chat room on gitter.im for general questions](https://gitter.im/gnome-terminator/community)
* [Help translating Terminator](TRANSLATION.md)

You can find old bugs and questions in the launchpad project, but please don't post anything new there.

* https://answers.launchpad.net/terminator
* https://bugs.launchpad.net/terminator

## Origins

Terminator began by shamelessly copying code from the vte-demo.py in the vte 
widget package, and the gedit terminal plugin (which was fantastically 
useful at figuring out vte's API).

vte-demo.py was not my code and is copyright its original author. While it 
does not contain any specific licensing information in it, the VTE package 
appears to be licenced under LGPL v2.

The original version 0.1 release of Terminator was on Saturday, 28 July 2007.
 [Here is the archived Terminator 0.1 release announcement](http://cmsj.net/2007/07/28/terminator-01-released.html)

## Licensing

The gedit terminal plugin is part of the gedit-plugins package, which is 
licenced under GPL v2 or later.

I am thus licensing Terminator as GPL v2 only.

Cristian Grada provided the old icon under the same licence.
Cory Kontros provided the new icon under the CC-by-SA licence.
For other authorship information, see debian/copyright
