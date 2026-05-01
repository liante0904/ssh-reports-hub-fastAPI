from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..database import get_keywords_db
from ..dependencies import get_user_from_token
from ..models import InvestmentNote, User
from ..schemas import InvestmentNoteCreate, InvestmentNoteResponse, InvestmentNoteUpdate

router = APIRouter(prefix="/notes", tags=["notes"])
api_router = APIRouter(prefix="/api/notes", tags=["notes"], include_in_schema=False)


def _get_notes_query(current_user: User, db: Session):
    return db.query(InvestmentNote).filter(InvestmentNote.user_id == current_user.id).all()


def _create_note(note_in: InvestmentNoteCreate, current_user: User, db: Session):
    db_note = InvestmentNote(**note_in.model_dump(), user_id=current_user.id)
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note


def _update_note(note_id: int, note_update: InvestmentNoteUpdate, current_user: User, db: Session):
    db_note = db.query(InvestmentNote).filter(
        InvestmentNote.id == note_id,
        InvestmentNote.user_id == current_user.id
    ).first()

    if not db_note:
        raise HTTPException(status_code=404, detail="Note Not Found")

    update_data = note_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_note, key, value)

    db.commit()
    db.refresh(db_note)
    return db_note


def _delete_note(note_id: int, current_user: User, db: Session):
    db_note = db.query(InvestmentNote).filter(
        InvestmentNote.id == note_id,
        InvestmentNote.user_id == current_user.id
    ).first()

    if not db_note:
        raise HTTPException(status_code=404, detail="Note Not Found")

    db.delete(db_note)
    db.commit()
    return {"status": "success"}


@router.get("", response_model=List[InvestmentNoteResponse])
@router.get("/", response_model=List[InvestmentNoteResponse])
async def get_notes(
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db)
):
    return _get_notes_query(current_user, db)


@api_router.get("", response_model=List[InvestmentNoteResponse])
@api_router.get("/", response_model=List[InvestmentNoteResponse])
async def get_notes_api(
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db)
):
    return _get_notes_query(current_user, db)


@router.post("", response_model=InvestmentNoteResponse)
@router.post("/", response_model=InvestmentNoteResponse)
async def create_note(
    note_in: InvestmentNoteCreate,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db)
):
    return _create_note(note_in, current_user, db)


@api_router.post("", response_model=InvestmentNoteResponse)
@api_router.post("/", response_model=InvestmentNoteResponse)
async def create_note_api(
    note_in: InvestmentNoteCreate,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db)
):
    return _create_note(note_in, current_user, db)


@router.put("/{note_id}", response_model=InvestmentNoteResponse)
@router.put("/{note_id}/", response_model=InvestmentNoteResponse)
async def update_note(
    note_id: int,
    note_update: InvestmentNoteUpdate,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db)
):
    return _update_note(note_id, note_update, current_user, db)


@api_router.put("/{note_id}", response_model=InvestmentNoteResponse)
@api_router.put("/{note_id}/", response_model=InvestmentNoteResponse)
async def update_note_api(
    note_id: int,
    note_update: InvestmentNoteUpdate,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db)
):
    return _update_note(note_id, note_update, current_user, db)


@router.delete("/{note_id}")
@router.delete("/{note_id}/")
async def delete_note(
    note_id: int,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db)
):
    return _delete_note(note_id, current_user, db)


@api_router.delete("/{note_id}")
@api_router.delete("/{note_id}/")
async def delete_note_api(
    note_id: int,
    current_user: User = Depends(get_user_from_token),
    db: Session = Depends(get_keywords_db)
):
    return _delete_note(note_id, current_user, db)
