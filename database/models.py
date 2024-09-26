from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String)
    
    # Hinzugefügtes Attribut für Telegram-ID
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)

    transactions = relationship("Transaction", back_populates="owner")
    budgets = relationship("Budget", back_populates="owner")
    goals = relationship("Goal", back_populates="owner")

class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float)
    description = Column(String)
    date = Column(DateTime)
    user_id = Column(Integer, ForeignKey('users.id'))
    category = Column(String, index=True)
    subcategory = Column(String, index=True)
    currency = Column(String, index=True)
    type = Column(String, index=True)  # 'expense' oder 'income'

    owner = relationship("User", back_populates="transactions")

class Budget(Base):
    __tablename__ = 'budgets'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    limit = Column(Float)
    user_id = Column(Integer, ForeignKey('users.id'))
    year = Column(Integer)  # Neues Feld für das Jahr
    month = Column(Integer)  # Neues Feld für den Monat
    
    owner = relationship("User", back_populates="budgets")

class Goal(Base):
    __tablename__ = 'goals'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    target_amount = Column(Float)
    current_amount = Column(Float, default=0.0)
    user_id = Column(Integer, ForeignKey('users.id'))
    
    owner = relationship("User", back_populates="goals")