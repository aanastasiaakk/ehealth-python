"""Профілі користувачів."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import ensure_owner_or_admin, get_current_user
from app.models import User
from app.schemas import UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(user: User = Depends(get_current_user)):
    return user


@router.get("/{user_id}", response_model=UserOut)
def read_user(
    user_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Спочатку перевіряємо права, і лише потім шукаємо в базі:
    # так чужий користувач не дізнається навіть, чи існує такий id.
    ensure_owner_or_admin(current, user_id)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UserUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Змінити профіль. Захищено від IDOR: пацієнт з id=5 не може
    змінити профіль користувача з id=6, просто підставивши інше число в URL."""
    ensure_owner_or_admin(current, user_id)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    # exclude_unset: змінюємо лише ті поля, які реально прийшли в запиті
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user
