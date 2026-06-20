# Recording the demo GIF

The README leads with `docs/demo.gif`. Record it last, once you're happy with the output.

Suggested 3-beat script (keep it under ~15s, it autoplays in the README):

1. `radar wip` — the headline. Let the STALE flag land.
2. `radar log --since 2026-06-01` — the history view scrolls.
3. `radar log --recap` — the shareable card pops at the end.

Tips:
- Use a clean, high-contrast terminal theme and a comfortably large font.
- A real account with a few repos in flight sells it better than a demo account.
- Tools: [vhs](https://github.com/charmbracelet/vhs) (scriptable, reproducible) or
  [asciinema](https://asciinema.org) + `agg` to render a GIF. On Windows, ScreenToGif works.
- Save the result as `docs/demo.gif`.
