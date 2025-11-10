"""
RFID Card management endpoints
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from app.models.database import get_db, RFIDCard, User
from app.core.config import get_egypt_now

router = APIRouter()

# Request/Response models
class RFIDCardCreate(BaseModel):
    id_tag: str = Field(..., description="RFID tag ID (unique)")
    card_number: Optional[str] = Field(None, description="Physical card number")
    holder_name: Optional[str] = Field(None, description="Card holder name")
    description: Optional[str] = Field(None, description="Optional description")
    is_active: bool = Field(True, description="Whether card is active")
    is_blocked: bool = Field(False, description="Whether card is blocked")
    expires_at: Optional[datetime] = Field(None, description="Card expiration date")
    user_id: Optional[int] = Field(None, description="Associated user ID")
    organization_id: Optional[str] = Field(None, description="Organization ID")
    site_id: Optional[str] = Field(None, description="Site ID")
    card_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    wattage_limit: Optional[float] = Field(None, ge=0, description="Total wattage limit assigned to this RFID card (in Wh). When set, remaining_wattage will be initialized to this value.")

class RFIDCardUpdate(BaseModel):
    card_number: Optional[str] = None
    holder_name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    is_blocked: Optional[bool] = None
    expires_at: Optional[datetime] = None
    user_id: Optional[int] = None
    organization_id: Optional[str] = None
    site_id: Optional[str] = None
    card_metadata: Optional[Dict[str, Any]] = None
    wattage_limit: Optional[float] = Field(None, ge=0, description="Total wattage limit assigned to this RFID card (in Wh). If updated, remaining_wattage will be reset to this value if not already set.")

class RFIDCardResponse(BaseModel):
    id: int
    id_tag: str
    card_number: Optional[str]
    holder_name: Optional[str]
    description: Optional[str]
    is_active: bool
    is_blocked: bool
    expires_at: Optional[datetime]
    user_id: Optional[int]
    organization_id: Optional[str]
    site_id: Optional[str]
    card_metadata: Dict[str, Any]
    wattage_limit: Optional[float]
    remaining_wattage: Optional[float]
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime]

    class Config:
        from_attributes = True

class RFIDCardStatusResponse(BaseModel):
    id_tag: str
    exists: bool
    status: str  # Accepted, Blocked, Expired, Invalid
    is_active: bool
    is_blocked: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]

def get_authorization_status(card: Optional[RFIDCard]) -> str:
    """Determine authorization status for an RFID card"""
    if not card:
        return "Invalid"
    
    if card.is_blocked:
        return "Blocked"
    
    if not card.is_active:
        return "Invalid"
    
    if card.expires_at:
        current_time = get_egypt_now()
        if card.expires_at < current_time:
            return "Expired"
    
    return "Accepted"

@router.post("/rfid-cards", response_model=RFIDCardResponse, tags=["RFID Cards"])
async def create_rfid_card(
    card: RFIDCardCreate,
    db: Session = Depends(get_db)
):
    """Create a new RFID card"""
    # Check if id_tag already exists
    existing = db.query(RFIDCard).filter(RFIDCard.id_tag == card.id_tag).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"RFID card with id_tag '{card.id_tag}' already exists")
    
    # Check if user_id exists (if provided)
    if card.user_id:
        user = db.query(User).filter(User.id == card.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ID {card.user_id} not found")
    
    # Create new RFID card
    db_card = RFIDCard(
        id_tag=card.id_tag,
        card_number=card.card_number,
        holder_name=card.holder_name,
        description=card.description,
        is_active=card.is_active,
        is_blocked=card.is_blocked,
        expires_at=card.expires_at,
        user_id=card.user_id,
        organization_id=card.organization_id,
        site_id=card.site_id,
        card_metadata=card.card_metadata or {},
        wattage_limit=card.wattage_limit,
        remaining_wattage=card.wattage_limit if card.wattage_limit is not None else None
    )
    
    db.add(db_card)
    db.commit()
    db.refresh(db_card)
    
    return db_card

@router.get("/rfid-cards", response_model=List[RFIDCardResponse], tags=["RFID Cards"])
async def list_rfid_cards(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    is_active: Optional[bool] = None,
    is_blocked: Optional[bool] = None,
    organization_id: Optional[str] = None,
    site_id: Optional[str] = None,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List RFID cards with optional filters"""
    query = db.query(RFIDCard)
    
    if is_active is not None:
        query = query.filter(RFIDCard.is_active == is_active)
    
    if is_blocked is not None:
        query = query.filter(RFIDCard.is_blocked == is_blocked)
    
    if organization_id:
        query = query.filter(RFIDCard.organization_id == organization_id)
    
    if site_id:
        query = query.filter(RFIDCard.site_id == site_id)
    
    if user_id:
        query = query.filter(RFIDCard.user_id == user_id)
    
    cards = query.order_by(RFIDCard.created_at.desc()).offset(skip).limit(limit).all()
    
    return cards

