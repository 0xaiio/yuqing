from app.models import Photo, Source
from app.repository import GalleryRepository
from app.schemas import FaceClusterRead, PhotoRead, SourceRead, decode_json_list


def build_photo_read(repository: GalleryRepository, photo: Photo) -> PhotoRead:
    base_people = decode_json_list(photo.people)
    scene_tags = decode_json_list(photo.scene_tags)
    object_tags = decode_json_list(photo.object_tags)
    face_clusters = decode_json_list(photo.face_clusters)
    cluster_map = repository.get_face_clusters_by_labels(face_clusters)
    face_names = [
        cluster.display_name
        for label in face_clusters
        if (cluster := cluster_map.get(label)) and cluster.display_name
    ]
    merged_people = list(dict.fromkeys(base_people + face_names))

    return PhotoRead(
        id=photo.id or 0,
        source_id=photo.source_id,
        source_kind=photo.source_kind,
        source_name=photo.source_name,
        original_path=photo.original_path,
        storage_path=photo.storage_path,
        sha256=photo.sha256,
        phash=photo.phash,
        caption=photo.caption,
        ocr_text=photo.ocr_text,
        people=merged_people,
        scene_tags=scene_tags,
        object_tags=object_tags,
        face_clusters=face_clusters,
        face_names=face_names,
        face_count=photo.face_count,
        vector_ready=bool(photo.vector_embedding),
        taken_at=photo.taken_at,
        created_at=photo.created_at,
    )


def build_source_read(
    source: Source,
    *,
    watching: bool,
    watch_processing: bool,
    queued_file_count: int,
    watch_error: str | None,
    last_watch_event_at,
    last_watch_completed_at,
) -> SourceRead:
    return SourceRead(
        id=source.id or 0,
        name=source.name,
        kind=source.kind,
        root_path=source.root_path,
        enabled=source.enabled,
        watching=watching,
        watch_processing=watch_processing,
        queued_file_count=queued_file_count,
        watch_error=watch_error,
        last_watch_event_at=last_watch_event_at,
        last_watch_completed_at=last_watch_completed_at,
        created_at=source.created_at,
    )


def build_face_cluster_read(
    cluster,
    repository: GalleryRepository,
    *,
    photo_count: int = 0,
    latest_photo_at=None,
) -> FaceClusterRead:
    example_photo = repository.get_photo(cluster.example_photo_id) if cluster.example_photo_id else None
    return FaceClusterRead(
        id=cluster.id or 0,
        label=cluster.label,
        display_name=cluster.display_name,
        example_photo_id=cluster.example_photo_id,
        example_photo_asset_url=(
            f"/api/v1/photos/{example_photo.id}/asset" if example_photo and example_photo.id else None
        ),
        photo_count=photo_count,
        named=bool(cluster.display_name),
        latest_photo_at=latest_photo_at,
        created_at=cluster.created_at,
        updated_at=cluster.updated_at,
    )
