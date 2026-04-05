from pathlib import Path

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
    ".heic",
}

SUPPORTED_VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".mkv",
    ".webm",
}


class BaseConnector:
    IMAGE_SUFFIXES = SUPPORTED_IMAGE_EXTENSIONS
    VIDEO_SUFFIXES = SUPPORTED_VIDEO_EXTENSIONS

    def discover(self, root_path: Path, limit: int = 50) -> list[Path]:
        raise NotImplementedError

    @staticmethod
    def is_supported_image(path: Path) -> bool:
        return path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS

    @staticmethod
    def is_supported_video(path: Path) -> bool:
        return path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS

    @classmethod
    def is_supported_media(cls, path: Path) -> bool:
        return cls.is_supported_image(path) or cls.is_supported_video(path)


class LocalFolderConnector(BaseConnector):
    def discover(self, root_path: Path, limit: int = 50) -> list[Path]:
        if not root_path.exists():
            raise FileNotFoundError(f"Folder does not exist: {root_path}")

        image_paths = [
            path
            for path in root_path.rglob("*")
            if path.is_file() and self.is_supported_media(path)
        ]
        image_paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return image_paths[:limit]


class WeChatFolderConnector(LocalFolderConnector):
    """WeChat v1 connector based on user-authorized local folders."""


class QQFolderConnector(LocalFolderConnector):
    """QQ v1 connector based on user-authorized local folders."""


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, BaseConnector] = {
            "local_folder": LocalFolderConnector(),
            "wechat_folder": WeChatFolderConnector(),
            "qq_folder": QQFolderConnector(),
        }

    def get(self, kind: str) -> BaseConnector:
        connector = self._connectors.get(kind)
        if connector is None:
            raise ValueError(f"Unsupported source kind: {kind}")
        return connector