@router.get("/rfid-cards/{id_tag}", response_model=RFIDCardResponse, tags=["RFID Cards"])
async def get_rfid_card(
    id_tag: str,
    db: Session = Depends(get_db)
):
    """Get RFID card by id_tag"""
    card = db.query(RFIDCard).filter(RFIDCard.id_tag == id_tag).first()
    if not card:
        raise HTTPException(status_code=404, detail=f"RFID card with id_tag '{id_tag}' not found")
    
    return card

@router.put("/rfid-cards/{id_tag}", response_model=RFIDCardResponse, tags=["RFID Cards"])
async def update_rfid_card(
    id_tag: str,
    card_update: RFIDCardUpdate,
    db: Session = Depends(get_db)
):
    """Update RFID card"""
    card = db.query(RFIDCard).filter(RFIDCard.id_tag == id_tag).first()
    if not card:
        raise HTTPException(status_code=404, detail=f"RFID card with id_tag '{id_tag}' not found")
    
    # Check if user_id exists (if being updated)
    if card_update.user_id is not None and card_update.user_id != card.user_id:
        user = db.query(User).filter(User.id == card_update.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail=f"User with ID {card_update.user_id} not found")
    
    # Update fields
    update_data = card_update.dict(exclude_unset=True)
    
    # If wattage_limit is being updated and remaining_wattage is not set, reset it to the new limit
    if "wattage_limit" in update_data and update_data["wattage_limit"] is not None:
        if card.remaining_wattage is None:
            update_data["remaining_wattage"] = update_data["wattage_limit"]
    
    for field, value in update_data.items():
        setattr(card, field, value)
    
    card.updated_at = get_egypt_now()
    db.commit()
    db.refresh(card)
    
    return card

@router.delete("/rfid-cards/{id_tag}", tags=["RFID Cards"])
async def delete_rfid_card(
    id_tag: str,
    db: Session = Depends(get_db)
):
    """Delete RFID card"""
    card = db.query(RFIDCard).filter(RFIDCard.id_tag == id_tag).first()
    if not card:
        raise HTTPException(status_code=404, detail=f"RFID card with id_tag '{id_tag}' not found")
    
    db.delete(card)
    db.commit()
    
    return {"message": f"RFID card with id_tag '{id_tag}' deleted successfully"}

@router.post("/rfid-cards/{id_tag}/block", response_model=RFIDCardResponse, tags=["RFID Cards"])
async def block_rfid_card(
    id_tag: str,
    db: Session = Depends(get_db)
):
    """Block an RFID card"""
    card = db.query(RFIDCard).filter(RFIDCard.id_tag == id_tag).first()
    if not card:
        raise HTTPException(status_code=404, detail=f"RFID card with id_tag '{id_tag}' not found")
    
    card.is_blocked = True
    card.updated_at = get_egypt_now()
    db.commit()
    db.refresh(card)
    
    return card

@router.post("/rfid-cards/{id_tag}/unblock", response_model=RFIDCardResponse, tags=["RFID Cards"])
async def unblock_rfid_card(
    id_tag: str,
    db: Session = Depends(get_db)
):
    """Unblock an RFID card"""
    card = db.query(RFIDCard).filter(RFIDCard.id_tag == id_tag).first()
    if not card:
        raise HTTPException(status_code=404, detail=f"RFID card with id_tag '{id_tag}' not found")
    
    card.is_blocked = False
    card.updated_at = get_egypt_now()
    db.commit()
    db.refresh(card)
    
    return card

