from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "Cross Source AI Photo Manager"
    api_prefix: str = "/api/v1"
    database_url: str = f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"
    import_root: Path = DATA_DIR / "imports"
    search_upload_root: Path = DATA_DIR / "search-uploads"
    person_library_root: Path = DATA_DIR / "person-library"
    face_model_root: Path = DATA_DIR / "face-models"
    face_runtime_config_path: Path = DATA_DIR / "face-runtime-config.json"
    video_frame_root: Path = DATA_DIR / "video-frames"
    wechat_default_path: Path | None = None
    qq_default_path: Path | None = None
    ai_enable_ocr: bool = True
    ai_ocr_engine: str = "rapidocr"
    ai_enable_vision: bool = False
    ai_vision_base_url: str = "https://api.openai.com/v1"
    ai_vision_api_key: str | None = None
    ai_vision_model: str | None = None
    ai_vision_timeout_seconds: int = 90
    watcher_enabled: bool = True
    watcher_recursive: bool = True
    watcher_debounce_seconds: int = 3
    face_detection_pack_name: str = "buffalo_l"
    face_detection_model_filename: str = "det_10g.onnx"
    face_detection_input_size: int = 1024
    face_detection_confidence_threshold: float = 0.35
    face_detection_nms_threshold: float = 0.4
    face_detection_max_faces: int = 12
    face_recognition_repo_id: str = "minchul/cvlface_adaface_ir50_webface4m"
    face_recognition_model_filename: str = "model.pt"
    face_recognition_device: str = "cpu"
    face_recognition_batch_size: int = 8
    face_cluster_similarity_threshold: float = 0.5
    person_recognition_similarity_threshold: float = 0.52
    face_tuning_preview_cluster_limit: int = 240
    video_frame_sample_interval_seconds: int = 1
    video_max_sampled_frames: int = 24
    video_face_retry_interval_seconds: float = 0.5
    video_face_retry_max_frames: int = 48
    video_person_vote_min_hits: int = 2
    video_person_moment_max_per_person: int = 5
    video_person_moment_min_gap_seconds: float = 2.0
    video_thumbnail_offset_ratio: float = 0.15
    video_embedding_model_id: str = "google/siglip2-base-patch16-224"
    video_embedding_device: str = "cpu"
    video_scene_candidate_limit: int = 5

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_directories(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.import_root.mkdir(parents=True, exist_ok=True)
        self.search_upload_root.mkdir(parents=True, exist_ok=True)
        self.person_library_root.mkdir(parents=True, exist_ok=True)
        self.face_model_root.mkdir(parents=True, exist_ok=True)
        self.video_frame_root.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
