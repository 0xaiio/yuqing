from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread, Timer

from sqlmodel import Session
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import Settings, get_settings
from app.connectors import BaseConnector
from app.database import engine
from app.import_pipeline import ImportPipeline
from app.repository import GalleryRepository


@dataclass
class WatchStatus:
    watching: bool
    processing: bool = False
    queued_file_count: int = 0
    last_error: str | None = None
    last_event_at: datetime | None = None
    last_completed_at: datetime | None = None


class SourceWatchManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._observer: Observer | None = None
        self._handlers: dict[int, SourceImportEventHandler] = {}
        self._watches: dict[int, object] = {}
        self._roots: dict[int, str] = {}
        self._statuses: dict[int, WatchStatus] = {}
        self._task_queue: Queue[int] = Queue()
        self._queued_paths: dict[int, dict[str, Path]] = {}
        self._queued_source_ids: set[int] = set()
        self._processing_source_ids: set[int] = set()
        self._worker_thread: Thread | None = None
        self._stop_event = Event()
        self._lock = Lock()

    def refresh(self) -> None:
        if not self.settings.watcher_enabled:
            return

        with self._lock:
            observer = self._ensure_observer()
            self._ensure_worker()
            with Session(engine) as session:
                repository = GalleryRepository(session)
                sources = repository.list_sources()

            desired_source_ids = set()
            for source in sources:
                source_id = source.id or 0
                existing_status = self._statuses.get(source_id, WatchStatus(watching=False))

                if not source.enabled:
                    self._queued_source_ids.discard(source_id)
                    self._statuses[source_id] = WatchStatus(
                        watching=False,
                        processing=False,
                        queued_file_count=0,
                        last_error=existing_status.last_error,
                        last_event_at=existing_status.last_event_at,
                        last_completed_at=existing_status.last_completed_at,
                    )
                    self._queued_paths.pop(source_id, None)
                    self._unschedule_source(source_id, observer)
                    continue

                desired_source_ids.add(source_id)
                root_path = Path(source.root_path)
                if not root_path.exists():
                    self._queued_source_ids.discard(source_id)
                    self._statuses[source_id] = WatchStatus(
                        watching=False,
                        processing=False,
                        queued_file_count=0,
                        last_error="目录不存在，无法启用实时监听。",
                        last_event_at=existing_status.last_event_at,
                        last_completed_at=existing_status.last_completed_at,
                    )
                    self._queued_paths.pop(source_id, None)
                    self._unschedule_source(source_id, observer)
                    continue

                if self._is_inside_import_root(root_path):
                    self._queued_source_ids.discard(source_id)
                    self._statuses[source_id] = WatchStatus(
                        watching=False,
                        processing=False,
                        queued_file_count=0,
                        last_error="来源目录位于归档目录内部，已跳过以避免循环导入。",
                        last_event_at=existing_status.last_event_at,
                        last_completed_at=existing_status.last_completed_at,
                    )
                    self._queued_paths.pop(source_id, None)
                    self._unschedule_source(source_id, observer)
                    continue

                current_root = self._roots.get(source_id)
                if current_root != str(root_path) or source_id not in self._watches:
                    self._unschedule_source(source_id, observer)
                    handler = SourceImportEventHandler(source_id=source_id, manager=self)
                    watch = observer.schedule(
                        handler,
                        str(root_path),
                        recursive=self.settings.watcher_recursive,
                    )
                    self._handlers[source_id] = handler
                    self._watches[source_id] = watch
                    self._roots[source_id] = str(root_path)

                self._statuses[source_id] = WatchStatus(
                    watching=True,
                    processing=source_id in self._processing_source_ids,
                    queued_file_count=len(self._queued_paths.get(source_id, {})),
                    last_error=existing_status.last_error,
                    last_event_at=existing_status.last_event_at,
                    last_completed_at=existing_status.last_completed_at,
                )

            for source_id in list(self._watches):
                if source_id not in desired_source_ids:
                    self._queued_source_ids.discard(source_id)
                    self._queued_paths.pop(source_id, None)
                    self._unschedule_source(source_id, observer)
                    self._statuses[source_id] = WatchStatus(watching=False)

    def shutdown(self) -> None:
        with self._lock:
            self._stop_event.set()
            if self._observer is not None:
                for handler in self._handlers.values():
                    handler.cancel()
                self._observer.stop()
                self._observer.join(timeout=5)
                self._observer = None
            if self._worker_thread is not None:
                self._worker_thread.join(timeout=5)
                self._worker_thread = None
            self._handlers.clear()
            self._watches.clear()
            self._roots.clear()
            self._queued_paths.clear()
            self._queued_source_ids.clear()
            self._processing_source_ids.clear()

    def enqueue_paths(self, source_id: int, paths: list[Path]) -> None:
        valid_paths = [path for path in paths if path.exists()]
        if not valid_paths:
            return

        now = datetime.now(timezone.utc)
        with self._lock:
            pending = self._queued_paths.setdefault(source_id, {})
            for path in valid_paths:
                pending[str(path.resolve())] = path.resolve()

            status = self._statuses.get(source_id, WatchStatus(watching=True))
            status.watching = True
            status.last_error = None
            status.last_event_at = now
            status.queued_file_count = len(pending)
            self._statuses[source_id] = status

            if source_id not in self._queued_source_ids and source_id not in self._processing_source_ids:
                self._task_queue.put(source_id)
                self._queued_source_ids.add(source_id)

    def get_status(self, source_id: int | None) -> WatchStatus:
        if source_id is None:
            return WatchStatus(watching=False)
        return self._statuses.get(source_id, WatchStatus(watching=False))

    def active_watch_count(self) -> int:
        return sum(1 for status in self._statuses.values() if status.watching)

    def queued_task_count(self) -> int:
        return len(self._queued_source_ids)

    def worker_busy(self) -> bool:
        return bool(self._processing_source_ids)

    def _ensure_observer(self) -> Observer:
        if self._observer is None:
            self._observer = Observer()
            self._observer.daemon = True
            self._observer.start()
        return self._observer

    def _ensure_worker(self) -> None:
        if self._worker_thread is not None and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = Thread(target=self._worker_loop, name="watch-import-worker", daemon=True)
        self._worker_thread.start()

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                source_id = self._task_queue.get(timeout=0.5)
            except Empty:
                continue

            with self._lock:
                self._queued_source_ids.discard(source_id)
                pending_paths = list(self._queued_paths.get(source_id, {}).values())
                self._queued_paths[source_id] = {}
                status = self._statuses.get(source_id, WatchStatus(watching=False))
                status.processing = True
                status.queued_file_count = 0
                self._statuses[source_id] = status
                self._processing_source_ids.add(source_id)

            if pending_paths:
                self._process_paths(source_id, pending_paths)

            with self._lock:
                self._processing_source_ids.discard(source_id)
                status = self._statuses.get(source_id, WatchStatus(watching=False))
                status.processing = False
                status.queued_file_count = len(self._queued_paths.get(source_id, {}))
                if status.watching:
                    status.last_completed_at = datetime.now(timezone.utc)
                self._statuses[source_id] = status

                if status.queued_file_count > 0 and source_id not in self._queued_source_ids:
                    self._task_queue.put(source_id)
                    self._queued_source_ids.add(source_id)

            self._task_queue.task_done()

    def _process_paths(self, source_id: int, paths: list[Path]) -> None:
        with Session(engine) as session:
            repository = GalleryRepository(session)
            source = repository.get_source(source_id)
            if source is None or not source.enabled:
                with self._lock:
                    self._statuses[source_id] = WatchStatus(
                        watching=False,
                        processing=False,
                        queued_file_count=0,
                        last_error="来源不存在或已被禁用。",
                    )
                return

            job = ImportPipeline(session).run(source=source, limit=len(paths), explicit_paths=paths)

        with self._lock:
            status = self._statuses.get(source_id, WatchStatus(watching=True))
            status.watching = True
            status.last_error = job.error_message
            self._statuses[source_id] = status

    def _unschedule_source(self, source_id: int, observer: Observer) -> None:
        handler = self._handlers.pop(source_id, None)
        if handler is not None:
            handler.cancel()
        watch = self._watches.pop(source_id, None)
        if watch is not None:
            observer.unschedule(watch)
        self._roots.pop(source_id, None)

    def _is_inside_import_root(self, root_path: Path) -> bool:
        try:
            return root_path.resolve().is_relative_to(self.settings.import_root.resolve())
        except FileNotFoundError:
            return False


class SourceImportEventHandler(FileSystemEventHandler):
    def __init__(self, source_id: int, manager: SourceWatchManager) -> None:
        self.source_id = source_id
        self.manager = manager
        self._pending: dict[str, Path] = {}
        self._timer: Timer | None = None
        self._lock = Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle_event(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle_event(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._handle_event(event, moved_path=getattr(event, "dest_path", None))

    def cancel(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._pending.clear()

    def _handle_event(self, event: FileSystemEvent, moved_path: str | None = None) -> None:
        candidate = Path(moved_path or event.src_path)
        if event.is_directory or not BaseConnector.is_supported_media(candidate):
            return

        with self._lock:
            self._pending[str(candidate.resolve())] = candidate.resolve()
            if self._timer is not None:
                self._timer.cancel()
            self._timer = Timer(self.manager.settings.watcher_debounce_seconds, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            paths = [path for path in self._pending.values() if path.exists()]
            self._pending.clear()
            self._timer = None
        if paths:
            self.manager.enqueue_paths(self.source_id, paths)
