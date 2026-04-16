from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from core.deps import get_db, get_current_user
from core.security import hash_password, verify_password, create_access_token
from models import User, UserRole
from api.schemas import UserCreate, UserOut, TokenOut

router = APIRouter()


@router.post("/register", response_model=UserOut)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="邮箱已存在")

    role_map = {"consumer": UserRole.CONSUMER, "farmer": UserRole.FARMER, "admin": UserRole.ADMIN}
    role = role_map.get(payload.role.lower())
    if not role:
        raise HTTPException(status_code=400, detail="角色不合法")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token(subject=user.username, extra={"role": user.role.value, "uid": user.id})
    return TokenOut(access_token=token)


from pydantic import BaseModel

class LoginJson(BaseModel):
    username: str
    password: str

@router.post("/login_json", response_model=TokenOut, summary="登录（JSON）")
def login_json(payload: LoginJson, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_access_token(subject=user.username, extra={"role": user.role.value, "uid": user.id})
    return TokenOut(access_token=token)


# 获取当前登录用户信息（含 id，供前端存储 userId）
@router.get("/me", response_model=UserOut, summary="获取当前用户信息")
def get_me(current_user: User = Depends(get_current_user)):
    return current_user