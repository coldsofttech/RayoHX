"""Downloading one media playlist from start to finish.

``MediaDownload`` prepares everything (strategy, disk space, working folder, resume state), runs the
segment pipeline, and then commits the output or cleans up. Whatever happens, it leaves behind only
what a later resume needs: nothing after a success, and the state plus the data that cannot be
recreated after a failure or a cancellation.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from rayohx._download._sinks import OutputSink
    from rayohx._download._state import ResumeState
    from rayohx._download._storage import SizeEstimator
    from rayohx._download._workspace import Workspace
    from rayohx._http import HttpClient
    from rayohx.cancellation import CancellationToken
    from rayohx.config import DownloadConfig
    from rayohx.enums import ContainerFormat, StorageStrategy
    from rayohx.events import EventBus
    from rayohx.models import DownloadProgress, MediaPlaylist, StorageMetrics, Variant

logger = logging.getLogger(__name__)


def _uses_disk(strategy: StorageStrategy) -> bool:
    """Whether ``strategy`` keeps segments in files on disk."""
    from rayohx.enums import StorageStrategy

    return strategy in {StorageStrategy.TEMPORARY, StorageStrategy.HYBRID}


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadSummary:
    """What a finished download did."""

    strategy: StorageStrategy
    total_segments: int
    #: Segments that did not need downloading because an earlier run had them.
    resumed_segments: int
    metrics: StorageMetrics
    #: The figures at the moment the last segment was written.
    progress: DownloadProgress
    elapsed_seconds: float
    output: Path | None


class MediaDownload:
    """Downloads the segments of ``playlist`` into ``sink``.

    ``cancel`` should be the same token the ``client`` was built with, so that waiting requests
    stop as soon as the download is cancelled.

    When ``container`` is given, every segment is checked against it. With
    ``config.output.validate`` the finished output is validated before it is put in place, as
    ``output_container`` (the same as ``container`` unless the segments are re-wrapped).
    ``on_finalizing`` is called once all segments are written, just before that final step.
    """

    def __init__(
        self,
        playlist: MediaPlaylist,
        *,
        client: HttpClient,
        config: DownloadConfig,
        sink: OutputSink,
        variant: Variant | None = None,
        events: EventBus | None = None,
        download_id: str | None = None,
        cancel: CancellationToken | None = None,
        container: ContainerFormat | None = None,
        output_container: ContainerFormat | None = None,
        on_finalizing: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        import uuid

        self._container = container
        self._output_container = output_container or container
        self._on_finalizing = on_finalizing
        self._playlist = playlist
        self._client = client
        self._config = config
        self._sink = sink
        self._variant = variant
        self._events = events
        self._download_id = download_id or uuid.uuid4().hex[:12]
        self._cancel = cancel
        self._clock = clock
        self._space_warned = False

    @property
    def download_id(self) -> str:
        """The identifier events and log lines carry."""
        return self._download_id

    def run(self) -> DownloadSummary:
        """Download and commit the output.

        Raises:
            UnsupportedPlaylistError: For live streams and protected (DRM) streams.
            OutputExistsError: If the output exists and overwriting was not allowed.
            InsufficientStorageError: If the disk cannot hold the download.
            SegmentDownloadError: If a segment cannot be downloaded.
            CancellationError: If the download was cancelled.
        """
        from rayohx._crypto import require_supported_encryption
        from rayohx._download._state import playlist_signature
        from rayohx._download._storage import (
            SizeEstimator,
            choose_strategy,
            validate_strategy,
        )
        from rayohx._download._workspace import Workspace, resolve_workspace_root, workspace_key
        from rayohx.errors import DownloadError, UnsupportedPlaylistError

        started = self._clock()
        playlist = self._playlist
        segments = playlist.segments
        if not playlist.is_vod:
            raise UnsupportedPlaylistError(
                "This is a live stream, which is not supported.",
                hint="Only complete (video on demand) playlists can be downloaded.",
            )
        if not segments:
            raise DownloadError("The playlist has no segments to download.")
        require_supported_encryption(segments)

        config = self._config
        sink = self._sink
        strategy = choose_strategy(
            config.storage.strategy, sink_supports_resume=sink.supports_resume
        )
        validate_strategy(strategy, sink_supports_resume=sink.supports_resume)
        sink.preflight()

        estimator = SizeEstimator.for_playlist(playlist, self._variant)
        signature = playlist_signature(segments)
        wants_state = config.resume and sink.supports_resume
        needs_workspace = wants_state or _uses_disk(strategy)
        # The folder is named by address and output only. A changed stream finds old state there
        # whose fingerprint no longer matches, and discards it instead of leaving it behind.
        root = resolve_workspace_root(
            config.storage.workspace_dir,
            sink.target,
            workspace_key(playlist.uri, sink.target.name if sink.target else ""),
        )
        output_dir = sink.target.parent if sink.target else root
        self._check_space(strategy, estimator, output_dir, root)

        if not needs_workspace:
            return self._run(strategy, estimator, signature, None, started)
        workspace = Workspace(root)
        with workspace:
            summary = self._run(strategy, estimator, signature, workspace, started)
        workspace.clean(keep_state=False, keep_segments=False)
        return summary

    # --- one run ---------------------------------------------------------------------------

    def _run(
        self,
        strategy: StorageStrategy,
        estimator: SizeEstimator,
        signature: str,
        workspace: Workspace | None,
        started: float,
    ) -> DownloadSummary:
        from pathlib import Path

        from rayohx._crypto import KeyProvider
        from rayohx._download._fetcher import HlsSegmentFetcher
        from rayohx._download._pipeline import SegmentPipeline
        from rayohx._download._progress import ProgressTracker
        from rayohx._download._state import StateFile
        from rayohx._download._storage import StorageTracker, make_store
        from rayohx.enums import DownloadState

        config = self._config
        sink = self._sink
        segments = self._playlist.segments
        tracker = StorageTracker()
        state_file = StateFile(workspace.state_path) if workspace else None

        saved = None
        if workspace is not None and state_file is not None:
            if config.resume:
                saved = state_file.load(
                    signature=signature, total_segments=len(segments), strategy=strategy.value
                )
            if saved is None:
                # Nothing valid to continue from: staged segments of another run must not leak in.
                workspace.reset()

        offset = saved.written_bytes if saved and saved.next_index else None
        have = sink.open(resume_offset=offset)
        start_index = saved.next_index if saved and offset and have == offset else 0
        if offset and have != offset:
            logger.info("The partial output could not be reused, so the download starts over.")

        segments_dir = workspace.segments_path if workspace else Path()
        store = make_store(strategy, config.storage, tracker, segments_dir)
        progress = ProgressTracker(len(segments), estimator, tracker, clock=self._clock)
        reused = len([index for index in store.existing() if index >= start_index])
        progress.segments_completed(start_index)
        tracker.written(have)

        def checkpoint(next_index: int, written: int) -> None:
            if state_file is not None:
                state_file.save(self._state(signature, strategy, next_index, written))

        if state_file is not None:
            checkpoint(start_index, have)

        fetcher = HlsSegmentFetcher(
            self._client,
            segments,
            KeyProvider(
                self._client,
                fetcher=config.key_fetcher,
                allow_file_keys=config.allow_file_keys,
            ),
            container=self._container,
        )
        pipeline = SegmentPipeline(
            segments=segments,
            fetcher=fetcher,
            store=store,
            sink=sink,
            strategy=strategy,
            concurrency=config.concurrency,
            storage=config.storage,
            tracker=tracker,
            progress=progress,
            estimator=estimator,
            cancel=self._cancel,
            bus=self._events,
            download_id=self._download_id,
            start_index=start_index,
            on_checkpoint=checkpoint if state_file is not None else None,
            recheck_space=lambda: self._check_space(
                strategy,
                estimator,
                sink.target.parent if sink.target else Path.cwd(),
                workspace.path if workspace else Path.cwd(),
            ),
            clock=self._clock,
        )
        try:
            pipeline.run()
            final = progress.snapshot(DownloadState.FINALIZING, 0)
            if self._on_finalizing is not None:
                self._on_finalizing()
            output = sink.commit(self._validator())
        except BaseException as exc:
            self._abandon(strategy, workspace, exc)
            raise
        return DownloadSummary(
            strategy=strategy,
            total_segments=len(segments),
            resumed_segments=start_index + reused,
            metrics=tracker.snapshot(),
            progress=final,
            elapsed_seconds=self._clock() - started,
            output=output,
        )

    def _validator(self) -> Callable[[Path], None] | None:
        container = self._output_container
        if container is None or not self._config.output.validate:
            return None
        from rayohx._download._containers import validate_output

        return lambda path: validate_output(container, path)

    def _abandon(
        self, strategy: StorageStrategy, workspace: Workspace | None, error: BaseException
    ) -> None:
        """After a failure or cancellation keep only what resuming needs.

        A finished download that failed its final check has nothing to resume, so it keeps nothing.
        """
        from rayohx.errors import FinalizationError

        keep = (
            self._config.resume
            and self._config.storage.keep_state_on_failure
            and not isinstance(error, FinalizationError)
        )
        resumable = keep and self._sink.supports_resume
        self._sink.abort(keep_partial=resumable)
        if workspace is None:
            return
        keep_segments = keep and _uses_disk(strategy)
        workspace.clean(keep_state=resumable or keep_segments, keep_segments=keep_segments)

    def _state(
        self, signature: str, strategy: StorageStrategy, next_index: int, written: int
    ) -> ResumeState:
        from rayohx._download._state import ResumeState
        from rayohx._redaction import redact_url

        return ResumeState(
            signature=signature,
            total_segments=len(self._playlist.segments),
            strategy=strategy.value,
            next_index=next_index,
            written_bytes=written,
            source=redact_url(self._playlist.uri),
        )

    def _check_space(
        self,
        strategy: StorageStrategy,
        estimator: SizeEstimator,
        output_dir: Path,
        workspace_dir: Path,
    ) -> None:
        from rayohx._download._storage import check_disk_space, space_needed

        if not self._config.storage.check_space:
            if not self._space_warned:
                logger.warning("The disk space check is turned off.")
                self._space_warned = True
            return
        estimate = estimator.total_bytes()
        if not estimate:
            return
        need = space_needed(
            strategy, estimate, self._config.storage, writes_file=self._sink.writes_file
        )
        check_disk_space(
            need,
            output_dir=output_dir,
            workspace_dir=workspace_dir,
            reserve_bytes=self._config.storage.reserve_bytes,
        )
