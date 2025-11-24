from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.example import Example
from app.schemas.example import ExampleCreate, ExampleUpdate, ExampleResponse
from app.services.example_service import ExampleService

router = APIRouter()


@router.get("/examples", response_model=List[ExampleResponse])
async def get_examples(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Lista todos os exemplos"""
    service = ExampleService(db)
    examples = service.get_all(skip=skip, limit=limit)
    return examples


@router.get("/examples/{example_id}", response_model=ExampleResponse)
async def get_example(
    example_id: int,
    db: Session = Depends(get_db)
):
    """Busca um exemplo por ID"""
    service = ExampleService(db)
    example = service.get_by_id(example_id)
    if not example:
        raise HTTPException(status_code=404, detail="Exemplo não encontrado")
    return example


@router.post("/examples", response_model=ExampleResponse, status_code=201)
async def create_example(
    example_data: ExampleCreate,
    db: Session = Depends(get_db)
):
    """Cria um novo exemplo"""
    service = ExampleService(db)
    example = service.create(example_data)
    return example


@router.put("/examples/{example_id}", response_model=ExampleResponse)
async def update_example(
    example_id: int,
    example_data: ExampleUpdate,
    db: Session = Depends(get_db)
):
    """Atualiza um exemplo"""
    service = ExampleService(db)
    example = service.update(example_id, example_data)
    if not example:
        raise HTTPException(status_code=404, detail="Exemplo não encontrado")
    return example


@router.delete("/examples/{example_id}", status_code=204)
async def delete_example(
    example_id: int,
    db: Session = Depends(get_db)
):
    """Deleta um exemplo"""
    service = ExampleService(db)
    success = service.delete(example_id)
    if not success:
        raise HTTPException(status_code=404, detail="Exemplo não encontrado")

