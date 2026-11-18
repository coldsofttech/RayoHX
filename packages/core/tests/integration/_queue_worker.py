"""A separate process that runs the queue, so a test can kill it half way."""

import sys
import time
from pathlib import Path

from rayohx.platform import Rayo
from rayohx.platform.secrets import MemorySecretStore


def main(home: str, downloads: str) -> None:
    rayo = Rayo(home=Path(home), download_dir=Path(downloads), secrets=MemorySecretStore())
    rayo.queue.start()
    sys.stdout.write("running\n")
    sys.stdout.flush()
    while True:
        time.sleep(0.1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
