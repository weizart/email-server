"""
Storage module.

This module is part of the Personal Mail Server project.
"""

# storage.py
from models import User, Email, Folder
from sqlalchemy.future import select
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict
from cryptography.fernet import Fernet
import datetime
from email import message_from_bytes

class MailStorage:
    def __init__(self, config):
        self.config = config
        # 假设config已经包含cipher_suite等属性

    async def save_email(self, session: AsyncSession, recipient: str, sender: str, email_data: bytes, folder: str = 'INBOX') -> int:
        email_msg = message_from_bytes(email_data)
        subject = email_msg.get('subject', '')
        
        # 加密邮件内容
        encrypted_content = self.config.cipher_suite.encrypt(email_data).decode('utf-8')
        
        # 获取或创建文件夹
        result = await session.execute(
            select(Folder).where(Folder.user_email == recipient, Folder.name == folder)
        )
        folder_obj = result.scalar_one_or_none()
        if not folder_obj:
            folder_obj = Folder(user_email=recipient, name=folder)
            session.add(folder_obj)
            await session.flush()  # 获取folder_obj.id
        
        # 创建邮件
        new_email = Email(
            recipient=recipient,
            sender=sender,
            subject=subject,
            content=encrypted_content,
            folder=folder_obj,
            received_at=datetime.datetime.utcnow()
        )
        session.add(new_email)
        await session.flush()  # 获取new_email.id
        
        # 生成UID
        new_email.uid = new_email.id + 1000  # 确保UID从1000开始
        
        await session.commit()
        return new_email.uid

    async def get_emails(self, session: AsyncSession, email: str, folder: str = 'INBOX') -> List[Dict]:
        result = await session.execute(
            select(Email).join(Folder).where(
                Email.recipient == email,
                Folder.name == folder
            ).order_by(Email.received_at.desc())
        )
        emails = result.scalars().all()
        return [
            {
                'id': email.id,
                'uid': email.uid,
                'sender': email.sender,
                'subject': email.subject,
                'content': self.config.cipher_suite.decrypt(email.content.encode('utf-8')),
                'flags': email.flags,
                'received_at': email.received_at
            }
            for email in emails
        ]

    async def update_flags(self, session: AsyncSession, email_id: int, flags: str):
        await session.execute(
            update(Email).where(Email.id == email_id).values(flags=flags)
        )
        await session.commit()
