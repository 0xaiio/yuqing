import json
from pathlib import Path
from uuid import uuid4

import imagehash
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from sqlmodel import Session

from app.ai import AIAnalyzer
from app.config import get_settings
from app.database import create_db_and_tables, engine, get_session
from app.embeddings import VectorEmbeddingService, serialize_vector
from app.face_clustering import FaceClusteringService
from app.face_tuning import FaceRuntimeConfigService, FaceTuningService
from app.import_pipeline import ImportPipeline
from app.media_cleanup import MediaCleanupService
from app.media_library import MediaLibraryService
from app.people import PersonLibraryService
from app.repository import GalleryRepository
from app.schemas import (
    CleanupResponse,
    FaceClusterRead,
    FaceClusterRenameRequest,
    FaceThresholdUpdateRequest,
    FaceTuningBundleRead,
    HealthRead,
    ImportJobRead,
    ImportRequest,
    PersonCreate,
    PersonClusterCorrectionCandidateRead,
    PersonClusterCorrectionRequest,
    PersonClusterCorrectionResult,
    PersonRead,
    PersonRenameRequest,
    PersonSampleRead,
    PhotoRead,
    SearchQuery,
    SearchResponse,
    SourceCreate,
    SourceRead,
    VideoRead,
    VideoSearchResponse,
    decode_json_list,
)
from app.search_service import SearchService
from app.video_processing import VideoProcessingService
from app.video_search_service import VideoSearchService
from app.serializers import (
    build_face_cluster_read,
    build_person_cluster_correction_candidate,
    build_person_read,
    build_person_sample_read,
    build_photo_read,
    build_source_read,
    build_video_read,
)
from app.watcher import SourceWatchManager

settings = get_settings()
watch_manager = SourceWatchManager(settings)

