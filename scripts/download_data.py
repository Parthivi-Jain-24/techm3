"""Download real OFAC SDN and OpenSanctions data files.

Usage:
    python scripts/download_data.py                   # Download all
    python scripts/download_data.py --ofac-only        # OFAC SDN + ALT only
    python scripts/download_data.py --opensanctions-only  # OpenSanctions only

Downloads are placed in data/sanctions/ relative to the project root.
Uses only stdlib (urllib) — no pip dependencies required.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve


DOWNLOADS = {
    "ofac_sdn": {
        "url": "https://www.treasury.gov/ofac/downloads/sdn.csv",
        "dest": "data/sanctions/ofac_sdn.csv",
        "desc": "OFAC SDN List (~5 MB)",
    },
    "ofac_alt": {
        "url": "https://www.treasury.gov/ofac/downloads/alt.csv",
        "dest": "data/sanctions/ofac_alt.csv",
        "desc": "OFAC ALT (aliases) (~1 MB)",
    },
    "ofac_add": {
        "url": "https://www.treasury.gov/ofac/downloads/add.csv",
        "dest": "data/sanctions/ofac_add.csv",
        "desc": "OFAC ADD (addresses) (~2 MB)",
    },
    "opensanctions": {
        "url": "https://data.opensanctions.org/datasets/latest/default/targets.simple.csv",
        "dest": "data/sanctions/opensanctions_targets.csv",
        "desc": "OpenSanctions targets (~500 MB)",
    },
}


def _progress_hook(block_num: int, block_size: int, total_size: int) -> None:
    """Show download progress."""
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(100, downloaded * 100 // total_size)
        mb_down = downloaded / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)
        sys.stdout.write(f"\r  [{percent:3d}%] {mb_down:.1f} / {mb_total:.1f} MB")
    else:
        mb_down = downloaded / (1024 * 1024)
        sys.stdout.write(f"\r  {mb_down:.1f} MB downloaded")
    sys.stdout.flush()


def download_file(name: str, info: dict, project_root: Path) -> bool:
    """Download a single file. Returns True on success."""
    dest = project_root / info["dest"]
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"\nDownloading {info['desc']}...")
    print(f"  URL:  {info['url']}")
    print(f"  Dest: {dest}")

    if dest.exists():
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  File already exists ({size_mb:.1f} MB). Skipping. Delete to re-download.")
        return True

    start = time.time()
    try:
        urlretrieve(info["url"], str(dest), reporthook=_progress_hook)
        elapsed = time.time() - start
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"\n  Done! {size_mb:.1f} MB in {elapsed:.1f}s")
        return True
    except (URLError, OSError) as e:
        print(f"\n  FAILED: {e}")
        if dest.exists():
            dest.unlink()
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Download sanctions data files")
    parser.add_argument("--ofac-only", action="store_true", help="Download OFAC files only")
    parser.add_argument("--opensanctions-only", action="store_true", help="Download OpenSanctions only")
    args = parser.parse_args()

    # Find project root (parent of scripts/)
    project_root = Path(__file__).resolve().parent.parent

    print(f"Project root: {project_root}")
    print("=" * 60)

    if args.ofac_only:
        keys = ["ofac_sdn", "ofac_alt", "ofac_add"]
    elif args.opensanctions_only:
        keys = ["opensanctions"]
    else:
        keys = list(DOWNLOADS.keys())

    success = 0
    for key in keys:
        if download_file(key, DOWNLOADS[key], project_root):
            success += 1

    print()
    print("=" * 60)
    print(f"Downloaded {success}/{len(keys)} files successfully.")

    if success < len(keys):
        print("\nTIP: If downloads fail, you can manually download from:")
        for key in keys:
            info = DOWNLOADS[key]
            print(f"  {info['url']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
