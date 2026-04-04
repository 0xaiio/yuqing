import json
from pathlib import Path
from uuid import uuid4

import imagehash
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from sqlmodel import Session

from app.ai import AIAnalyzer
from app.config import get_settings
from app.database import create_db_and_tables, get_session
from app.embeddings import VectorEmbeddingService, serialize_vector
from app.face_clustering import FaceClusteringService
from app.import_pipeline import ImportPipeline
from app.repository import GalleryRepository
from app.schemas import (
    FaceClusterRead,
    FaceClusterRenameRequest,
    HealthRead,
    ImportJobRead,
    ImportRequest,
    PhotoRead,
    SearchQuery,
    SearchResponse,
    SourceCreate,
    SourceRead,
    decode_json_list,
)
from app.search_service import SearchService
from app.serializers import build_face_cluster_read, build_photo_read, build_source_read
from app.watcher import SourceWatchManager

settings = get_settings()
watch_manager = SourceWatchManager(settings)

app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1420", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    settings.ensure_directories()
    create_db_and_tables()
    watch_manager.refresh()


@app.on_event("shutdown")
def on_shutdown() -> None:
    watch_manager.shutdown()


@app.get(f"{settings.api_prefix}/health", response_model=HealthRead)
def health_check() -> HealthRead:
    return HealthRead(
        status="ok",
        app_name=settings.app_name,
        import_root=str(settings.import_root),
        active_watchers=watch_manager.active_watch_count(),
        queued_watch_tasks=watch_manager.queued_task_count(),
        watch_worker_busy=watch_manager.worker_busy(),
    )


@app.get(f"{settings.api_prefix}/sources", response_model=list[SourceRead])
def list_sources(session: Session = Depends(get_session)) -> list[SourceRead]:
    repository = GalleryRepository(session)
    sources = repository.list_sources()
    return [_build_source_read_with_status(source) for source in sources]


