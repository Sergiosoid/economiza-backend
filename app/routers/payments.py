"""
Router para endpoints de pagamento (Stripe)
"""
import logging
import stripe
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Configurar Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Planos disponíveis
PLANS = {
    "pro": {
        "name": "PRO",
        "price_id": settings.STRIPE_PRICE_ID_PRO,
        "features": [
            "Scans ilimitados",
            "Análises avançadas",
            "Exportação de dados",
            "Suporte prioritário"
        ]
    }
}


@router.post(
    "/payments/create-checkout-session",
    dependencies=[Depends(get_current_user)]
)
async def create_checkout_session(
    plan: str = "pro",
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Cria uma sessão de checkout do Stripe para assinatura PRO.
    
    Args:
        plan: Plano a assinar (padrão: "pro")
        
    Returns:
        URL da sessão de checkout do Stripe
    """
    if plan not in PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plano inválido. Planos disponíveis: {list(PLANS.keys())}"
        )
    
    # Verificar se usuário já é PRO
    user = db.query(User).filter(
        User.id == user_id
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.is_pro:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já possui assinatura PRO ativa"
        )
    
    plan_config = PLANS[plan]
    
    try:
        # Criar ou buscar customer no Stripe
        customer_id = user.stripe_customer_id
        if not customer_id:
            # Criar novo customer
            customer = stripe.Customer.create(
                email=user.email,
                metadata={
                    'user_id': str(user_id)
                }
            )
            customer_id = customer.id
            
            # Salvar customer_id no banco
            user.stripe_customer_id = customer_id
            db.commit()
            logger.info(f"Created Stripe customer: {customer_id} for user: {user_id}")
        
        # Criar sessão de checkout no Stripe
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            customer=customer_id,
            line_items=[{
                'price': plan_config['price_id'],
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"{settings.FRONTEND_URL}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.FRONTEND_URL}/payment/cancel",
            metadata={
                'user_id': str(user_id),
                'plan': plan
            },
            subscription_data={
                'metadata': {
                    'user_id': str(user_id),
                    'plan': plan
                }
            }
        )
        
        logger.info(f"Checkout session created: {checkout_session.id} for user: {user_id}")
        
        return {
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar sessão de checkout: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error creating checkout session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao criar sessão de checkout"
        )


@router.post("/payments/webhook")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook do Stripe para processar eventos de assinatura.
    
    Eventos processados:
    - checkout.session.completed: Marca usuário como PRO
    - customer.subscription.updated: Atualiza status da assinatura
    - customer.subscription.deleted: Remove status PRO
    """
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing stripe-signature header"
        )
    
    # Validar assinatura do webhook
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured"
        )
    
    try:
        # Verificar assinatura do webhook
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        logger.debug(f"Webhook signature verified for event: {event.get('type', 'unknown')}")
    except ValueError as e:
        logger.warning(f"Invalid webhook payload: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload"
        )
    except stripe.error.SignatureVerificationError as e:
        logger.warning(f"Invalid webhook signature: {e}")
        # Logar tentativa de webhook inválido (possível ataque)
        logger.warning(f"Webhook signature verification failed - possible attack attempt")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature"
        )
    
    # Processar evento
    event_type = event['type']
    event_data = event['data']['object']
    
    logger.info(f"Processing Stripe webhook event: {event_type}")
    
    try:
        if event_type == 'checkout.session.completed':
            # Assinatura concluída
            session = event_data
            user_id = session.get('metadata', {}).get('user_id')
            subscription_id = session.get('subscription')
            customer_id = session.get('customer')
            
            if user_id and subscription_id:
                # Buscar subscription para obter customer_id se não estiver na session
                if not customer_id:
                    subscription = stripe.Subscription.retrieve(subscription_id)
                    customer_id = subscription.customer
                
                _update_user_subscription(
                    db=db,
                    user_id=UUID(user_id),
                    customer_id=customer_id,
                    subscription_id=subscription_id,
                    is_pro=True
                )
                logger.info(f"User {user_id} upgraded to PRO (subscription: {subscription_id}, customer: {customer_id})")
        
        elif event_type == 'customer.subscription.updated':
            # Assinatura atualizada
            subscription = event_data
            subscription_id = subscription.get('id')
            status_sub = subscription.get('status')
            customer_id = subscription.get('customer')
            user_id = subscription.get('metadata', {}).get('user_id')
            
            if user_id and subscription_id:
                is_pro = status_sub in ['active', 'trialing']
                _update_user_subscription(
                    db=db,
                    user_id=UUID(user_id),
                    customer_id=customer_id,
                    subscription_id=subscription_id,
                    is_pro=is_pro
                )
                logger.info(f"Subscription {subscription_id} updated for user {user_id}: is_pro={is_pro}")
        
        elif event_type == 'customer.subscription.deleted':
            # Assinatura cancelada
            subscription = event_data
            subscription_id = subscription.get('id')
            user_id = subscription.get('metadata', {}).get('user_id')
            
            if user_id:
                _update_user_subscription(
                    db=db,
                    user_id=UUID(user_id),
                    subscription_id=None,
                    is_pro=False
                )
                logger.info(f"User {user_id} subscription cancelled")
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        # Retornar 200 para evitar retries do Stripe
        return {"status": "error", "message": str(e)}


def _update_user_subscription(
    db: Session,
    user_id: UUID,
    subscription_id: Optional[str],
    is_pro: bool,
    customer_id: Optional[str] = None
):
    """
    Atualiza status de assinatura do usuário.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        logger.warning(f"User not found: {user_id}")
        return
    
    user.is_pro = is_pro
    user.subscription_id = subscription_id
    
    # Atualizar customer_id se fornecido
    if customer_id:
        user.stripe_customer_id = customer_id
    
    db.commit()
    
    logger.info(f"User {user_id} updated: is_pro={is_pro}, subscription_id={subscription_id}, customer_id={customer_id}")


@router.get(
    "/payments/subscription-status",
    dependencies=[Depends(get_current_user)]
)
async def get_subscription_status(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Retorna o status da assinatura do usuário.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "is_pro": user.is_pro,
        "subscription_id": user.subscription_id,
        "customer_id": user.stripe_customer_id,
        "plan": "pro" if user.is_pro else None
    }

