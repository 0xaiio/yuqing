from sqlmodel import Session, desc, select

from app.models import FaceCluster, ImportJob, Photo, Source, utc_now


class GalleryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_sources(self) -> list[Source]:
        statement = select(Source).order_by(Source.created_at.desc())
        return list(self.session.exec(statement))

    def list_enabled_sources(self) -> list[Source]:
        statement = select(Source).where(Source.enabled.is_(True)).order_by(Source.created_at.desc())
        return list(self.session.exec(statement))

    def get_source(self, source_id: int) -> Source | None:
        return self.session.get(Source, source_id)

    def create_source(self, name: str, kind: str, root_path: str, enabled: bool = True) -> Source:
        source = Source(name=name, kind=kind, root_path=root_path, enabled=enabled)
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        return source

    def update_source_enabled(self, source: Source, enabled: bool) -> Source:
        source.enabled = enabled
        self.session.add(source)
        self.session.commit()
        self.session.refresh(source)
        return source

    def list_recent_photos(self, limit: int = 50) -> list[Photo]:
        statement = select(Photo).order_by(desc(Photo.created_at)).limit(limit)
        return list(self.session.exec(statement))

    def list_searchable_photos(self, limit: int = 1000) -> list[Photo]:
        statement = select(Photo).order_by(desc(Photo.created_at)).limit(limit)
        return list(self.session.exec(statement))

    def get_photo(self, photo_id: int) -> Photo | None:
        return self.session.get(Photo, photo_id)

    def find_photo_by_sha256(self, sha256: str) -> Photo | None:
        statement = select(Photo).where(Photo.sha256 == sha256)
        return self.session.exec(statement).first()

    def list_import_jobs(self, limit: int = 50) -> list[ImportJob]:
        statement = select(ImportJob).order_by(desc(ImportJob.created_at)).limit(limit)
        return list(self.session.exec(statement))

    def create_import_job(self, source: Source) -> ImportJob:
        job = ImportJob(source_id=source.id, source_name=source.name, status="running")
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def save_photo(self, photo: Photo) -> Photo:
        self.session.add(photo)
        self.session.commit()
        self.session.refresh(photo)
        return photo

    def finish_import_job(
        self,
        job: ImportJob,
        scanned_count: int,
        imported_count: int,
        duplicate_count: int,
        error_message: str | None = None,
    ) -> ImportJob:
        job.status = "failed" if error_message else "completed"
        job.scanned_count = scanned_count
        job.imported_count = imported_count
        job.duplicate_count = duplicate_count
        job.error_message = error_message
        job.updated_at = utc_now()
        self.session.add(job)
        self.session.commit()
        self.session.refresh(job)
        return job

    def list_face_clusters(self, limit: int = 200) -> list[FaceCluster]:
        statement = select(FaceCluster).order_by(desc(FaceCluster.updated_at)).limit(limit)
        return list(self.session.exec(statement))

    def get_face_cluster_by_label(self, label: str) -> FaceCluster | None:
        statement = select(FaceCluster).where(FaceCluster.label == label)
        return self.session.exec(statement).first()

    def get_face_clusters_by_labels(self, labels: list[str]) -> dict[str, FaceCluster]:
        if not labels:
            return {}
        statement = select(FaceCluster).where(FaceCluster.label.in_(labels))
        return {cluster.label: cluster for cluster in self.session.exec(statement)}

    def create_face_cluster(self, cluster: FaceCluster) -> FaceCluster:
        self.session.add(cluster)
        self.session.commit()
        self.session.refresh(cluster)
        return cluster

    def save_face_cluster(self, cluster: FaceCluster) -> FaceCluster:
        cluster.updated_at = utc_now()
        self.session.add(cluster)
        self.session.commit()
        self.session.refresh(cluster)
        return cluster
