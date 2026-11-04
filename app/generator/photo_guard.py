"""Validate and orient photos before adding them to a Word document."""
import hashlib
import io
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError


MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 50_000_000
MIN_SIDE = 300
SUPPORTED = {"JPEG", "PNG", "BMP", "GIF", "TIFF", "WEBP"}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_photos(paths: list[str]) -> None:
    seen = set()
    for name in paths:
        path = Path(name)
        try:
            if not path.is_file():
                raise ValueError(f"照片不存在：{path.name}")
            if path.stat().st_size > MAX_BYTES:
                raise ValueError(f"照片“{path.name}”超过25MB，请压缩后重试。")
            fingerprint = _digest(path)
            if fingerprint in seen:
                raise ValueError(f"照片“{path.name}”与前面选择的照片重复，请换一张。")
            seen.add(fingerprint)
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    if image.format not in SUPPORTED:
                        raise ValueError(f"不支持的照片格式：{path.name}")
                    width, height = image.size
                    if width * height > MAX_PIXELS:
                        raise ValueError(f"照片“{path.name}”像素过大，请先缩小。")
                    if min(width, height) < MIN_SIDE:
                        raise ValueError(f"照片“{path.name}”分辨率过低，短边至少需要300像素。")
                    image.load()
        except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError(f"照片“{path.name}”无法读取或已损坏，请重新选择：{exc}") from exc


def prepare_photos(paths: list[str]) -> list[io.BytesIO]:
    """Return independent upright image streams, preserving aspect ratio."""
    prepared = []
    for name in paths:
        with Image.open(name) as original:
            image = ImageOps.exif_transpose(original)
            image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            stream = io.BytesIO()
            if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
                image.save(stream, format="PNG")
            else:
                image.convert("RGB").save(stream, format="JPEG", quality=90)
            stream.seek(0)
            prepared.append(stream)
    return prepared
