import io
import warnings
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image as PILImage
from PIL import ImageOps
from pillow_heif import register_heif_opener
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Image, User
from ..permissions import can_view_image
from ..schemas import ImageOut
from ..security import current_user

register_heif_opener()
PILImage.MAX_IMAGE_PIXELS = 60_000_000
FORMATS = ("JPEG", "PNG", "WEBP", "HEIF")

router = APIRouter(prefix="/api/images", tags=["images"])


def clean_image(data: bytes) -> bytes:
    """Re-encode as a resized WebP, which also drops location and other metadata."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", PILImage.DecompressionBombWarning)
            with PILImage.open(io.BytesIO(data), formats=FORMATS) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
        image.thumbnail((1600, 1600))
        clean = PILImage.new("RGB", image.size)
        clean.paste(image)
        out = io.BytesIO()
        clean.save(out, "WEBP", quality=82)
        return out.getvalue()
    except Exception:
        raise HTTPException(422, "That file is not a supported image") from None


@router.post("", status_code=201)
def upload(
    file: UploadFile, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> ImageOut:
    settings = get_settings()
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "Image is too large")
    cleaned = clean_image(data)
    image = Image(id=uuid4(), owner_id=user.id)
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    (settings.media_dir / f"{image.id}.webp").write_bytes(cleaned)
    db.add(image)
    db.commit()
    return ImageOut.model_validate(image)


@router.get("/{image_id}", include_in_schema=False)
def show(image_id: UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    path = get_settings().media_dir / f"{image_id}.webp"
    if not can_view_image(db, user, image_id) or not path.is_file():
        raise HTTPException(404, "Image not found")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
