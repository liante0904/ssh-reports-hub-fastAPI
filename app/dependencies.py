from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_keywords_db
from .models import User
from .security import decode_access_token
from .settings import get_settings, Settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/telegram")

async def get_settings_dep() -> Settings:
    return get_settings()

async def get_user_from_token(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_keywords_db),
    settings: Settings = Depends(get_settings_dep)
):
    payload = decode_access_token(token, settings)
    user_id = payload["sub"]
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User Not Found")
    return user
