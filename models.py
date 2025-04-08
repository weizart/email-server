"""
Models module.

This module is part of the Personal Mail Server project.
"""

# models.py
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, DateTime, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    email = Column(String, primary_key=True, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    folders = relationship("Folder", back_populates="user", cascade="all, delete-orphan")
    emails_received = relationship("Email", back_populates="recipient_user", foreign_keys='Email.recipient')
    emails_sent = relationship("Email", back_populates="sender_user", foreign_keys='Email.sender')

class Folder(Base):
    __tablename__ = 'folders'
    __table_args__ = (UniqueConstraint('user_email', 'name', name='_user_folder_uc'),)
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_email = Column(String, ForeignKey('users.email'), nullable=False)
    name = Column(String, nullable=False)
    
    user = relationship("User", back_populates="folders")
    emails = relationship("Email", back_populates="folder")

class Email(Base):
    __tablename__ = 'emails'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    recipient = Column(String, ForeignKey('users.email'), nullable=False, index=True)
    sender = Column(String, ForeignKey('users.email'), nullable=False)
    subject = Column(String)
    content = Column(Text)  # 存储加密后的内容
    flags = Column(String, default='')
    folder_id = Column(Integer, ForeignKey('folders.id'), default=None)
    received_at = Column(DateTime, default=datetime.datetime.utcnow)
    uid = Column(Integer, unique=True, index=True)
    
    recipient_user = relationship("User", back_populates="emails_received", foreign_keys=[recipient])
    sender_user = relationship("User", back_populates="emails_sent", foreign_keys=[sender])
    folder = relationship("Folder", back_populates="emails")
