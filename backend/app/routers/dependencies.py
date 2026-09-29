from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_session

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
TagsQuery = Annotated[list[str] | None, Query(description="key:value; every tag must match")]
