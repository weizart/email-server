"""
Config module.

This module is part of the Personal Mail Server project.
"""

# config.py
import os
from cryptography.fernet import Fernet

class MailServerConfig:
    def __init__(self):
        self.domain = "weizart.com"
        self.smtp_host = "0.0.0.0"
        self.smtp_port = 2525
        self.imap_host = "0.0.0.0"
        self.imap_port = 1430
        self.web_host = "0.0.0.0"
        self.web_port = 3000
        self.admin_user = "admin"
        self.admin_password = "admin123"  # 请修改为安全的密码
        self.ssl_cert = "cert.pem"
        self.ssl_key = "key.pem"
        self.storage_path = "mailstore"
        self.db_path = "mailserver.db"
        self.redis_url = "redis://localhost"
        self.use_ssl = False
        self.require_starttls = False
        
        # 加密密钥
        self.secret_key = Fernet.generate_key()
        self.cipher_suite = Fernet(self.secret_key)
        
        # JWT 密钥
        self.jwt_secret = "your-secret-key"  # 请更改为安全的密钥
