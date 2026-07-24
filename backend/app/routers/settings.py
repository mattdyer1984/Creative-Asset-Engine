"""
Settings API — Phase 12 (Human Feedback & Learning System, see
MIGRATION_PLAN.md). Just the one real setting asked for so far
(Learning Mode). Lazily creates the AppSetting singleton row on first
read - callers never need to know whether it's been initialized yet.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.app_setting import SINGLETON_ID, AppSetting
from app.schemas import AppSettingRead, AppSettingUpdateRequest

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _get_or_create_settings(db: Session) -> AppSetting:
    settings_row = db.get(AppSetting, SINGLETON_ID)
    if settings_row is None:
        settings_row = AppSetting(id=SINGLETON_ID)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


@router.get("", response_model=AppSettingRead)
def get_settings(db: Session = Depends(get_db)) -> AppSetting:
    return _get_or_create_settings(db)


@router.put("", response_model=AppSettingRead)
def update_settings(payload: AppSettingUpdateRequest, db: Session = Depends(get_db)) -> AppSetting:
    settings_row = _get_or_create_settings(db)
    settings_row.learning_mode_enabled = payload.learning_mode_enabled
    db.commit()
    db.refresh(settings_row)
    return settings_row
