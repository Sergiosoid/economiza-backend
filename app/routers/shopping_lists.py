"""
Router para endpoints de listas de compras e unidades
"""
import logging
from typing import List
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from uuid import UUID
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.unit import Unit
from app.models.shopping_list import ShoppingList, ShoppingListItem
from app.schemas.shopping_list import (
    UnitResponse,
    ShoppingListCreate,
    ShoppingListResponse,
    ShoppingListItemCreate,
    ShoppingListItemResponse,
    ShoppingListEstimateResponse,
    ShoppingListItemEstimateResponse,
    ShoppingListSyncResponse,
    ItemComparisonResponse,
)
from app.services.price_engine import estimate_item_price
from app.services.list_sync import (
    find_best_match_for_list_item,
    compare_quantities_and_price,
    build_item_comparison,
    build_unplanned_item_comparison,
)
from app.models.shopping_list_execution import ShoppingListExecution
from app.models.receipt import Receipt
from app.models.notification import Notification
from app.services.pdf_generator import generate_sync_pdf
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/units", response_model=List[UnitResponse])
async def get_units(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Retorna todas as unidades disponíveis.
    
    Não requer autenticação específica, mas usa get_current_user para manter consistência.
    """
    try:
        units = db.query(Unit).order_by(Unit.type, Unit.code).all()
        return [UnitResponse.model_validate(unit) for unit in units]
    except Exception as e:
        logger.error(f"Erro ao buscar unidades: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar unidades"
        )


@router.post("/shopping-lists", response_model=ShoppingListResponse, status_code=status.HTTP_201_CREATED)
async def create_shopping_list(
    data: ShoppingListCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Cria uma nova lista de compras com itens.
    
    Body:
    {
        "name": "Lista do mercado",
        "items": [
            {
                "description": "Arroz 5kg",
                "quantity": 5000,
                "unit_code": "g",
                "product_id": null
            }
        ]
    }
    """
    try:
        # Buscar unidades para validar e obter informações
        unit_map = {}
        for unit in db.query(Unit).all():
            unit_map[unit.code] = unit

        # Criar lista de compras
        shopping_list = ShoppingList(
            user_id=user_id,
            name=data.name,
            is_shared=False,
            meta=None
        )
        db.add(shopping_list)
        db.flush()  # Para obter o ID

        # Criar itens
        items = []
        for item_data in data.items:
            # Validar unidade
            if item_data.unit_code not in unit_map:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unidade '{item_data.unit_code}' não encontrada"
                )
            
            unit = unit_map[item_data.unit_code]
            
            item = ShoppingListItem(
                shopping_list_id=shopping_list.id,
                product_id=item_data.product_id,
                description=item_data.description,
                quantity=item_data.quantity,
                unit_code=unit.code,
                unit_type=unit.type,  # unit_type = unidade.type
                unit_multiplier=unit.multiplier,  # unit_multiplier = unidade.multiplier
                price_estimate=None
            )
            db.add(item)
            items.append(item)

        db.commit()
        db.refresh(shopping_list)

        # Carregar itens para resposta
        db.refresh(shopping_list)
        for item in items:
            db.refresh(item)

        logger.info(f"Lista de compras criada: list_id={shopping_list.id}, user_id={user_id}, items_count={len(items)}")

        return ShoppingListResponse(
            id=shopping_list.id,
            user_id=shopping_list.user_id,
            name=shopping_list.name,
            is_shared=shopping_list.is_shared,
            meta=shopping_list.meta,
            items=[ShoppingListItemResponse.model_validate(item) for item in items],
            created_at=shopping_list.created_at,
            updated_at=shopping_list.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao criar lista de compras: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar lista de compras: {str(e)}"
        )


