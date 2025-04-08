"""
Main module.

This module is part of the Personal Mail Server project.
"""

# main.py
import asyncio
import logging
from mail_server import MailServer
from config import MailServerConfig
from web_client import WebClient

# 配置日志到文件和控制台
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.FileHandler("mailserver.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main():
    config = MailServerConfig()
    server = MailServer(config)
    
    try:
        await server.setup()
        
        # 初始化邮件客户端
        web_client = WebClient(config, server.storage, server.db_session_factory)
        web_app = await web_client.setup()
        
        # 启动Web服务器
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, config.web_host, config.web_port)
        await site.start()
        
        # 启动邮件服务器
        await server.start()
        
        print(f"""
邮件服务器配置信息:
域名: {config.domain}
SMTP服务器: {config.smtp_host}:{config.smtp_port}
IMAP服务器: {config.imap_host}:{config.imap_port}
Web邮件客户端: http://{config.web_host}:{config.web_port}/login

您可以使用以下设置配置邮件客户端:
- 邮箱地址: example@{config.domain}
- SMTP服务器: {config.smtp_host}
- SMTP端口: {config.smtp_port}
- IMAP服务器: {config.imap_host}
- IMAP端口: {config.imap_port}
""")
        
        # 保持服务器运行
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在停止服务器...")
        await server.stop()
    except Exception as e:
        logger.error(f'服务器运行时发生错误: {str(e)}')
        await server.stop()

if __name__ == '__main__':
    asyncio.run(main())
