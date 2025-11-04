"""
User management endpoints
"""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, EmailStr, validator
import bcrypt
from app.models.database import get_db, User, RFIDCard
from app.core.config import get_egypt_now

router = APIRouter()

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    # Bcrypt has a 72-byte limit, so truncate if necessary
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    try:
        # Bcrypt has a 72-byte limit, so truncate if necessary
        password_bytes = plain_password.encode('utf-8')
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False

# Request/Response models
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username (unique)")
    email: EmailStr = Field(..., description="Email address (unique)")
    password: str = Field(..., min_length=6, max_length=72, description="Password (min 6 characters, max 72 bytes for bcrypt)")
    roles: Optional[List[str]] = Field(default_factory=lambda: ["viewer"], description="User roles")
    permissions: Optional[List[str]] = Field(default_factory=list, description="Additional permissions")
    organization_id: Optional[str] = Field(None, description="Organization ID")
    is_active: bool = Field(True, description="Whether user is active")
    is_verified: bool = Field(False, description="Whether user email is verified")
    
    @validator('password')
    def validate_password_length(cls, v):
        """Validate password doesn't exceed 72 bytes (bcrypt limit)"""
        if len(v.encode('utf-8')) > 72:
            raise ValueError('Password cannot exceed 72 bytes when encoded as UTF-8')
        return v

class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6, max_length=72, description="New password (if provided, will be hashed, max 72 bytes)")
    roles: Optional[List[str]] = None
    permissions: Optional[List[str]] = None
    organization_id: Optional[str] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    roles: List[str]
    permissions: List[str]
    organization_id: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime]

    class Config:
        from_attributes = True

class UserChangePassword(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=6, max_length=72, description="New password (min 6 characters, max 72 bytes)")
    
    @validator('new_password')
    def validate_password_length(cls, v):
        """Validate password doesn't exceed 72 bytes (bcrypt limit)"""
        if len(v.encode('utf-8')) > 72:
            raise ValueError('Password cannot exceed 72 bytes when encoded as UTF-8')
        return v

class UserResetPassword(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=72, description="New password (min 6 characters, max 72 bytes)")
    
    @validator('new_password')
    def validate_password_length(cls, v):
        """Validate password doesn't exceed 72 bytes (bcrypt limit)"""
        if len(v.encode('utf-8')) > 72:
            raise ValueError('Password cannot exceed 72 bytes when encoded as UTF-8')
        return v

@router.post("/users", response_model=UserResponse, tags=["Users"])
async def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    """Create a new user"""
    # Check if username already exists
    existing_username = db.query(User).filter(User.username == user.username).first()
    if existing_username:
        raise HTTPException(status_code=409, detail=f"Username '{user.username}' already exists")
    
    # Check if email already exists
    existing_email = db.query(User).filter(User.email == user.email).first()
    if existing_email:
        raise HTTPException(status_code=409, detail=f"Email '{user.email}' already exists")
    
    # Hash password
    hashed_password = hash_password(user.password)
    
    # Create new user
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        roles=user.roles or ["viewer"],
        permissions=user.permissions or [],
        organization_id=user.organization_id,
        is_active=user.is_active,
        is_verified=user.is_verified
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Return user without password
    return db_user

@router.get("/users", response_model=List[UserResponse], tags=["Users"])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = None,
    is_verified: Optional[bool] = None,
    organization_id: Optional[str] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List users with optional filters"""
    query = db.query(User)
    
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    
    if is_verified is not None:
        query = query.filter(User.is_verified == is_verified)
    
    if organization_id:
        query = query.filter(User.organization_id == organization_id)
    
    if role:
        query = query.filter(User.roles.contains([role]))
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (User.username.like(search_pattern)) |
            (User.email.like(search_pattern))
        )
    
    users = query.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    
    return users

@router.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
async def get_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Get user by ID"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    return user

@router.get("/users/username/{username}", response_model=UserResponse, tags=["Users"])
async def get_user_by_username(
    username: str,
    db: Session = Depends(get_db)
):
    """Get user by username"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with username '{username}' not found")
    
    return user

@router.get("/users/email/{email}", response_model=UserResponse, tags=["Users"])
async def get_user_by_email(
    email: str,
    db: Session = Depends(get_db)
):
    """Get user by email"""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with email '{email}' not found")
    
    return user