@router.get("/shopping-lists/{list_id}", response_model=ShoppingListResponse)
async def get_shopping_list(
    list_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Retorna uma lista de compras específica com seus itens.
    
    Verifica se a lista pertence ao usuário autenticado.
    """
    try:
        shopping_list = db.query(ShoppingList).filter(
            ShoppingList.id == list_id,
            ShoppingList.user_id == user_id
        ).first()

        if not shopping_list:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lista de compras não encontrada"
            )

        # Carregar itens
        items = db.query(ShoppingListItem).filter(
            ShoppingListItem.shopping_list_id == list_id
        ).order_by(ShoppingListItem.created_at).all()

        return ShoppingListResponse(
            id=shopping_list.id,
            user_id=shopping_list.user_id,
            name=shopping_list.name,
            is_shared=shopping_list.is_shared,
            meta=shopping_list.meta,
            items=[ShoppingListItemResponse.model_validate(item) for item in items],
            created_at=shopping_list.created_at,
            updated_at=shopping_list.updated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar lista de compras: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar lista de compras"
        )


@router.get("/shopping-lists", response_model=List[ShoppingListResponse])
async def list_shopping_lists(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Lista todas as listas de compras do usuário.
    
    Query params:
    - limit: Número máximo de resultados (padrão: 10, máximo: 100)
    - offset: Número de resultados para pular (padrão: 0)
    """
    try:
        shopping_lists = db.query(ShoppingList).filter(
            ShoppingList.user_id == user_id
        ).order_by(ShoppingList.updated_at.desc()).limit(limit).offset(offset).all()

        result = []
        for sl in shopping_lists:
            # Carregar itens para cada lista
            items = db.query(ShoppingListItem).filter(
                ShoppingListItem.shopping_list_id == sl.id
            ).order_by(ShoppingListItem.created_at).all()

            result.append(ShoppingListResponse(
                id=sl.id,
                user_id=sl.user_id,
                name=sl.name,
                is_shared=sl.is_shared,
                meta=sl.meta,
                items=[ShoppingListItemResponse.model_validate(item) for item in items],
                created_at=sl.created_at,
                updated_at=sl.updated_at
            ))

        return result

    except Exception as e:
        logger.error(f"Erro ao listar listas de compras: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar listas de compras"
        )


@router.post("/shopping-lists/{list_id}/estimate", response_model=ShoppingListEstimateResponse)
async def estimate_shopping_list(
    list_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Calcula estimativa de preços para uma lista de compras
    baseado no histórico de compras do usuário.
    
    Retorna:
    - list_id: ID da lista
    - total_estimate: Soma das estimativas de todos os itens
    - items: Array com estimativas individuais de cada item
    """
    try:
        # Verificar se a lista pertence ao usuário
        shopping_list = db.query(ShoppingList).filter(
            ShoppingList.id == list_id,
            ShoppingList.user_id == user_id
        ).first()

        if not shopping_list:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lista de compras não encontrada"
            )

        # Buscar itens da lista
        items = db.query(ShoppingListItem).filter(
            ShoppingListItem.shopping_list_id == list_id
        ).all()

        if not items:
            return ShoppingListEstimateResponse(
                list_id=list_id,
                total_estimate=None,
                items=[]
            )

        # Estimar preço para cada item
        estimated_items = []
        total_estimate = Decimal('0.0')

        for item in items:
            estimate = estimate_item_price(item, db, user_id)
            
            estimated_items.append(ShoppingListItemEstimateResponse(
                id=item.id,
                description=item.description,
                quantity=float(item.quantity),
                unit_code=item.unit_code,
                unit_price_estimate=float(estimate["unit_price_estimate"]) if estimate["unit_price_estimate"] else None,
                total_price_estimate=float(estimate["total_price_estimate"]) if estimate["total_price_estimate"] else None,
                confidence=estimate["confidence"]
            ))

            # Somar ao total se houver estimativa
            if estimate["total_price_estimate"]:
                total_estimate += estimate["total_price_estimate"]

        logger.info(f"Estimativa calculada para lista {list_id}: total={total_estimate}, items={len(estimated_items)}")

        return ShoppingListEstimateResponse(
            list_id=list_id,
            total_estimate=float(total_estimate) if total_estimate > 0 else None,
            items=estimated_items
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao estimar preços da lista: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao estimar preços: {str(e)}"
        )


@router.post("/shopping-lists/{list_id}/sync-with-receipt/{receipt_id}", response_model=ShoppingListSyncResponse)
async def sync_shopping_list_with_receipt(
    list_id: UUID,
    receipt_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Sincroniza uma lista de compras com uma nota fiscal.
    
    Compara itens planejados com itens comprados, calcula diferenças de preço e quantidade,
    e salva histórico da execução.
    
    Args:
        list_id: ID da lista de compras
        receipt_id: ID da nota fiscal
        db: Sessão do banco de dados
        user_id: ID do usuário autenticado
        
    Returns:
        ShoppingListSyncResponse com comparação detalhada
    """
    try:
        # Verificar se a lista pertence ao usuário
        shopping_list = db.query(ShoppingList).filter(
            ShoppingList.id == list_id,
            ShoppingList.user_id == user_id
        ).first()

        if not shopping_list:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Lista de compras não encontrada ou não pertence ao usuário"
            )

        # Verificar se a nota pertence ao usuário
        receipt = db.query(Receipt).filter(
            Receipt.id == receipt_id,
            Receipt.user_id == user_id
        ).first()

        if not receipt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nota fiscal não encontrada ou não pertence ao usuário"
            )

        # Carregar itens da lista
        list_items = db.query(ShoppingListItem).filter(
            ShoppingListItem.shopping_list_id == list_id
        ).all()

        # Carregar itens da nota
        receipt_items = db.query(ReceiptItem).filter(
            ReceiptItem.receipt_id == receipt_id
        ).all()

        logger.info(f"Sincronizando lista {list_id} com nota {receipt_id}: {len(list_items)} itens planejados, {len(receipt_items)} itens na nota")

        # Lista de itens da nota já mapeados (para evitar duplicação)
        matched_receipt_items = set()
        
        # Array de comparações
        comparisons = []
        
        # Processar cada item da lista
        for list_item in list_items:
            # Buscar melhor match entre receipt_items não mapeados
            available_receipt_items = [
                ri for idx, ri in enumerate(receipt_items)
                if idx not in matched_receipt_items
            ]
            
            matched_item, score = find_best_match_for_list_item(
                list_item,
                available_receipt_items,
                db,
                user_id
            )
            
            if matched_item and score > 0:
                # Encontrar índice do item mapeado
                matched_idx = receipt_items.index(matched_item)
                matched_receipt_items.add(matched_idx)
                
                # Comparar quantidades e preços
                comparison_data = compare_quantities_and_price(list_item, matched_item)
                
                # Construir comparação
                comparison = build_item_comparison(list_item, matched_item, comparison_data)
                comparisons.append(comparison)
            else:
                # Item não encontrado na nota
                comparison = build_item_comparison(list_item, None, None)
                comparisons.append(comparison)

        # Processar itens da nota não mapeados (itens extras)
        for idx, receipt_item in enumerate(receipt_items):
            if idx not in matched_receipt_items:
                comparison = build_unplanned_item_comparison(receipt_item)
                comparisons.append(comparison)

        # Calcular totais
        planned_total = Decimal('0.0')
        real_total = Decimal('0.0')
        items_planned = 0
        items_purchased = 0
        items_missing = 0
        items_extra = 0

        for comp in comparisons:
            if comp["planned_total"] is not None:
                planned_total += Decimal(str(comp["planned_total"]))
                items_planned += 1
            
            if comp["real_total"] is not None:
                real_total += Decimal(str(comp["real_total"]))
                items_purchased += 1
            
            if comp["status"] == "PLANNED_NOT_PURCHASED":
                items_missing += 1
            elif comp["status"] == "PURCHASED_NOT_PLANNED":
                items_extra += 1

        # Calcular diferença
        difference = real_total - planned_total if planned_total > 0 else None
        difference_percent = None
        if planned_total > 0 and difference is not None:
            difference_percent = (difference / planned_total) * Decimal('100')

        # Construir summary
        summary = {
            "planned_total": float(planned_total) if planned_total > 0 else None,
            "real_total": float(real_total),
            "difference": float(difference) if difference is not None else None,
            "difference_percent": float(difference_percent) if difference_percent is not None else None,
            "items_planned": items_planned,
            "items_purchased": items_purchased,
            "items_missing": items_missing,
            "items_extra": items_extra
        }

        # Salvar execução no banco
        execution = ShoppingListExecution(
            shopping_list_id=list_id,
            receipt_id=receipt_id,
            user_id=user_id,
            planned_total=planned_total if planned_total > 0 else None,
            real_total=real_total,
            difference=difference,
            difference_percent=difference_percent,
            summary={
                "summary": summary,
                "items": comparisons
            }
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        logger.info(f"Execução de sincronização salva: execution_id={execution.id}, planned_total={planned_total}, real_total={real_total}")

        # Criar notificações
        # Notificação de sincronização completa
        sync_notification = Notification(
            user_id=user_id,
            type="SYNC_COMPLETED",
            payload={
                **summary,
                "list_id": str(list_id),
                "receipt_id": str(receipt_id),
                "execution_id": str(execution.id)
            },
            is_read=False
        )
        db.add(sync_notification)

        # Notificação de alerta de preço (se diferença > 10%)
        if difference_percent and abs(difference_percent) > Decimal('10'):
            price_notification = Notification(
                user_id=user_id,
                type="PRICE_ALERT",
                payload={
                    **summary,
                    "list_id": str(list_id),
                    "receipt_id": str(receipt_id),
                    "execution_id": str(execution.id)
                },
                is_read=False
            )
            db.add(price_notification)
            logger.info(f"Notificação de alerta de preço criada: difference_percent={difference_percent}")

        # Notificação de itens faltantes
        if items_missing > 0:
            missing_notification = Notification(
                user_id=user_id,
                type="ITEM_MISSING",
                payload={
                    **summary,
                    "list_id": str(list_id),
                    "receipt_id": str(receipt_id),
                    "execution_id": str(execution.id),
                    "missing_count": items_missing
                },
                is_read=False
            )
            db.add(missing_notification)
            logger.info(f"Notificação de itens faltantes criada: items_missing={items_missing}")

        db.commit()

        return ShoppingListSyncResponse(
            list_id=list_id,
            receipt_id=receipt_id,
            summary=summary,
            items=[ItemComparisonResponse(**comp) for comp in comparisons],
            execution_id=execution.id,
            created_at=execution.created_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao sincronizar lista com nota: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao sincronizar lista com nota: {str(e)}"
        )


@router.get("/shopping-lists/{list_id}/executions")
async def list_shopping_list_executions(
    list_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Lista histórico de execuções de sincronização de uma lista de compras.
    
    Query params:
    - limit: Número máximo de resultados (padrão: 20, máximo: 100)
    - offset: Número de resultados para pular (padrão: 0)
    """
    try:
        # Verificar se a lista pertence ao usuário
        shopping_list = db.query(ShoppingList).filter(
            ShoppingList.id == list_id,
            ShoppingList.user_id == user_id
        ).first()

        if not shopping_list:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Lista de compras não encontrada ou não pertence ao usuário"
            )

        # Buscar execuções
        executions = db.query(ShoppingListExecution).filter(
            ShoppingListExecution.shopping_list_id == list_id,
            ShoppingListExecution.user_id == user_id
        ).order_by(ShoppingListExecution.created_at.desc()).limit(limit).offset(offset).all()

        result = []
        for exec in executions:
            result.append({
                "execution_id": exec.id,
                "created_at": exec.created_at,
                "planned_total": float(exec.planned_total) if exec.planned_total else None,
                "real_total": float(exec.real_total) if exec.real_total else None,
                "difference": float(exec.difference) if exec.difference else None,
                "difference_percent": float(exec.difference_percent) if exec.difference_percent else None,
                "receipt_id": exec.receipt_id
            })

        logger.info(f"Listando {len(result)} execuções para lista {list_id}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao listar execuções: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar execuções"
        )


@router.get("/shopping-lists/executions/{execution_id}/pdf")
async def get_execution_pdf(
    execution_id: UUID,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user)
):
    """
    Gera PDF de uma execução de sincronização.
    
    Retorna PDF como StreamingResponse.
    """
    try:
        # Buscar execução
        execution = db.query(ShoppingListExecution).filter(
            ShoppingListExecution.id == execution_id,
            ShoppingListExecution.user_id == user_id
        ).first()

        if not execution:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Execução não encontrada ou não pertence ao usuário"
            )

        # Gerar PDF
        pdf_bytes = generate_sync_pdf(execution)

        logger.info(f"PDF gerado para execução {execution_id}: {len(pdf_bytes)} bytes")

        # Retornar como StreamingResponse
        from io import BytesIO
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=relatorio_sincronizacao_{execution_id}.pdf"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar PDF: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar PDF: {str(e)}"
        )

