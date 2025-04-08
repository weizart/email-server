"""
SMTP Handler module.

This module is part of the Personal Mail Server project.
"""

# smtp_handler.py
import logging
from aiosmtpd.handlers import AsyncMessage
from email.message import EmailMessage

logger = logging.getLogger(__name__)

class SMTPHandler(AsyncMessage):
    def __init__(self, config, storage, db_session_factory):
        super().__init__()
        self.config = config
        self.storage = storage
        self.db_session_factory = db_session_factory

    async def handle_MAIL(self, server, session, envelope, address, mail_options):
        if not getattr(server, 'authenticated', False):
            return '530 5.7.0 Authentication required'
        envelope.mail_from = address
        return '250 OK'

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if not getattr(server, 'authenticated', False):
            return '530 5.7.0 Authentication required'
        # 验证收件人域名
        if not address.endswith(f"@{self.config.domain}"):
            logger.warning(f"拒绝接受邮件: 无效的收件人域名 {address}")
            return '550 Invalid recipient domain'
        envelope.rcpt_tos.append(address)
        return '250 OK'

    async def handle_DATA(self, server, session, envelope):
        if not getattr(server, 'authenticated', False):
            logger.warning("未通过认证，拒绝接受邮件数据")
            return '530 5.7.0 Authentication required'
        return await super().handle_DATA(server, session, envelope)

    async def handle_message(self, message: EmailMessage):
        # 处理邮件消息，保存到存储中
        try:
            mail_from = message['From']
            rcpt_tos = message.get_all('To', [])
            if isinstance(rcpt_tos, str):
                rcpt_tos = [rcpt_tos]
            data = message.as_bytes()

            # 保存每个收件人的邮件
            async with self.db_session_factory() as db_session:
                for rcpt in rcpt_tos:
                    if not rcpt.endswith(f"@{self.config.domain}"):
                        logger.warning(f"拒绝接受邮件: 无效的收件人域名 {rcpt}")
                        continue
                    uid = await self.storage.save_email(db_session, rcpt, mail_from, data)
                    logger.info(f'邮件已保存: From {mail_from} to {rcpt} (UID: {uid})')

        except Exception as e:
            logger.error(f'处理邮件时发生错误: {str(e)}')