@app.post(
    f"{settings.api_prefix}/sources",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_source(
    payload: SourceCreate,
    session: Session = Depends(get_session),
) -> SourceRead:
    repository = GalleryRepository(session)
    source = repository.create_source(
        name=payload.name,
        kind=payload.kind,
        root_path=str(payload.root_path),
        enabled=payload.enabled,
    )
    watch_manager.refresh()
    return _build_source_read_with_status(source)


@app.post(f"{settings.api_prefix}/sources/{{source_id}}/import", response_model=ImportJobRead)
def import_source(
    source_id: int,
    payload: ImportRequest,
    session: Session = Depends(get_session),
) -> ImportJobRead:
    repository = GalleryRepository(session)
    source = repository.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    job = ImportPipeline(session).run(source=source, limit=payload.limit)
    return ImportJobRead.model_validate(job, from_attributes=True)


@app.post(f"{settings.api_prefix}/sources/{{source_id}}/watch/start", response_model=SourceRead)
def start_source_watch(source_id: int, session: Session = Depends(get_session)) -> SourceRead:
    repository = GalleryRepository(session)
    source = repository.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    source = repository.update_source_enabled(source, True)
    watch_manager.refresh()
    return _build_source_read_with_status(source)


@app.post(f"{settings.api_prefix}/sources/{{source_id}}/watch/stop", response_model=SourceRead)
def stop_source_watch(source_id: int, session: Session = Depends(get_session)) -> SourceRead:
    repository = GalleryRepository(session)
    source = repository.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    source = repository.update_source_enabled(source, False)
    watch_manager.refresh()
    return _build_source_read_with_status(source)


@app.get(f"{settings.api_prefix}/import-jobs", response_model=list[ImportJobRead])
def list_import_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[ImportJobRead]:
    repository = GalleryRepository(session)
    jobs = repository.list_import_jobs(limit=limit)
    return [ImportJobRead.model_validate(job, from_attributes=True) for job in jobs]


@app.get(f"{settings.api_prefix}/photos", response_model=list[PhotoRead])
def list_photos(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[PhotoRead]:
    repository = GalleryRepository(session)
    photos = repository.list_recent_photos(limit=limit)
    return [build_photo_read(repository, photo) for photo in photos]


@app.get(f"{settings.api_prefix}/photos/{{photo_id}}", response_model=PhotoRead)
def get_photo(photo_id: int, session: Session = Depends(get_session)) -> PhotoRead:
    repository = GalleryRepository(session)
    photo = repository.get_photo(photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return build_photo_read(repository, photo)


@app.get(f"{settings.api_prefix}/photos/{{photo_id}}/asset")
def get_photo_asset(
    photo_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    repository = GalleryRepository(session)
    photo = repository.get_photo(photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    asset_path = Path(photo.storage_path)
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="Photo asset not found")

    return FileResponse(path=asset_path)


@app.post(f"{settings.api_prefix}/photos/{{photo_id}}/reanalyze", response_model=PhotoRead)
def reanalyze_photo(
    photo_id: int,
    session: Session = Depends(get_session),
) -> PhotoRead:
    repository = GalleryRepository(session)
    photo = repository.get_photo(photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")

    photo_path = Path(photo.storage_path)
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo asset not found")

    analysis = AIAnalyzer(settings).analyze(
        photo_path=photo_path,
        source_kind=photo.source_kind or "local_folder",
    )
    existing_face_labels = decode_json_list(photo.face_clusters)
    face_service = FaceClusteringService(session, settings)
    if existing_face_labels:
        face_result = face_service.resolve_labels([str(item) for item in existing_face_labels])
    else:
        face_result = face_service.analyze_photo(photo_path, example_photo_id=photo.id)

    merged_people = list(dict.fromkeys(analysis.people + face_result.names))
    vector_embedding = VectorEmbeddingService().embed_photo(
        photo_path,
        caption=analysis.caption,
        ocr_text=analysis.ocr_text,
        people=merged_people,
        scene_tags=analysis.scene_tags,
        object_tags=analysis.object_tags,
        phash=photo.phash,
    )

    photo.caption = analysis.caption
    photo.ocr_text = analysis.ocr_text
    photo.people = json.dumps(merged_people, ensure_ascii=False)
    photo.scene_tags = json.dumps(analysis.scene_tags, ensure_ascii=False)
    photo.object_tags = json.dumps(analysis.object_tags, ensure_ascii=False)
    photo.face_clusters = json.dumps(face_result.labels, ensure_ascii=False)
    photo.face_count = max(photo.face_count, face_result.face_count)
    photo.vector_embedding = serialize_vector(vector_embedding)
    photo = repository.save_photo(photo)
    return build_photo_read(repository, photo)


@app.get(f"{settings.api_prefix}/photos/{{photo_id}}/similar", response_model=SearchResponse)
def similar_photos(
    photo_id: int,
    limit: int = Query(default=24, ge=1, le=100),
    session: Session = Depends(get_session),
) -> SearchResponse:
    return SearchService(session).similar_to_photo(photo_id, limit=limit)


@app.post(f"{settings.api_prefix}/search/by-image", response_model=SearchResponse)
async def search_by_image(
    file: UploadFile = File(...),
    limit: int = Form(default=24),
    session: Session = Depends(get_session),
) -> SearchResponse:
    suffix = Path(file.filename or "query.jpg").suffix.lower() or ".jpg"
    target_path = settings.search_upload_root / f"{uuid4().hex}{suffix}"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty image upload")

    target_path.write_bytes(payload)
    try:
        analysis = AIAnalyzer(settings).analyze(target_path, source_kind="local_folder")
        phash = _phash(target_path)
        vector = VectorEmbeddingService().embed_photo(
            target_path,
            caption=analysis.caption,
            ocr_text=analysis.ocr_text,
            people=analysis.people,
            scene_tags=analysis.scene_tags,
            object_tags=analysis.object_tags,
            phash=phash,
        )
        return SearchService(session).search_by_vector(vector, limit=limit)
    finally:
        target_path.unlink(missing_ok=True)


@app.get(f"{settings.api_prefix}/face-clusters", response_model=list[FaceClusterRead])
def list_face_clusters(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[FaceClusterRead]:
    repository = GalleryRepository(session)
    clusters = repository.list_face_clusters(limit=limit)
    stats = _collect_face_cluster_stats(repository)
    return [
        build_face_cluster_read(
            cluster,
            repository,
            photo_count=stats.get(cluster.label, {}).get("photo_count", 0),
            latest_photo_at=stats.get(cluster.label, {}).get("latest_photo_at"),
        )
        for cluster in clusters
    ]


@app.post(f"{settings.api_prefix}/face-clusters/{{cluster_label}}/rename", response_model=FaceClusterRead)
def rename_face_cluster(
    cluster_label: str,
    payload: FaceClusterRenameRequest,
    session: Session = Depends(get_session),
) -> FaceClusterRead:
    repository = GalleryRepository(session)
    face_service = FaceClusteringService(session, settings)
    cluster = face_service.rename_cluster(cluster_label, payload.display_name.strip())
    if cluster is None:
        raise HTTPException(status_code=404, detail="Face cluster not found")

    stats = _collect_face_cluster_stats(repository)
    return build_face_cluster_read(
        cluster,
        repository,
        photo_count=stats.get(cluster.label, {}).get("photo_count", 0),
        latest_photo_at=stats.get(cluster.label, {}).get("latest_photo_at"),
    )


@app.get(f"{settings.api_prefix}/face-clusters/{{cluster_label}}/photos", response_model=SearchResponse)
def list_face_cluster_photos(
    cluster_label: str,
    limit: int = Query(default=48, ge=1, le=100),
    session: Session = Depends(get_session),
) -> SearchResponse:
    repository = GalleryRepository(session)
    cluster = repository.get_face_cluster_by_label(cluster_label)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Face cluster not found")

    return SearchService(session).search(
        SearchQuery(
            text="",
            people=[],
            scene_tags=[],
            object_tags=[],
            source_kinds=[],
            face_cluster_labels=[cluster_label],
            mode="hybrid",
            limit=limit,
        )
    )


@app.post(f"{settings.api_prefix}/search", response_model=SearchResponse)
def search_photos(
    payload: SearchQuery,
    session: Session = Depends(get_session),
) -> SearchResponse:
    return SearchService(session).search(payload)


def _build_source_read_with_status(source) -> SourceRead:
    status_info = watch_manager.get_status(source.id)
    return build_source_read(
        source,
        watching=status_info.watching,
        watch_processing=status_info.processing,
        queued_file_count=status_info.queued_file_count,
        watch_error=status_info.last_error,
        last_watch_event_at=status_info.last_event_at,
        last_watch_completed_at=status_info.last_completed_at,
    )


def _collect_face_cluster_stats(repository: GalleryRepository) -> dict[str, dict[str, object]]:
    stats: dict[str, dict[str, object]] = {}
    for photo in repository.list_searchable_photos(limit=5000):
        latest_time = photo.taken_at or photo.created_at
        for label in decode_json_list(photo.face_clusters):
            item = stats.setdefault(label, {"photo_count": 0, "latest_photo_at": None})
            item["photo_count"] = int(item["photo_count"]) + 1
            previous_latest = item["latest_photo_at"]
            if previous_latest is None or (latest_time and latest_time > previous_latest):
                item["latest_photo_at"] = latest_time
    return stats


def _phash(photo_path: Path) -> str | None:
    try:
        with Image.open(photo_path) as image:
            return str(imagehash.phash(image))
    except Exception:
        return None
