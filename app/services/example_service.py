from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.example import Example
from app.schemas.example import ExampleCreate, ExampleUpdate


class ExampleService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self, skip: int = 0, limit: int = 100) -> List[Example]:
        """Retorna todos os exemplos"""
        return self.db.query(Example).offset(skip).limit(limit).all()

    def get_by_id(self, example_id: int) -> Optional[Example]:
        """Retorna um exemplo por ID"""
        return self.db.query(Example).filter(Example.id == example_id).first()

    def create(self, example_data: ExampleCreate) -> Example:
        """Cria um novo exemplo"""
        db_example = Example(**example_data.model_dump())
        self.db.add(db_example)
        self.db.commit()
        self.db.refresh(db_example)
        return db_example

    def update(self, example_id: int, example_data: ExampleUpdate) -> Optional[Example]:
        """Atualiza um exemplo"""
        db_example = self.get_by_id(example_id)
        if not db_example:
            return None
        
        update_data = example_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_example, field, value)
        
        self.db.commit()
        self.db.refresh(db_example)
        return db_example

    def delete(self, example_id: int) -> bool:
        """Deleta um exemplo"""
        db_example = self.get_by_id(example_id)
        if not db_example:
            return False
        
        self.db.delete(db_example)
        self.db.commit()
        return True

