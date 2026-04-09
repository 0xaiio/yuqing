from __future__ import annotations

import json
import threading

from sqlmodel import Session

from app.config import Settings, get_settings
from app.database import engine
from app.models import BackgroundTask, utc_now
from app.repository import GalleryRepository
from app.video_reanalysis import reanalyze_video_record

VIDEO_REANALYZE_ALL_TASK = "video_reanalyze_all"


class BackgroundTaskManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._lock = threading.Lock()
        self._threads: dict[int, threading.Thread] = {}

    def start_video_reanalysis_all(self) -> BackgroundTask:
        with self._lock:
            with Session(engine) as session:
                repository = GalleryRepository(session)
                existing = repository.find_running_background_task(VIDEO_REANALYZE_ALL_TASK)
                if existing is not None:
                    return existing

                video_ids = [video.id for video in repository.list_recent_videos(limit=5000) if video.id]
                task = repository.create_background_task(
                    BackgroundTask(
                        task_type=VIDEO_REANALYZE_ALL_TASK,
                        title="批量重分析全部视频",
                        status="queued",
                        total_items=len(video_ids),
                        payload=json.dumps({"video_ids": video_ids}, ensure_ascii=False),
                    )
                )

            worker = threading.Thread(
                target=self._run_video_reanalysis_all,
                args=(task.id or 0, video_ids),
                daemon=True,
                name=f"video-reanalyze-{task.id}",
            )
            self._threads[task.id or 0] = worker
            worker.start()
            return task

    def list_tasks(self, limit: int = 80) -> list[BackgroundTask]:
        with Session(engine) as session:
            return GalleryRepository(session).list_background_tasks(limit=limit)

    def get_task(self, task_id: int) -> BackgroundTask | None:
        with Session(engine) as session:
            return GalleryRepository(session).get_background_task(task_id)

    def _run_video_reanalysis_all(self, task_id: int, video_ids: list[int]) -> None:
        try:
            self._mark_running(task_id)
            completed = 0
            failed = 0
            last_error: str | None = None

            for video_id in video_ids:
                try:
                    with Session(engine) as session:
                        repository = GalleryRepository(session)
                        video = repository.get_video(video_id)
                        if video is None:
                            raise ValueError(f"Video not found: {video_id}")
                        reanalyze_video_record(session, video, settings=self.settings)
                    completed += 1
                except Exception as error:  # pragma: no cover - best effort background accounting
                    failed += 1
                    last_error = str(error)
                self._update_progress(task_id, completed=completed, failed=failed, error_message=last_error)

            self._mark_finished(task_id, completed=completed, failed=failed, error_message=last_error)
        finally:
            with self._lock:
                self._threads.pop(task_id, None)

    def _mark_running(self, task_id: int) -> None:
        with Session(engine) as session:
            repository = GalleryRepository(session)
            task = repository.get_background_task(task_id)
            if task is None:
                return
            task.status = "running"
            task.started_at = utc_now()
            repository.save_background_task(task)

    def _update_progress(
        self,
        task_id: int,
        *,
        completed: int,
        failed: int,
        error_message: str | None,
    ) -> None:
        with Session(engine) as session:
            repository = GalleryRepository(session)
            task = repository.get_background_task(task_id)
            if task is None:
                return
            task.completed_items = completed
            task.failed_items = failed
            task.error_message = error_message
            repository.save_background_task(task)

    def _mark_finished(
        self,
        task_id: int,
        *,
        completed: int,
        failed: int,
        error_message: str | None,
    ) -> None:
        with Session(engine) as session:
            repository = GalleryRepository(session)
            task = repository.get_background_task(task_id)
            if task is None:
                return
            task.completed_items = completed
            task.failed_items = failed
            task.error_message = error_message
            task.status = "failed" if failed and completed == 0 else "completed"
            task.finished_at = utc_now()
            repository.save_background_task(task)
