import logging
import threading
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..fetch import check_url, fetch
from ..importer import Budget, import_data
from ..models import ImportJob, User, now
from ..schemas import ImportOut, ImportUrlIn
from ..security import current_user
from .images import clean_image, save_image

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/imports", tags=["imports"])

# Imports are slow, so a few at a time leaves room for everyone else's requests.
slots = threading.BoundedSemaphore(4)
# More than one import can cost: both models with the longest source and answer.
RESERVED = Decimal("0.50")


def import_slot():
    if not slots.acquire(blocking=False):
        raise HTTPException(503, "Several recipes are being imported. Try again in a minute.")
    try:
        yield
    finally:
        slots.release()


def start(db: Session, user: User) -> Budget:
    settings = get_settings()

    def lock():
        # Limits are checked one at a time, so simultaneous imports cannot pass them.
        db.execute(text("select pg_advisory_xact_lock(hashtext('import_jobs'))"))

    def check_daily(limit: int, *conditions):
        since = now() - timedelta(days=1)
        query = select(func.count()).select_from(ImportJob)
        query = query.where(ImportJob.user_id == user.id, ImportJob.created_at > since)
        if db.scalar(query.where(*conditions)) >= limit:
            raise HTTPException(429, "You have reached the daily import limit. Try again later.")

    lock()
    check_daily(settings.import_daily_limit)
    job = ImportJob(user_id=user.id)
    db.add(job)
    # Committing also gives back the database connection while the slow work runs.
    db.commit()

    def reserve():
        lock()
        check_daily(settings.import_daily_model_limit, ImportJob.used_model)
        month = now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        spent = db.scalar(select(func.sum(ImportJob.cost)).where(ImportJob.created_at >= month))
        if (spent or 0) + RESERVED > Decimal(str(settings.import_monthly_dollars)):
            raise HTTPException(429, "The site has reached this month's import budget.")
        job.used_model = True
        job.cost = RESERVED
        db.commit()

    def settle(cost: Decimal):
        job.cost = cost
        db.commit()

    return Budget(reserve, settle)


@router.post("/url")
def import_url(
    body: ImportUrlIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    _: None = Depends(import_slot),
) -> ImportOut:
    url = check_url(body.url)
    budget = start(db, user)
    page = fetch(url, max_bytes=10 * 1024 * 1024, seconds=15)
    result = import_data(page.data, budget, url=page.url, encoding=page.encoding)
    if result.image_url:
        # The picture is a bonus: a recipe without it is still worth having.
        try:
            picture = fetch(result.image_url, max_bytes=get_settings().max_upload_bytes, seconds=10)
            result.content.image_id = save_image(db, user, clean_image(picture.data)).id
        except HTTPException as error:
            log.info("No picture imported: %s", error.detail)
    return ImportOut(content=result.content, notice=result.notice)


@router.post("/file")
def import_file(
    file: UploadFile,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    _: None = Depends(import_slot),
) -> ImportOut:
    limit = get_settings().max_upload_bytes
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, "That file is too large")
    result = import_data(data, start(db, user))
    return ImportOut(content=result.content, notice=result.notice)
