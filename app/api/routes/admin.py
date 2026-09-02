from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.schemas.admin import RecoveryCaseResponse, AdminActionResponse
from app.api.dependencies.auth import get_admin_user
from app.persistence.database import get_db
from app.domain.operations.service import AdminOperationsService

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(get_admin_user)]
)

@router.get("/cases/{case_id}", response_model=RecoveryCaseResponse)
def get_case(case_id: UUID, db: Session = Depends(get_db)):
    service = AdminOperationsService(db)
    return service.get_recovery_case(case_id)

@router.post("/cases/{case_id}/stop", response_model=AdminActionResponse)
def stop_case(case_id: UUID, db: Session = Depends(get_db)):
    service = AdminOperationsService(db)
    case = service.stop_recovery_case(case_id)
    return AdminActionResponse(
        status="success",
        message="Recovery case stopped successfully",
        case_id=case.id,
        case_status=case.status.value
    )

@router.post("/cases/{case_id}/retry", response_model=AdminActionResponse)
def retry_case(case_id: UUID, db: Session = Depends(get_db)):
    service = AdminOperationsService(db)
    case = service.force_retry_case(case_id)
    return AdminActionResponse(
        status="success",
        message="Recovery case retry queued successfully",
        case_id=case.id,
        case_status=case.status.value
    )
