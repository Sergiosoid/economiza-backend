"""
Router para gerenciamento de créditos
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID, uuid4
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/credits")
async def get_credits(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Retorna o saldo de créditos do usuário atual.
    """
    try:
        db_user = db.query(User).filter(User.id == user_id).first()
        
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        return {
            "credits": db_user.credits or 0,
            "credits_purchased": db_user.credits_purchased or 0,
            "credits_used": db_user.credits_used or 0,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar créditos: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar créditos"
        )


@router.post("/credits/consume")
async def consume_credit(
    action_type: str = Query(..., description="Tipo de ação: 'scan', 'ai_analysis', etc."),
    action_id: UUID = Query(None, description="ID da ação (receipt_id, etc.)"),
    credits_amount: int = Query(1, description="Quantidade de créditos a consumir"),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Consome créditos do usuário para uma ação específica.
    
    Verifica:
    - Se o usuário tem créditos suficientes
    - Limite mensal do provider (se configurado)
    - Registra o uso no histórico
    """
    try:
        db_user = db.query(User).filter(User.id == user_id).first()
        
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Verificar limite mensal do provider (se configurado)
        provider_monthly_limit = getattr(settings, "PROVIDER_MONTHLY_LIMIT", None)
        if provider_monthly_limit is not None and provider_monthly_limit > 0:
            # Contar usos do mês atual
            now = datetime.utcnow()
            month_start = datetime(now.year, now.month, 1)
            
            from app.models.credit_usage import CreditUsage
            monthly_usage = db.query(func.sum(CreditUsage.credits_consumed)).filter(
                CreditUsage.user_id == user_id,
                CreditUsage.created_at >= month_start,
                CreditUsage.action_type == action_type
            ).scalar() or 0
            
            if monthly_usage + credits_amount > provider_monthly_limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Limite mensal do provider excedido. Limite: {provider_monthly_limit}, Usado: {monthly_usage}"
                )

        # Verificar se tem créditos suficientes
        current_credits = db_user.credits or 0
        if current_credits < credits_amount:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Créditos insuficientes. Disponível: {current_credits}, Necessário: {credits_amount}"
            )

        # Consumir créditos
        db_user.credits = current_credits - credits_amount
        db_user.credits_used = (db_user.credits_used or 0) + credits_amount

        # Registrar no histórico
        from app.models.credit_usage import CreditUsage
        usage_record = CreditUsage(
            id=uuid4(),
            user_id=user_id,
            credits_consumed=credits_amount,
            action_type=action_type,
            action_id=action_id
        )
        db.add(usage_record)
        db.commit()
        db.refresh(db_user)

        logger.info(f"Crédito consumido: user_id={user_id}, amount={credits_amount}, action={action_type}")

        return {
            "success": True,
            "credits_remaining": db_user.credits,
            "credits_consumed": credits_amount
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao consumir crédito: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao consumir crédito"
        )


@router.post("/credits/purchase/start")
async def start_purchase_credits(
    amount: int = Query(..., ge=1, le=1000, description="Quantidade de créditos a comprar"),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Inicia o processo de compra de créditos.
    
    Retorna URL de checkout do Stripe ou informações para pagamento.
    """
    try:
        db_user = db.query(User).filter(User.id == user_id).first()
        
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # TODO: Integrar com Stripe para criar sessão de checkout
        # Por enquanto, retorna estrutura básica
        
        # Em produção, aqui seria criada uma sessão de checkout do Stripe
        # com um price_id específico para créditos
        
        return {
            "checkout_url": f"{settings.FRONTEND_URL}/credits/checkout?amount={amount}",
            "amount": amount,
            "estimated_price": amount * 0.10,  # Exemplo: R$ 0,10 por crédito
            "message": "Redirecione o usuário para checkout_url para completar a compra"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao iniciar compra de créditos: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao iniciar compra de créditos"
        )


@router.post("/credits/add")
async def add_credits(
    amount: int = Query(..., ge=1, description="Quantidade de créditos a adicionar"),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Adiciona créditos ao usuário (usado após pagamento confirmado via webhook).
    
    ATENÇÃO: Este endpoint deve ser protegido e usado apenas por webhooks do Stripe.
    Em produção, adicione validação de assinatura do webhook.
    """
    try:
        db_user = db.query(User).filter(User.id == user_id).first()
        
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Adicionar créditos
        current_credits = db_user.credits or 0
        db_user.credits = current_credits + amount
        db_user.credits_purchased = (db_user.credits_purchased or 0) + amount
        
        db.commit()
        db.refresh(db_user)

        logger.info(f"Créditos adicionados: user_id={db_user.id}, amount={amount}")

        return {
            "success": True,
            "credits": db_user.credits,
            "credits_added": amount
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao adicionar créditos: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao adicionar créditos"
        )