@router.put("/users/{user_id}", response_model=UserResponse, tags=["Users"])
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db)
):
    """Update user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Check if username is being changed and already exists
    if user_update.username and user_update.username != user.username:
        existing = db.query(User).filter(User.username == user_update.username).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Username '{user_update.username}' already exists")
    
    # Check if email is being changed and already exists
    if user_update.email and user_update.email != user.email:
        existing = db.query(User).filter(User.email == user_update.email).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Email '{user_update.email}' already exists")
    
    # Update fields
    update_data = user_update.dict(exclude_unset=True)
    
    # Hash password if provided
    if 'password' in update_data:
        update_data['hashed_password'] = hash_password(update_data.pop('password'))
    
    for field, value in update_data.items():
        setattr(user, field, value)
    
    user.updated_at = get_egypt_now()
    db.commit()
    db.refresh(user)
    
    return user

@router.delete("/users/{user_id}", tags=["Users"])
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Delete user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Check if user has associated RFID cards
    rfid_cards = db.query(RFIDCard).filter(RFIDCard.user_id == user_id).count()
    if rfid_cards > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete user: {rfid_cards} RFID card(s) are associated with this user. Please remove or reassign RFID cards first."
        )
    
    db.delete(user)
    db.commit()
    
    return {"message": f"User with ID {user_id} deleted successfully"}

@router.post("/users/{user_id}/activate", response_model=UserResponse, tags=["Users"])
async def activate_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Activate a user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    user.is_active = True
    user.updated_at = get_egypt_now()
    db.commit()
    db.refresh(user)
    
    return user

@router.post("/users/{user_id}/deactivate", response_model=UserResponse, tags=["Users"])
async def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Deactivate a user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    user.is_active = False
    user.updated_at = get_egypt_now()
    db.commit()
    db.refresh(user)
    
    return user

@router.post("/users/{user_id}/verify", response_model=UserResponse, tags=["Users"])
async def verify_user(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Mark user as verified"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    user.is_verified = True
    user.updated_at = get_egypt_now()
    db.commit()
    db.refresh(user)
    
    return user

@router.post("/users/{user_id}/change-password", tags=["Users"])
async def change_password(
    user_id: int,
    password_data: UserChangePassword,
    db: Session = Depends(get_db)
):
    """Change user password (requires current password)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Verify current password
    if not verify_password(password_data.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Update password
    user.hashed_password = hash_password(password_data.new_password)
    user.updated_at = get_egypt_now()
    db.commit()
    
    return {"message": "Password changed successfully"}

@router.post("/users/{user_id}/reset-password", tags=["Users"])
async def reset_password(
    user_id: int,
    password_data: UserResetPassword,
    db: Session = Depends(get_db)
):
    """Reset user password (admin function - no current password required)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Update password
    user.hashed_password = hash_password(password_data.new_password)
    user.updated_at = get_egypt_now()
    db.commit()
    
    return {"message": "Password reset successfully"}

@router.get("/users/{user_id}/rfid-cards", tags=["Users"])
async def get_user_rfid_cards(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Get all RFID cards associated with a user"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    rfid_cards = db.query(RFIDCard).filter(RFIDCard.user_id == user_id).all()
    
    return {
        "user_id": user_id,
        "username": user.username,
        "rfid_cards": [
            {
                "id": card.id,
                "id_tag": card.id_tag,
                "card_number": card.card_number,
                "holder_name": card.holder_name,
                "is_active": card.is_active,
                "is_blocked": card.is_blocked,
                "created_at": card.created_at.isoformat(),
                "last_used_at": card.last_used_at.isoformat() if card.last_used_at else None
            }
            for card in rfid_cards
        ],
        "total": len(rfid_cards)
    }

@router.get("/users/{user_id}/stats", tags=["Users"])
async def get_user_stats(
    user_id: int,
    db: Session = Depends(get_db)
):
    """Get user statistics"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    rfid_cards_count = db.query(RFIDCard).filter(RFIDCard.user_id == user_id).count()
    active_rfid_cards = db.query(RFIDCard).filter(
        RFIDCard.user_id == user_id,
        RFIDCard.is_active == True,
        RFIDCard.is_blocked == False
    ).count()
    
    return {
        "user_id": user_id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "roles": user.roles,
        "rfid_cards_total": rfid_cards_count,
        "rfid_cards_active": active_rfid_cards,
        "created_at": user.created_at.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None
    }

