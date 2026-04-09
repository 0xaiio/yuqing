from app.models import PersonProfile, PersonSample, Photo, Source, Video
from app.repository import GalleryRepository
from app.schemas import (
    FaceClusterRead,
    PersonClusterCorrectionCandidateRead,
    PersonRead,
    PersonSampleRead,
    PhotoRead,
    SourceRead,
    VideoRead,
    VideoPersonMomentRead,
    decode_json_records,
    decode_json_list,
)


def build_photo_read(repository: GalleryRepository, photo: Photo) -> PhotoRead:
    base_people = decode_json_list(photo.people)
    scene_tags = decode_json_list(photo.scene_tags)
    object_tags = decode_json_list(photo.object_tags)
    face_clusters = decode_json_list(photo.face_clusters)
    cluster_map = repository.get_face_clusters_by_labels(face_clusters)
    person_map = repository.get_person_profiles_by_ids(
        [cluster.person_profile_id for cluster in cluster_map.values() if cluster.person_profile_id]
    )
    cluster_display_names = [
        cluster.display_name
        for label in face_clusters
        if (cluster := cluster_map.get(label)) and cluster.display_name
    ]
    recognized_person_names = [
        person_map[cluster.person_profile_id].name
        for label in face_clusters
        if (cluster := cluster_map.get(label))
        and cluster.person_profile_id
        and person_map.get(cluster.person_profile_id)
    ]
    face_names = list(dict.fromkeys(cluster_display_names + recognized_person_names))
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


def build_video_read(repository: GalleryRepository, video: Video) -> VideoRead:
    base_people = decode_json_list(video.people)
    scene_tags = decode_json_list(video.scene_tags)
    object_tags = decode_json_list(video.object_tags)
    face_clusters = decode_json_list(video.face_clusters)
    cluster_map = repository.get_face_clusters_by_labels(face_clusters)
    person_map = repository.get_person_profiles_by_ids(
        [cluster.person_profile_id for cluster in cluster_map.values() if cluster.person_profile_id]
    )
    cluster_display_names = [
        cluster.display_name
        for label in face_clusters
        if (cluster := cluster_map.get(label)) and cluster.display_name
    ]
    recognized_person_names = [
        person_map[cluster.person_profile_id].name
        for label in face_clusters
        if (cluster := cluster_map.get(label))
        and cluster.person_profile_id
        and person_map.get(cluster.person_profile_id)
    ]
    face_names = list(dict.fromkeys(cluster_display_names + recognized_person_names))
    merged_people = list(dict.fromkeys(base_people + face_names))
    person_moments = [
        VideoPersonMomentRead(
            person_name=str(item.get("person_name", "")),
            timestamp_seconds=float(item.get("timestamp_seconds", 0.0)),
            score=float(item.get("score", 0.0)),
            bbox=[float(value) for value in item.get("bbox", []) if isinstance(value, (int, float))],
            cluster_label=str(item.get("cluster_label")) if item.get("cluster_label") else None,
        )
        for item in decode_json_records(video.person_moments)
        if item.get("person_name")
    ]

    return VideoRead(
        id=video.id or 0,
        source_id=video.source_id,
        source_kind=video.source_kind,
        source_name=video.source_name,
        original_path=video.original_path,
        storage_path=video.storage_path,
        thumbnail_path=video.thumbnail_path,
        thumbnail_asset_url=(f"/api/v1/videos/{video.id}/thumbnail" if video.id and video.thumbnail_path else None),
        sha256=video.sha256,
        caption=video.caption,
        ocr_text=video.ocr_text,
        people=merged_people,
        scene_tags=scene_tags,
        object_tags=object_tags,
        face_clusters=face_clusters,
        face_names=face_names,
        person_moments=person_moments,
        face_count=video.face_count,
        vector_ready=bool(video.vector_embedding),
        duration_seconds=video.duration_seconds,
        frame_width=video.frame_width,
        frame_height=video.frame_height,
        fps=video.fps,
        sampled_frame_count=video.sampled_frame_count,
        taken_at=video.taken_at,
        created_at=video.created_at,
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


def build_person_read(
    person: PersonProfile,
    repository: GalleryRepository,
    *,
    linked_cluster_count: int = 0,
    linked_photo_count: int = 0,
) -> PersonRead:
    example_sample = repository.get_person_sample(person.example_sample_id) if person.example_sample_id else None
    return PersonRead(
        id=person.id or 0,
        name=person.name,
        example_sample_id=person.example_sample_id,
        example_sample_asset_url=(
            f"/api/v1/person-samples/{example_sample.id}/asset"
            if example_sample and example_sample.id
            else None
        ),
        sample_count=person.sample_count,
        linked_cluster_count=linked_cluster_count,
        linked_photo_count=linked_photo_count,
        created_at=person.created_at,
        updated_at=person.updated_at,
    )


def build_person_sample_read(sample: PersonSample) -> PersonSampleRead:
    return PersonSampleRead(
        id=sample.id or 0,
        person_id=sample.person_id,
        original_filename=sample.original_filename,
        asset_url=f"/api/v1/person-samples/{sample.id}/asset" if sample.id else None,
        created_at=sample.created_at,
    )


def build_person_cluster_correction_candidate(
    payload: dict[str, object],
) -> PersonClusterCorrectionCandidateRead:
    example_photo_id = payload.get("example_photo_id")
    return PersonClusterCorrectionCandidateRead(
        label=str(payload["label"]),
        display_name=str(payload["display_name"]) if payload.get("display_name") else None,
        example_photo_id=int(example_photo_id) if example_photo_id else None,
        example_photo_asset_url=(
            f"/api/v1/photos/{int(example_photo_id)}/asset" if example_photo_id else None
        ),
        photo_count=int(payload.get("photo_count", 0)),
        score=float(payload.get("score", 0.0)),
        competitor_score=float(payload.get("competitor_score", 0.0)),
        margin=float(payload.get("margin", 0.0)),
        current_person_id=(
            int(payload["current_person_id"]) if payload.get("current_person_id") is not None else None
        ),
        current_person_name=(
            str(payload["current_person_name"]) if payload.get("current_person_name") else None
        ),
        linked_to_selected_person=bool(payload.get("linked_to_selected_person", False)),
        recommended=bool(payload.get("recommended", False)),
    )
