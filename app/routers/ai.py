"""
Router para endpoints de IA (recomendações, sugestões)
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.dependencies import get_current_user
from app.services.recommendation_service import generate_savings_suggestions

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/ai/suggestions")
async def get_savings_suggestions(
    limit: int = Query(default=3, ge=1, le=10, description="Número máximo de sugestões"),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Retorna sugestões de economia baseadas nos gastos do usuário.
    
    Analisa os produtos mais comprados pelo usuário nos últimos 90 dias
    e sugere alternativas mais baratas encontradas no catálogo.
    
    Cada sugestão inclui:
    - Produto atual e preço
    - Produto sugerido e preço
    - Diferença de preço
    - Economia estimada por mês
    - Rationale (explicação da sugestão)
    - Confiança da sugestão (0-1)
    
    Returns:
        Lista de sugestões ordenadas por economia potencial
    """
    logger.info(f"Fetching savings suggestions for user: {user_id}, limit: {limit}")
    
    try:
        suggestions = generate_savings_suggestions(
            db=db,
            user_id=user_id,
            limit=limit
        )
        
        return {
            "suggestions": suggestions,
            "count": len(suggestions),
            "message": f"Encontradas {len(suggestions)} sugestões de economia"
        }
        
    except Exception as e:
        logger.error(f"Error generating suggestions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar sugestões de economia"
        )

