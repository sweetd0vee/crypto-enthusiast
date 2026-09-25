from fastapi import APIRouter, Depends

from app.api.deps import require_admin

router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])
