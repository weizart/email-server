"""
Mail Server module.

This module is part of the Personal Mail Server project.
"""

# mail_server.py
import asyncio
import logging
import ssl
import os
import base64
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import SMTP, Envelope
from aiohttp import web
from smtp_handler import SMTPHandler
from imap_handler import IMAPProtocol, create_imap_server
from web_admin import WebAdmin
from web_client import WebClient
from config import MailServerConfig
from storage import MailStorage
from database import AsyncSessionLocal, init_db
from models import User, SessionLocal
from sqlalchemy.future import select
import bcrypt
from aioimaplib import aioimaplib

logger = logging.getLogger(__name__)


class CustomSMTP(SMTP):
    """自定义的 SMTP 类，用于处理 AUTH 认证和验证会话状态。"""

    def __init__(self, *args, db_session_factory=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_session_factory = db_session_factory
        logger.debug(f"New CustomSMTP instance created: {id(self)}")

    async def handle_AUTH(self, server, session, envelope, arg):
        """
        处理 AUTH 命令，支持 LOGIN 和 PLAIN 机制。
        """
        logger.debug(f"handle_AUTH called with arg: {arg}")

        if arg is None:
            # 客户端只发送了 AUTH 命令，未指定机制
            return '501 Syntax error in parameters or arguments'

        try:
            # 分离机制名称和参数
            parts = arg.strip().split(' ', 1)
            mechanism = parts[0].upper()
            credentials = parts[1] if len(parts) > 1 else None
        except Exception as e:
            logger.error(f"Error parsing AUTH argument: {e}")
            return '501 Syntax error in parameters or arguments'

        if mechanism == 'PLAIN':
            return await self.handle_AUTH_PLAIN(session, credentials)
        elif mechanism == 'LOGIN':
            return await self.handle_AUTH_LOGIN(session, credentials)
        else:
            return f'504 Unrecognized authentication type {mechanism}'

    async def handle_AUTH_PLAIN(self, session, credentials):
        """
        处理 AUTH PLAIN 机制。
        """
        logger.debug("Handling AUTH PLAIN")

        if not credentials:
            # 客户端需要先发送 credentials
            # 通常，客户端会发送 credentials 一次性
            return '334 '  # 空的挑战，表示继续发送

        try:
            decoded = base64.b64decode(credentials).decode('utf-8')
            parts = decoded.split('\0')
            if len(parts) != 3:
                raise ValueError("Invalid AUTH PLAIN format")
            _, username, password = parts
            logger.debug(f"Received AUTH PLAIN credentials: username={username}")
        except Exception as e:
            logger.error(f"Error decoding AUTH PLAIN credentials: {e}")
            return '535 5.7.8 Authentication credentials invalid'

        # 验证用户名和密码
        auth_result = await self.authenticate_user(username, password)
        if auth_result:
            session.authenticated = True
            session.username = username
            logger.info(f"AUTH PLAIN authenticated user: {username}")
            return '235 2.7.0 Authentication successful'
        else:
            logger.warning(f"AUTH PLAIN authentication failed for user: {username}")
            return '535 5.7.8 Authentication credentials invalid'

    async def handle_AUTH_LOGIN(self, session, credentials):
        """
        处理 AUTH LOGIN 机制。
        """
        logger.debug("Handling AUTH LOGIN")

        if not hasattr(session, 'auth_login_stage'):
            session.auth_login_stage = 'username'

        if session.auth_login_stage == 'username':
            if not credentials:
                # 客户端需要先发送用户名
                return '334 VXNlcm5hbWU6'  # Base64('Username:')
            try:
                decoded_username = base64.b64decode(credentials).decode('utf-8')
                session.auth_username = decoded_username
                logger.debug(f"Received AUTH LOGIN username: {decoded_username}")
            except Exception as e:
                logger.error(f"Error decoding AUTH LOGIN username: {e}")
                session.auth_login_stage = None
                return '535 5.7.8 Authentication credentials invalid'
            session.auth_login_stage = 'password'
            return '334 UGFzc3dvcmQ6'  # Base64('Password:')

        elif session.auth_login_stage == 'password':
            if not credentials:
                # 客户端需要发送密码
                return '334 '  # 空的挑战，表示继续发送
            try:
                decoded_password = base64.b64decode(credentials).decode('utf-8')
                username = session.auth_username
                logger.debug(f"Received AUTH LOGIN password for user: {username}")
            except Exception as e:
                logger.error(f"Error decoding AUTH LOGIN password: {e}")
                session.auth_login_stage = None
                return '535 5.7.8 Authentication credentials invalid'

            # 验证用户名和密码
            auth_result = await self.authenticate_user(username, decoded_password)
            if auth_result:
                session.authenticated = True
                session.username = username
                logger.info(f"AUTH LOGIN authenticated user: {username}")
                session.auth_login_stage = None
                return '235 2.7.0 Authentication successful'
            else:
                logger.warning(f"AUTH LOGIN authentication failed for user: {username}")
                session.auth_login_stage = None
                return '535 5.7.8 Authentication credentials invalid'

        else:
            logger.error("Invalid AUTH LOGIN stage")
            session.auth_login_stage = None
            return '500 5.5.2 Authentication failed'

    async def authenticate_user(self, username, password):
        """
        验证用户凭证。
        """
        logger.debug(f"Authenticating user: {username}")
        try:
            async with self.db_session_factory() as db_session:
                result = await db_session.execute(
                    select(User).where(User.email == username)
                )
                user = result.scalar_one_or_none()
                if user and bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
                    return True
                else:
                    return False
        except Exception as e:
            logger.error(f"Error during user authentication: {e}")
            return False

    async def handle_MAIL(self, server, session, envelope, address, mail_options):
        """
        覆盖 handle_MAIL，用于在收到 MAIL FROM 命令时先检查会话是否已经成功认证。
        如果未认证，则返回 530，拒绝接收邮件。
        """
        logger.debug(f"handle_MAIL called: authenticated={getattr(session, 'authenticated', False)}")
        if not getattr(session, 'authenticated', False):
            logger.warning("MAIL FROM command received without authentication")
            return '530 5.7.0 Authentication required'
        # 如果已经认证，通过 super() 调用默认处理
        return await super().handle_MAIL(server, session, envelope, address, mail_options)

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        """
        覆盖 handle_RCPT，用于在收到 RCPT TO 命令时检查会话是否已经认证。
        """
        logger.debug(f"handle_RCPT called: authenticated={getattr(session, 'authenticated', False)}")
        if not getattr(session, 'authenticated', False):
            logger.warning("RCPT TO command received without authentication")
            return '530 5.7.0 Authentication required'
        return await super().handle_RCPT(server, session, envelope, address, rcpt_options)

    async def handle_DATA(self, server, session, envelope):
        """
        覆盖 handle_DATA，用于在收到 DATA 命令时检查会话是否已经认证。
        """
        logger.debug(f"handle_DATA called: authenticated={getattr(session, 'authenticated', False)}")
        if not getattr(session, 'authenticated', False):
            logger.warning("DATA command received without authentication")
            return '530 5.7.0 Authentication required'
        return await super().handle_DATA(server, session, envelope)


class MailServer:
    def __init__(self, config: MailServerConfig):
        self.config = config
        self.storage = MailStorage(config)
        self.db_session_factory = AsyncSessionLocal
        self.web_admin = None
        self.web_client = None
        self.web_app = None
        self.smtp_controller = None
        self.imap_server = None
        self.runner = None

    async def setup(self):
        try:
            # Initialize the database
            await init_db()

            # Initialize the Web admin interface and client
            self.web_admin = WebAdmin(self.config, self.storage, self.db_session_factory)
            self.web_client = WebClient(self.config, self.storage, self.db_session_factory)
            
            # Create a single web application
            self.web_app = web.Application()
            
            # Create sub-applications
            admin_app = web.Application(middlewares=[self.web_admin.auth_middleware])
            client_app = web.Application(middlewares=[self.web_client.auth_middleware])
            
            # Set up admin routes
            admin_app.router.add_get('/login', self.web_admin.login_page)
            admin_app.router.add_post('/login', self.web_admin.login)
            admin_app.router.add_get('/mailboxes', self.web_admin.mailboxes_page)
            admin_app.router.add_get('/mailboxes/list', self.web_admin.list_mailboxes)
            admin_app.router.add_post('/mailboxes/create', self.web_admin.create_mailbox)
            admin_app.router.add_post('/mailboxes/delete', self.web_admin.delete_mailbox)
            
            # Set up client routes
            client_app.router.add_get('/login', self.web_client.login_page)
            client_app.router.add_post('/login', self.web_client.login)
            client_app.router.add_get('/mail', self.web_client.mail_page)
            client_app.router.add_get('/mails', self.web_client.get_mails)
            client_app.router.add_get('/mails/{mail_id}', self.web_client.get_mail)
            client_app.router.add_post('/mails', self.web_client.send_mail)
            
            # Add sub-applications to main application
            self.web_app.add_subapp('/admin/', admin_app)
            self.web_app.add_subapp('/client/', client_app)
            
            # Add redirect from root to client login
            async def redirect_to_client(request):
                raise web.HTTPFound('/client/login')
            
            self.web_app.router.add_get('/', redirect_to_client)

            logger.info('Mail server setup completed successfully')
        except Exception as e:
            logger.error(f'Setup failed: {str(e)}')
            raise

    async def start(self):
        try:
            # Start the SMTP server
            smtp_handler = SMTPHandler(self.config, self.storage, db_session_factory=self.db_session_factory)

            # 获取 SSL 上下文（如果使用 TLS）
            ssl_context = self._get_ssl_context() if self.config.use_ssl else None

            self.smtp_controller = Controller(
                handler=None,  # Handler 将在 factory 中提供
                hostname=self.config.smtp_host,
                port=self.config.smtp_port,
                auth_required=True,       # 标记需要认证
                auth_require_tls=False,   # 需要 TLS/SSL 可改为 True
                ssl_context=ssl_context,  # 如果使用 TLS，就把 ssl_context 传进来
                server_hostname=self.config.smtp_host,
                require_starttls=self.config.require_starttls  # 根据配置是否要求 STARTTLS
            )
            # 提供一个自定义 factory 来创建我们的 CustomSMTP 实例
            self.smtp_controller.factory = lambda: CustomSMTP(
                handler=smtp_handler,
                db_session_factory=self.db_session_factory
            )

            self.smtp_controller.start()
            logger.info(f'SMTP server started at {self.config.smtp_host}:{self.config.smtp_port}')

            # Start the IMAP server
            imap_factory = create_imap_server(self.config, self.storage, self.db_session_factory)
            self.imap_server = await asyncio.start_server(
                imap_factory,
                host=self.config.imap_host,
                port=self.config.imap_port,
                ssl=ssl_context
            )
            logger.info(f'IMAP server started at {self.config.imap_host}:{self.config.imap_port}')

            # Start the Web admin interface
            self.runner = web.AppRunner(self.web_app)
            await self.runner.setup()
            site = web.TCPSite(
                self.runner,
                self.config.web_host,
                self.config.web_port,
                ssl_context=ssl_context
            )
            await site.start()
            logger.info(f'Web admin interface started at {self.config.web_host}:{self.config.web_port}')

        except Exception as e:
            logger.error(f'Failed to start services: {str(e)}')
            await self.stop()
            raise

    def _get_ssl_context(self):
        try:
            if not (os.path.exists(self.config.ssl_cert) and os.path.exists(self.config.ssl_key)):
                logger.warning('SSL certificate or key file does not exist, SSL will not be used')
                return None

            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(self.config.ssl_cert, self.config.ssl_key)
            return ssl_context
        except Exception as e:
            logger.error(f'SSL configuration error: {str(e)}')
            return None

    async def stop(self):
        try:
            # Stop the SMTP server
            if self.smtp_controller:
                self.smtp_controller.stop()
                logger.info('SMTP server stopped')

            # Stop the IMAP server
            if self.imap_server:
                self.imap_server.close()
                await self.imap_server.wait_closed()
                logger.info('IMAP server stopped')

            # Stop the Web admin interface
            if self.runner:
                await self.runner.cleanup()
                logger.info('Web admin interface stopped')

        except Exception as e:
            logger.error(f'Error while stopping services: {str(e)}')
        finally:
            logger.info('Mail server has been fully stopped')