@router.post("/rfid-cards/{id_tag}/activate", response_model=RFIDCardResponse, tags=["RFID Cards"])
async def activate_rfid_card(
    id_tag: str,
    db: Session = Depends(get_db)
):
    """Activate an RFID card"""
    card = db.query(RFIDCard).filter(RFIDCard.id_tag == id_tag).first()
    if not card:
        raise HTTPException(status_code=404, detail=f"RFID card with id_tag '{id_tag}' not found")
    
    card.is_active = True
    card.updated_at = get_egypt_now()
    db.commit()
    db.refresh(card)
    
    return card

@router.post("/rfid-cards/{id_tag}/deactivate", response_model=RFIDCardResponse, tags=["RFID Cards"])
async def deactivate_rfid_card(
    id_tag: str,
    db: Session = Depends(get_db)
):
    """Deactivate an RFID card"""
    card = db.query(RFIDCard).filter(RFIDCard.id_tag == id_tag).first()
    if not card:
        raise HTTPException(status_code=404, detail=f"RFID card with id_tag '{id_tag}' not found")
    
    card.is_active = False
    card.updated_at = get_egypt_now()
    db.commit()
    db.refresh(card)
    
    return card

@router.get("/rfid-cards/{id_tag}/status", response_model=RFIDCardStatusResponse, tags=["RFID Cards"])
async def get_rfid_card_status(
    id_tag: str,
    db: Session = Depends(get_db)
):
    """Check RFID card authorization status"""
    card = db.query(RFIDCard).filter(RFIDCard.id_tag == id_tag).first()
    
    if not card:
        return RFIDCardStatusResponse(
            id_tag=id_tag,
            exists=False,
            status="Invalid",
            is_active=False,
            is_blocked=False,
            expires_at=None,
            last_used_at=None
        )
    
    status = get_authorization_status(card)
    
    return RFIDCardStatusResponse(
        id_tag=card.id_tag,
        exists=True,
        status=status,
        is_active=card.is_active,
        is_blocked=card.is_blocked,
        expires_at=card.expires_at,
        last_used_at=card.last_used_at
    )

@router.post("/rfid-cards/bulk", response_model=List[RFIDCardResponse], tags=["RFID Cards"])
async def bulk_create_rfid_cards(
    cards: List[RFIDCardCreate],
    db: Session = Depends(get_db)
):
    """Bulk create RFID cards"""
    created_cards = []
    errors = []
    
    for card_data in cards:
        # Check if id_tag already exists
        existing = db.query(RFIDCard).filter(RFIDCard.id_tag == card_data.id_tag).first()
        if existing:
            errors.append(f"RFID card with id_tag '{card_data.id_tag}' already exists")
            continue
        
        # Check if user_id exists (if provided)
        if card_data.user_id:
            user = db.query(User).filter(User.id == card_data.user_id).first()
            if not user:
                errors.append(f"User with ID {card_data.user_id} not found for card '{card_data.id_tag}'")
                continue
        
        # Create new RFID card
        db_card = RFIDCard(
            id_tag=card_data.id_tag,
            card_number=card_data.card_number,
            holder_name=card_data.holder_name,
            description=card_data.description,
            is_active=card_data.is_active,
            is_blocked=card_data.is_blocked,
            expires_at=card_data.expires_at,
            user_id=card_data.user_id,
            organization_id=card_data.organization_id,
            site_id=card_data.site_id,
            card_metadata=card_data.card_metadata or {},
            wattage_limit=card_data.wattage_limit,
            remaining_wattage=card_data.wattage_limit if card_data.wattage_limit is not None else None
        )
        
        db.add(db_card)
        created_cards.append(db_card)
    
    if errors:
        db.rollback()
        raise HTTPException(status_code=400, detail={
            "message": "Some cards could not be created",
            "errors": errors,
            "created_count": 0
        })
    
    db.commit()
    
    # Refresh all created cards
    for card in created_cards:
        db.refresh(card)
    
    return created_cards

