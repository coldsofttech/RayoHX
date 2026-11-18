"""The queue with the real engine over real sockets: pause, resume and a killed process."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

from rayohx.platform import Rayo
from rayohx.platform.jobs import JobState
from rayohx.platform.secrets import MemorySecretStore
from tests.helpers.media import ts_payload
from tests.helpers.servers import LocalServer, Reply, Seen

COUNT = 16
DELAY = 0.25
OPTIONS = {"concurrency": 2, "output": {"format": "ts"}}


def playlist() -> bytes:
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:4", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for index in range(COUNT):
        lines += ["#EXTINF:4.0,", f"seg{index}.ts"]
    return ("\n".join([*lines, "#EXT-X-ENDLIST"]) + "\n").encode()


def routes() -> dict[str, Callable[[Seen], Reply]]:
    table: dict[str, Callable[[Seen], Reply]] = {
        "/vod/index.m3u8": lambda _s: Reply(body=playlist())
    }
    for index in range(COUNT):
        table[f"/vod/seg{index}.ts"] = lambda _s, i=index: Reply(
            body=ts_payload(i, 20), delay=DELAY, headers={"Content-Type": "video/mp2t"}
        )
    return table


def expected() -> bytes:
    return b"".join(ts_payload(i, 20) for i in range(COUNT))


def fetched(server: LocalServer) -> Counter[int]:
    return Counter(
        int(r.path.removeprefix("/vod/seg").removesuffix(".ts"))
        for r in server.requests
        if r.path.startswith("/vod/seg")
    )


def wait_for(condition: Callable[[], bool], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        time.sleep(0.05)


def resume_index(downloads: Path) -> int:
    states = list(downloads.glob(".rayohx-*/state.json"))
    return json.loads(states[0].read_text())["next_index"] if states else 0


def make(tmp_path: Path) -> Rayo:
    return Rayo(home=tmp_path / "home", download_dir=tmp_path / "dl", secrets=MemorySecretStore())


def test_a_real_download_through_the_queue(tmp_path: Path) -> None:
    with LocalServer(routes()) as server, make(tmp_path) as rayo:
        job = rayo.queue.add(f"{server.url}/vod/index.m3u8", options=OPTIONS, output_name="a.ts")
        rayo.queue.start()
        assert rayo.queue.wait_idle(60)
        done = rayo.queue.get(job.id)
        assert done is not None
        assert done.state is JobState.COMPLETED
        assert Path(done.output_path or "").read_bytes() == expected()
        assert done.progress is not None
        assert done.progress["completed_segments"] == COUNT
        types = {e.type for e in rayo.event_store.query(job_id=job.id, limit=500)}
        assert {"download.started", "queue.job_completed"} <= types


def test_pause_keeps_the_work_and_resume_does_not_repeat_it(tmp_path: Path) -> None:
    with LocalServer(routes()) as server, make(tmp_path) as rayo:
        job = rayo.queue.add(f"{server.url}/vod/index.m3u8", options=OPTIONS, output_name="p.ts")
        rayo.queue.start()
        wait_for(lambda: len(fetched(server)) >= 6)
        assert rayo.queue.pause(job.id).ok
        wait_for(lambda: (rayo.queue.get(job.id) or job).state is JobState.PAUSED)
        assert rayo.queue.stats()["active"] == 0
        kept = resume_index(tmp_path / "dl")
        assert kept >= 1
        assert not (tmp_path / "dl" / "p.ts").exists()

        rayo.queue.resume(job.id)
        assert rayo.queue.wait_idle(60)
        done = rayo.queue.get(job.id)
        assert done is not None
        assert done.state is JobState.COMPLETED
        assert Path(done.output_path or "").read_bytes() == expected()
        counts = fetched(server)
        assert all(counts[i] == 1 for i in range(kept)), (kept, counts)


def test_a_killed_process_loses_nothing(tmp_path: Path) -> None:
    worker = Path(__file__).with_name("_queue_worker.py")
    with LocalServer(routes()) as server:
        parent = make(tmp_path)
        child = subprocess.Popen(
            [sys.executable, str(worker), str(tmp_path / "home"), str(tmp_path / "dl")],
            stdout=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        try:
            assert child.stdout is not None
            assert child.stdout.readline().strip() == "running"
            job = parent.queue.add(
                f"{server.url}/vod/index.m3u8", options=OPTIONS, output_name="k.ts"
            )
            assert parent.queue.stats()["runner"] == "another process"
            wait_for(lambda: len(fetched(server)) >= 8)
            wait_for(lambda: resume_index(tmp_path / "dl") >= 2)
        finally:
            os.kill(child.pid, signal.SIGKILL)
            child.wait()
        kept = resume_index(tmp_path / "dl")

        left = parent.queue.get(job.id)
        assert left is not None
        assert left.state in {JobState.DOWNLOADING, JobState.PREPARING}  # the crash left it so
        assert parent.queue.stats()["runner"] == "none"

        recovered = parent.queue.start()
        assert recovered == [job.id]
        assert parent.queue.wait_idle(60)
        done = parent.queue.get(job.id)
        assert done is not None
        assert done.state is JobState.COMPLETED
        assert done.recovered
        assert Path(done.output_path or "").read_bytes() == expected()
        counts = fetched(server)
        assert all(counts[i] == 1 for i in range(kept)), (kept, counts)
        parent.close()


@pytest.mark.skipif(sys.platform == "win32", reason="uses POSIX signals")
def test_stopping_the_queue_gracefully_requeues_and_the_next_start_finishes(
    tmp_path: Path,
) -> None:
    with LocalServer(routes()) as server:
        with make(tmp_path) as first:
            job = first.queue.add(
                f"{server.url}/vod/index.m3u8", options=OPTIONS, output_name="g.ts"
            )
            first.queue.start()
            wait_for(lambda: len(fetched(server)) >= 5)
            first.queue.stop()
            stopped = first.queue.get(job.id)
            assert stopped is not None
            assert stopped.state is JobState.QUEUED
        with make(tmp_path) as second:
            second.queue.start()
            assert second.queue.wait_idle(60)
            done = second.queue.get(job.id)
            assert done is not None
            assert done.state is JobState.COMPLETED
            assert Path(done.output_path or "").read_bytes() == expected()


def real_media_routes() -> dict[str, Callable[[Seen], Reply]]:
    """A playlist of a real H.264 + AAC transport stream cut into three segments."""
    data = (Path(__file__).resolve().parents[1] / "fixtures" / "media" / "h264_aac.ts").read_bytes()
    packets = len(data) // 188
    bounds = [(packets * i // 3) * 188 for i in range(3)] + [packets * 188]
    lines = ["#EXTM3U", "#EXT-X-TARGETDURATION:2", "#EXT-X-PLAYLIST-TYPE:VOD"]
    routes: dict[str, Callable[[Seen], Reply]] = {}
    for index in range(3):
        lines += ["#EXTINF:1.3,", f"seg{index}.ts"]
        part = data[bounds[index] : bounds[index + 1]]
        routes[f"/real/seg{index}.ts"] = lambda _s, p=part: Reply(body=p)
    routes["/real/index.m3u8"] = lambda _s: Reply(
        body=("\n".join([*lines, "#EXT-X-ENDLIST"]) + "\n").encode()
    )
    return routes


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="needs FFmpeg"
)
def test_the_archive_profile_makes_a_matroska_file_through_the_queue(tmp_path: Path) -> None:
    with LocalServer(real_media_routes()) as server, make(tmp_path) as rayo:
        job = rayo.queue.add(f"{server.url}/real/index.m3u8", profile="archive", output_name="film")
        assert job.profile_id == "archive"
        rayo.queue.start()
        assert rayo.queue.wait_idle(60)
        done = rayo.queue.get(job.id)
        assert done is not None
        assert done.state is JobState.COMPLETED, done.error_message
        path = Path(done.output_path or "")
        assert path.suffix == ".mkv"
        streams = json.loads(
            subprocess.run(
                ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],  # noqa: S607
                capture_output=True, text=True, check=True,
            ).stdout
        )["streams"]  # fmt: skip
        assert sorted(s["codec_type"] for s in streams) == ["audio", "video"]
        assert not list((tmp_path / "dl").glob(".*"))  # no leftovers
