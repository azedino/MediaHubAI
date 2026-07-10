from __future__ import annotations

import glob
import os
from pathlib import Path


class Downloader:
    def __init__(self):
        self.last_output = None

    def download(self, *args, **kwargs):
        raise NotImplementedError("Downloader subclasses must implement download()")

    def _locate_output(self, destination, filename_base=None):
        if not destination or not os.path.isdir(destination):
            return None

        if filename_base:
            candidates = glob.glob(os.path.join(destination, f"{filename_base}.*"))
        else:
            candidates = glob.glob(os.path.join(destination, "*.*"))

        if not candidates:
            return None
        return max(candidates, key=os.path.getmtime)

    @staticmethod
    def _locate_from_prepared_path(prepared_path: str | Path) -> str | None:
        """Localiza o arquivo final mesmo após conversão ou pós-processamento."""
        prepared = Path(prepared_path)
        candidates = [Path(value) for value in glob.glob(str(prepared.with_suffix(".*")))]
        candidates = [path for path in candidates if path.is_file() and path.suffix != ".part"]
        if not candidates:
            return None
        return str(max(candidates, key=lambda path: path.stat().st_mtime))
