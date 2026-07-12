#  Copyright (C) 2025–2026 Comicarr contributors
#
#  This file is part of Comicarr.
#
#  Comicarr is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

"""Machine-readable ownership metadata for bundled third-party libraries.

The companion document in ``docs/architecture/vendor-dependencies.md`` carries
the human-facing provenance and replacement decisions. Keeping the package
names here makes drift detectable in tests before a new vendor is imported.
"""

VENDOR_PROVENANCE = {
    "comictaggerlib": {
        "owner": "Comicarr",
        "source": "bundled ComicTagger 1.3.5 sources",
        "license": "mixed upstream notices; retain source headers",
    },
    "deluge_client": {
        "owner": "Comicarr",
        "source": "bundled deluge-client RPC implementation",
        "license": "MIT (source headers and LICENSE)",
    },
    "mega": {
        "owner": "Comicarr",
        "source": "bundled mega.py implementation",
        "license": "upstream license status requires legal review before redistribution",
    },
    "qbittorrent": {
        "owner": "Comicarr",
        "source": "bundled qBittorrent Web API client",
        "license": "MIT (LICENSE)",
    },
    "rtorrent": {
        "owner": "Comicarr",
        "source": "bundled rTorrent XML-RPC client",
        "license": "MIT (source headers)",
    },
    "transmissionrpc": {
        "owner": "Comicarr",
        "source": "bundled transmissionrpc client 0.11",
        "license": "MIT (source headers)",
    },
    "utorrent": {
        "owner": "Comicarr",
        "source": "bundled uTorrent Web API client",
        "license": "upstream license status requires legal review before redistribution",
    },
}