app = FastAPI(
    title=settings.app_name,
    version="0.5.0",
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
    FaceRuntimeConfigService(settings).apply_persisted_thresholds()
    create_db_and_tables()
    with Session(engine) as session:
        FaceClusteringService(session, settings).refresh_face_index_if_needed()
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


@app.delete(f"{settings.api_prefix}/photos/{{photo_id}}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(
    photo_id: int,
    delete_source_file: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> Response:
    try:
        deleted = MediaLibraryService(session, settings).delete_photo(
            photo_id,
            delete_source_file=delete_source_file,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Photo not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@app.get(f"{settings.api_prefix}/videos", response_model=list[VideoRead])
def list_videos(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[VideoRead]:
    repository = GalleryRepository(session)
    videos = repository.list_recent_videos(limit=limit)
    return [build_video_read(repository, video) for video in videos]


@app.get(f"{settings.api_prefix}/cleanup/candidates", response_model=CleanupResponse)
def list_cleanup_candidates(
    category: str = Query(...),
    limit: int = Query(default=80, ge=1, le=200),
    session: Session = Depends(get_session),
) -> CleanupResponse:
    try:
        return MediaCleanupService(session).list_candidates(category=category, limit=limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get(f"{settings.api_prefix}/videos/{{video_id}}", response_model=VideoRead)
def get_video(video_id: int, session: Session = Depends(get_session)) -> VideoRead:
    repository = GalleryRepository(session)
    video = repository.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return build_video_read(repository, video)


@app.delete(f"{settings.api_prefix}/videos/{{video_id}}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(
    video_id: int,
    delete_source_file: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> Response:
    try:
        deleted = MediaLibraryService(session, settings).delete_video(
            video_id,
            delete_source_file=delete_source_file,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(f"{settings.api_prefix}/videos/{{video_id}}/asset")
def get_video_asset(video_id: int, session: Session = Depends(get_session)) -> FileResponse:
    repository = GalleryRepository(session)
    video = repository.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    asset_path = Path(video.storage_path)
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="Video asset not found")
    return FileResponse(path=asset_path)


@app.get(f"{settings.api_prefix}/videos/{{video_id}}/thumbnail")
def get_video_thumbnail(video_id: int, session: Session = Depends(get_session)) -> FileResponse:
    repository = GalleryRepository(session)
    video = repository.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if not video.thumbnail_path:
        raise HTTPException(status_code=404, detail="Video thumbnail not found")

    asset_path = Path(video.thumbnail_path)
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="Video thumbnail not found")
    return FileResponse(path=asset_path)


@app.post(f"{settings.api_prefix}/videos/{{video_id}}/reanalyze", response_model=VideoRead)
def reanalyze_video(
    video_id: int,
    session: Session = Depends(get_session),
) -> VideoRead:
    repository = GalleryRepository(session)
    video = repository.get_video(video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    video_path = Path(video.storage_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video asset not found")

    analysis = VideoProcessingService(session, settings).analyze_video(
        video_path,
        asset_key=video.sha256,
        source_kind=video.source_kind or "local_folder",
    )

    video.thumbnail_path = str(analysis.thumbnail_path) if analysis.thumbnail_path else None
    video.caption = analysis.caption
    video.ocr_text = analysis.ocr_text
    video.people = json.dumps(analysis.people, ensure_ascii=False)
    video.scene_tags = json.dumps(analysis.scene_tags, ensure_ascii=False)
    video.object_tags = json.dumps(analysis.object_tags, ensure_ascii=False)
    video.face_clusters = json.dumps(analysis.face_clusters, ensure_ascii=False)
    video.face_count = analysis.face_count
    video.vector_embedding = serialize_vector(analysis.vector_embedding)
    video.duration_seconds = analysis.metadata.duration_seconds
    video.frame_width = analysis.metadata.frame_width
    video.frame_height = analysis.metadata.frame_height
    video.fps = analysis.metadata.fps
    video.sampled_frame_count = analysis.sampled_frame_count
    video = repository.save_video(video)
    return build_video_read(repository, video)


@app.get(f"{settings.api_prefix}/videos/{{video_id}}/similar", response_model=VideoSearchResponse)
def similar_videos(
    video_id: int,
    limit: int = Query(default=24, ge=1, le=100),
    session: Session = Depends(get_session),
) -> VideoSearchResponse:
    return VideoSearchService(session).similar_to_video(video_id, limit=limit)


@app.get(f"{settings.api_prefix}/person-samples/{{sample_id}}/asset")
def get_person_sample_asset(
    sample_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    repository = GalleryRepository(session)
    sample = repository.get_person_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Person sample not found")

    asset_path = Path(sample.storage_path)
    if not asset_path.exists():
        raise HTTPException(status_code=404, detail="Person sample asset not found")

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


@app.post(f"{settings.api_prefix}/search/by-person-image", response_model=SearchResponse)
async def search_by_person_image(
    file: UploadFile = File(...),
    limit: int = Form(default=24),
    session: Session = Depends(get_session),
) -> SearchResponse:
    suffix = Path(file.filename or "person-query.jpg").suffix.lower() or ".jpg"
    target_path = settings.search_upload_root / f"person-query-{uuid4().hex}{suffix}"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty image upload")

    target_path.write_bytes(payload)
    try:
        embeddings = FaceClusteringService(session, settings).extract_face_embeddings(target_path)
        if not embeddings:
            raise HTTPException(status_code=400, detail="No face detected in the uploaded query image")
        return SearchService(session).search_by_person_embedding(embeddings[0], limit=limit)
    finally:
        target_path.unlink(missing_ok=True)


@app.post(f"{settings.api_prefix}/search/videos/by-video", response_model=VideoSearchResponse)
async def search_videos_by_video(
    file: UploadFile = File(...),
    limit: int = Form(default=24),
    session: Session = Depends(get_session),
) -> VideoSearchResponse:
    suffix = Path(file.filename or "query-video.mp4").suffix.lower() or ".mp4"
    target_path = settings.search_upload_root / f"video-query-{uuid4().hex}{suffix}"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty video upload")

    target_path.write_bytes(payload)
    try:
        query_vector = VideoProcessingService(session, settings).build_query_video_embedding(target_path)
        return VideoSearchService(session).search_by_vector(query_vector, limit=limit)
    finally:
        target_path.unlink(missing_ok=True)


@app.post(f"{settings.api_prefix}/search/videos/by-person-image", response_model=VideoSearchResponse)
async def search_videos_by_person_image(
    file: UploadFile = File(...),
    limit: int = Form(default=24),
    session: Session = Depends(get_session),
) -> VideoSearchResponse:
    suffix = Path(file.filename or "person-video-query.jpg").suffix.lower() or ".jpg"
    target_path = settings.search_upload_root / f"person-video-query-{uuid4().hex}{suffix}"
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty image upload")

    target_path.write_bytes(payload)
    try:
        embeddings = FaceClusteringService(session, settings).extract_face_embeddings(target_path)
        if not embeddings:
            raise HTTPException(status_code=400, detail="No face detected in the uploaded query image")
        return VideoSearchService(session).search_by_person_embedding(embeddings[0], limit=limit)
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


@app.get(f"{settings.api_prefix}/face-clusters/{{cluster_label}}/videos", response_model=VideoSearchResponse)
def list_face_cluster_videos(
    cluster_label: str,
    limit: int = Query(default=48, ge=1, le=100),
    session: Session = Depends(get_session),
) -> VideoSearchResponse:
    repository = GalleryRepository(session)
    cluster = repository.get_face_cluster_by_label(cluster_label)
    if cluster is None:
        raise HTTPException(status_code=404, detail="Face cluster not found")

    return MediaLibraryService(session, settings).list_videos_by_face_clusters([cluster_label], limit=limit)


@app.get(f"{settings.api_prefix}/people", response_model=list[PersonRead])
def list_people(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[PersonRead]:
    repository = GalleryRepository(session)
    stats = _collect_person_stats(repository)
    return [
        build_person_read(
            person,
            repository,
            linked_cluster_count=stats.get(person.id or 0, {}).get("linked_cluster_count", 0),
            linked_photo_count=stats.get(person.id or 0, {}).get("linked_photo_count", 0),
        )
        for person in repository.list_person_profiles(limit=limit)
    ]


@app.post(f"{settings.api_prefix}/people", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
def create_person(
    payload: PersonCreate,
    session: Session = Depends(get_session),
) -> PersonRead:
    repository = GalleryRepository(session)
    person = PersonLibraryService(session, settings).create_person(payload.name.strip())
    stats = _collect_person_stats(repository)
    return build_person_read(
        person,
        repository,
        linked_cluster_count=stats.get(person.id or 0, {}).get("linked_cluster_count", 0),
        linked_photo_count=stats.get(person.id or 0, {}).get("linked_photo_count", 0),
    )


@app.post(f"{settings.api_prefix}/people/{{person_id}}/rename", response_model=PersonRead)
def rename_person(
    person_id: int,
    payload: PersonRenameRequest,
    session: Session = Depends(get_session),
) -> PersonRead:
    repository = GalleryRepository(session)
    try:
        person = PersonLibraryService(session, settings).rename_person(person_id, payload.name.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    stats = _collect_person_stats(repository)
    return build_person_read(
        person,
        repository,
        linked_cluster_count=stats.get(person.id or 0, {}).get("linked_cluster_count", 0),
        linked_photo_count=stats.get(person.id or 0, {}).get("linked_photo_count", 0),
    )


@app.get(f"{settings.api_prefix}/people/{{person_id}}/samples", response_model=list[PersonSampleRead])
def list_person_samples(
    person_id: int,
    session: Session = Depends(get_session),
) -> list[PersonSampleRead]:
    repository = GalleryRepository(session)
    person = repository.get_person_profile(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    return [build_person_sample_read(sample) for sample in repository.list_person_samples(person_id)]


@app.post(f"{settings.api_prefix}/people/{{person_id}}/samples", response_model=PersonRead)
async def add_person_sample(
    person_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> PersonRead:
    repository = GalleryRepository(session)
    try:
        person = PersonLibraryService(session, settings).add_sample(
            person_id,
            file_bytes=await file.read(),
            filename=file.filename or "sample.jpg",
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc

    stats = _collect_person_stats(repository)
    return build_person_read(
        person,
        repository,
        linked_cluster_count=stats.get(person.id or 0, {}).get("linked_cluster_count", 0),
        linked_photo_count=stats.get(person.id or 0, {}).get("linked_photo_count", 0),
    )


@app.delete(f"{settings.api_prefix}/people/{{person_id}}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: int,
    session: Session = Depends(get_session),
) -> Response:
    deleted = PersonLibraryService(session, settings).delete_person(person_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Person not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete(f"{settings.api_prefix}/people/{{person_id}}/samples/{{sample_id}}", response_model=PersonRead)
def delete_person_sample(
    person_id: int,
    sample_id: int,
    session: Session = Depends(get_session),
) -> PersonRead:
    repository = GalleryRepository(session)
    try:
        person = PersonLibraryService(session, settings).delete_sample(person_id, sample_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc

    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    stats = _collect_person_stats(repository)
    return build_person_read(
        person,
        repository,
        linked_cluster_count=stats.get(person.id or 0, {}).get("linked_cluster_count", 0),
        linked_photo_count=stats.get(person.id or 0, {}).get("linked_photo_count", 0),
    )


@app.get(f"{settings.api_prefix}/people/{{person_id}}/photos", response_model=SearchResponse)
def list_person_photos(
    person_id: int,
    limit: int = Query(default=48, ge=1, le=100),
    session: Session = Depends(get_session),
) -> SearchResponse:
    repository = GalleryRepository(session)
    person = repository.get_person_profile(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    person_clusters = repository.list_face_clusters_by_person(person_id, limit=5000)
    return SearchService(session).search(
        SearchQuery(
            text="",
            people=[person.name],
            scene_tags=[],
            object_tags=[],
            source_kinds=[],
            face_cluster_labels=[cluster.label for cluster in person_clusters],
            mode="hybrid",
            limit=limit,
        )
    )


@app.get(f"{settings.api_prefix}/people/{{person_id}}/videos", response_model=VideoSearchResponse)
def list_person_videos(
    person_id: int,
    limit: int = Query(default=48, ge=1, le=100),
    session: Session = Depends(get_session),
) -> VideoSearchResponse:
    repository = GalleryRepository(session)
    person = repository.get_person_profile(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    return MediaLibraryService(session, settings).list_videos_by_person(person_id, limit=limit)


@app.get(
    f"{settings.api_prefix}/people/{{person_id}}/correction-candidates",
    response_model=list[PersonClusterCorrectionCandidateRead],
)
def list_person_correction_candidates(
    person_id: int,
    limit: int = Query(default=80, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[PersonClusterCorrectionCandidateRead]:
    try:
        candidates = PersonLibraryService(session, settings).list_cluster_correction_candidates(
            person_id,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [build_person_cluster_correction_candidate(item) for item in candidates]


@app.post(
    f"{settings.api_prefix}/people/{{person_id}}/cluster-corrections",
    response_model=PersonClusterCorrectionResult,
)
def apply_person_cluster_correction(
    person_id: int,
    payload: PersonClusterCorrectionRequest,
    session: Session = Depends(get_session),
) -> PersonClusterCorrectionResult:
    repository = GalleryRepository(session)
    service = PersonLibraryService(session, settings)
    try:
        person, updated_labels = service.apply_cluster_correction(
            person_id,
            cluster_labels=payload.cluster_labels,
            action=payload.action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")

    stats = _collect_person_stats(repository)
    return PersonClusterCorrectionResult(
        person=build_person_read(
            person,
            repository,
            linked_cluster_count=stats.get(person.id or 0, {}).get("linked_cluster_count", 0),
            linked_photo_count=stats.get(person.id or 0, {}).get("linked_photo_count", 0),
        ),
        updated_cluster_count=len(updated_labels),
        updated_labels=updated_labels,
    )


@app.get(f"{settings.api_prefix}/face-tuning", response_model=FaceTuningBundleRead)
def get_face_tuning(
    session: Session = Depends(get_session),
) -> FaceTuningBundleRead:
    bundle = FaceTuningService(session, settings).build_bundle()
    return FaceTuningBundleRead.model_validate(bundle)


@app.post(f"{settings.api_prefix}/face-tuning/preview", response_model=FaceTuningBundleRead)
def preview_face_tuning(
    payload: FaceThresholdUpdateRequest,
    session: Session = Depends(get_session),
) -> FaceTuningBundleRead:
    overrides = payload.model_dump(exclude={"rebuild_index"})
    bundle = FaceTuningService(session, settings).build_bundle(overrides)
    return FaceTuningBundleRead.model_validate(bundle)


@app.post(f"{settings.api_prefix}/face-tuning/settings", response_model=FaceTuningBundleRead)
def update_face_tuning(
    payload: FaceThresholdUpdateRequest,
    session: Session = Depends(get_session),
) -> FaceTuningBundleRead:
    updates = payload.model_dump(exclude={"rebuild_index"})
    bundle = FaceTuningService(session, settings).update_thresholds(
        updates,
        rebuild_index=payload.rebuild_index,
    )
    return FaceTuningBundleRead.model_validate(bundle)


@app.post(f"{settings.api_prefix}/search", response_model=SearchResponse)
def search_photos(
    payload: SearchQuery,
    session: Session = Depends(get_session),
) -> SearchResponse:
    return SearchService(session).search(payload)


@app.post(f"{settings.api_prefix}/search/videos", response_model=VideoSearchResponse)
def search_videos(
    payload: SearchQuery,
    session: Session = Depends(get_session),
) -> VideoSearchResponse:
    return VideoSearchService(session).search(payload)


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


def _collect_person_stats(repository: GalleryRepository) -> dict[int, dict[str, int]]:
    stats: dict[int, dict[str, int]] = {}
    cluster_owner_by_label: dict[str, int] = {}

    for cluster in repository.list_face_clusters(limit=5000):
        if not cluster.person_profile_id:
            continue
        person_id = cluster.person_profile_id
        cluster_owner_by_label[cluster.label] = person_id
        item = stats.setdefault(person_id, {"linked_cluster_count": 0, "linked_photo_count": 0})
        item["linked_cluster_count"] += 1

    for photo in repository.list_searchable_photos(limit=5000):
        linked_people = {
            cluster_owner_by_label[label]
            for label in decode_json_list(photo.face_clusters)
            if label in cluster_owner_by_label
        }
        for person_id in linked_people:
            item = stats.setdefault(person_id, {"linked_cluster_count": 0, "linked_photo_count": 0})
            item["linked_photo_count"] += 1

    return stats


def _phash(photo_path: Path) -> str | None:
    try:
        with Image.open(photo_path) as image:
            return str(imagehash.phash(image))
    except Exception:
        return None
