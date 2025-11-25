"""
Router para endpoints de analytics
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.services.analytics_service import (
    get_monthly_summary,
    get_top_items,
    compare_store_prices
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/analytics/monthly-summary",
    dependencies=[Depends(get_current_user)]
)
async def monthly_summary(
    year: int = Query(..., description="Ano (ex: 2024)"),
    month: int = Query(..., ge=1, le=12, description="Mês (1-12)"),
    use_cache: bool = Query(True, description="Usar cache se disponível"),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Retorna resumo mensal de gastos do usuário.
    
    Inclui:
    - Total gasto no mês
    - Total por categoria
    - Top 10 itens mais comprados
    - Variação percentual vs mês anterior
    
    Os resultados são cacheados por mês para melhor performance.
    """
    try:
        result = get_monthly_summary(
            db=db,
            user_id=user_id,
            year=year,
            month=month,
            use_cache=use_cache
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating monthly summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao gerar resumo mensal"
        )


@router.get(
    "/analytics/top-items",
    dependencies=[Depends(get_current_user)]
)
async def top_items(
    limit: int = Query(20, ge=1, le=100, description="Número máximo de itens"),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Retorna os itens mais comprados pelo usuário.
    
    Ordenados por total gasto (maior primeiro).
    Cada item inclui:
    - Descrição
    - Quantidade total comprada
    - Total gasto
    - Preço médio
    - Número de compras
    """
    try:
        items = get_top_items(
            db=db,
            user_id=user_id,
            limit=limit
        )
        
        return {
            "items": items,
            "count": len(items)
        }
        
    except Exception as e:
        logger.error(f"Error getting top items: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar itens mais comprados"
        )


@router.get(
    "/analytics/compare-store",
    dependencies=[Depends(get_current_user)]
)
async def compare_store(
    product_id: UUID = Query(..., description="ID do produto"),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Compara preços de um produto em diferentes supermercados.
    
    Retorna:
    - Preço médio por supermercado
    - Menor preço encontrado
    - Loja com menor preço
    - Estatísticas de compras por loja
    
    Útil para identificar onde comprar mais barato.
    """
    try:
        result = compare_store_prices(
            db=db,
            user_id=user_id,
            product_id=product_id
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error comparing store prices: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao comparar preços por loja"
        )

