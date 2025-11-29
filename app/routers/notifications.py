"""
Router para endpoints de notificações
"""
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse, MarkReadRequest, MarkReadResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/notifications", response_model=List[NotificationResponse])
async def list_notifications(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Lista notificações do usuário.
    
    Query params:
    - limit: Número máximo de resultados (padrão: 50, máximo: 100)
    - offset: Número de resultados para pular (padrão: 0)
    - unread_only: Se True, retorna apenas notificações não lidas (padrão: False)
    """
    try:
        query = db.query(Notification).filter(Notification.user_id == user_id)
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        notifications = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset).all()
        
        logger.info(f"Listando {len(notifications)} notificações para usuário {user_id}")
        
        return [NotificationResponse.model_validate(notif) for notif in notifications]
    
    except Exception as e:
        logger.error(f"Erro ao listar notificações: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar notificações"
        )


@router.post("/notifications/mark-read", response_model=MarkReadResponse)
async def mark_notifications_read(
    request: MarkReadRequest,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Marca notificações como lidas.
    
    Body:
    {
        "notification_ids": ["uuid1", "uuid2", ...]
    }
    """
    try:
        # Verificar que todas as notificações pertencem ao usuário
        notifications = db.query(Notification).filter(
            Notification.id.in_(request.notification_ids),
            Notification.user_id == user_id
        ).all()
        
        marked_count = 0
        for notification in notifications:
            if not notification.is_read:
                notification.is_read = True
                marked_count += 1
        
        db.commit()
        
        logger.info(f"Marcadas {marked_count} notificações como lidas para usuário {user_id}")
        
        return MarkReadResponse(
            success=True,
            marked_count=marked_count
        )
    
    except Exception as e:
        logger.error(f"Erro ao marcar notificações como lidas: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao marcar notificações como lidas"
        )

