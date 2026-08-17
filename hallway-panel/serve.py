"""Run the panel service.

    set HA_TOKEN=...
    python serve.py                 # http://127.0.0.1:8099/preview

The ESP32 fetches /panel.png with an If-None-Match header; the browser watches
/preview, which reloads itself every 30 seconds.
"""

from __future__ import annotations

import logging
import os

from panel.config import load
from panel.server import create_app


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("PANEL_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load()
    app = create_app(config)

    host = os.environ.get("PANEL_HOST", "0.0.0.0")
    port = int(os.environ.get("PANEL_PORT", "8099"))
    log = logging.getLogger(__name__)
    log.info("preview on http://127.0.0.1:%d/preview", port)

    try:
        from waitress import serve as waitress_serve
    except ImportError:
        # Fine for poking at the layout from a checkout; the add-on installs
        # waitress, so the container never takes this path.
        log.warning("waitress not installed, falling back to the Flask dev server")
        app.run(host=host, port=port, threaded=True)
        return 0

    # A render can take a moment and the ESP32 has its own timeout; two threads
    # is enough for one device plus a browser on /preview.
    waitress_serve(app, host=host, port=port, threads=2, ident="hallway-panel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
