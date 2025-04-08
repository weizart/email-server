"""
Models module.

This module is part of the Personal Mail Server project.
"""

# models.py
from sqlalchemy import (
    Column, Integer, String, Text, ForeignKey, DateTime, UniqueConstraint, Boolean, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime
import bcrypt

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    folders = relationship("Folder", back_populates="user", cascade="all, delete-orphan")
    emails_received = relationship("Email", back_populates="recipient_user", 
                                 foreign_keys='Email.recipient',
                                 primaryjoin="User.email==Email.recipient")
    emails_sent = relationship("Email", back_populates="sender_user", 
                             foreign_keys='Email.sender',
                             primaryjoin="User.email==Email.sender")

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode('utf-8')
    
    def verify_password(self, password):
        return bcrypt.checkpw(password.encode(), self.password_hash.encode())

class Folder(Base):
    __tablename__ = 'folders'
    __table_args__ = (UniqueConstraint('user_email', 'name', name='_user_folder_uc'),)
    
    id = Column(Integer, primary_key=True)
    user_email = Column(String, ForeignKey('users.email'))
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    user = relationship("User", back_populates="folders")
    emails = relationship("Email", back_populates="folder")

class Email(Base):
    __tablename__ = 'emails'
    
    id = Column(Integer, primary_key=True)
    sender = Column(String, ForeignKey('users.email'), nullable=False)
    recipient = Column(String, ForeignKey('users.email'), nullable=False)
    subject = Column(String)
    body = Column(String)
    folder_id = Column(Integer, ForeignKey('folders.id'))
    unread = Column(Boolean, default=True)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    
    recipient_user = relationship("User", back_populates="emails_received", foreign_keys=[recipient])
    sender_user = relationship("User", back_populates="emails_sent", foreign_keys=[sender])
    folder = relationship("Folder", back_populates="emails")

# 创建数据库引擎
engine = create_engine('sqlite:///mailserver.db')
SessionLocal = sessionmaker(bind=engine)

async def init_db():
    Base.metadata.create_all(engine)
    
    # 创建默认管理员账户
    async with SessionLocal() as session:
        admin = session.query(User).filter_by(email='admin@weizart.com').first()
        if not admin:
            admin = User(email='admin@weizart.com')
            admin.set_password('admin123')
            session.add(admin)
            session.commit()
