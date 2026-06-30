"""用户偏好记忆路由 - 存储并自动填充工作流参数偏好"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from db.models import UserPreference
from core.preference_schema import (
    get_preference_schema,
    get_valid_preference_keys,
    get_secret_preference_keys,
    mask_preference_value,
)
from pydantic import BaseModel
from typing import Dict

router = APIRouter()


class PreferenceUpdate(BaseModel):
    key: str
    value: str


class PreferenceBatchUpdate(BaseModel):
    preferences: Dict[str, str]


@router.get("/api/preferences/schema")
async def get_preferences_schema():
    """返回偏好 schema 列表(供前端 schema 驱动渲染)"""
    return get_preference_schema()


@router.get("/api/preferences")
async def get_preferences(db: Session = Depends(get_db)):
    """返回所有偏好值,secret 类型脱敏返回"""
    prefs = db.query(UserPreference).all()
    secret_keys = get_secret_preference_keys()
    result = {}
    for p in prefs:
        if p.key in secret_keys:
            result[p.key] = mask_preference_value(p.value)
        else:
            result[p.key] = p.value
    return result


@router.put("/api/preferences")
async def update_preferences(data: PreferenceBatchUpdate, db: Session = Depends(get_db)):
    """批量更新偏好,校验 key 必须在 schema 中"""
    valid_keys = get_valid_preference_keys()
    for key in data.preferences:
        if key not in valid_keys:
            raise HTTPException(status_code=400, detail=f"未知的偏好 key: {key}")

    for key, value in data.preferences.items():
        existing = db.query(UserPreference).filter(UserPreference.key == key).first()
        if existing:
            existing.value = value
        else:
            new_pref = UserPreference(key=key, value=value)
            db.add(new_pref)
    db.commit()
    return {"success": True}


@router.delete("/api/preferences/{key}")
async def delete_preference(key: str, db: Session = Depends(get_db)):
    """删除单条偏好,校验 key 必须在 schema 中"""
    valid_keys = get_valid_preference_keys()
    if key not in valid_keys:
        raise HTTPException(status_code=400, detail=f"未知的偏好 key: {key}")

    existing = db.query(UserPreference).filter(UserPreference.key == key).first()
    if not existing:
        raise HTTPException(status_code=404, detail=f"偏好 {key} 不存在")

    db.delete(existing)
    db.commit()
    return {"success": True}
