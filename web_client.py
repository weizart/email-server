import logging
from aiohttp import web
import jwt
from datetime import datetime, timedelta
from sqlalchemy.future import select
from models import User, Email, Folder
import json

logger = logging.getLogger(__name__)

class WebClient:
    def __init__(self, config, storage, session_factory):
        self.config = config
        self.storage = storage
        self.session_factory = session_factory
        self.jwt_secret = self.config.jwt_secret

    def _create_token(self, email: str) -> str:
        expiration = datetime.utcnow() + timedelta(hours=24)
        token = jwt.encode(
            payload={"email": email, "exp": expiration},
            key=self.jwt_secret,
            algorithm="HS256"
        )
        return token

    @web.middleware
    async def auth_middleware(self, request, handler):
        if request.path == '/login' and request.method in ['GET', 'POST']:
            return await handler(request)
        
        token = request.cookies.get('token')
        if not token:
            return web.HTTPFound('/login')
        
        try:
            decoded = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            request['user'] = decoded
            return await handler(request)
        except jwt.ExpiredSignatureError:
            return web.HTTPFound('/login')
        except jwt.InvalidTokenError:
            return web.HTTPFound('/login')

    async def login_page(self, request):
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>邮件登录 - weizart.com</title>
            <meta charset="UTF-8">
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 0;
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    background-color: #f5f5f5;
                }
                .login-form {
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    width: 100%;
                    max-width: 320px;
                }
                .login-form h2 {
                    margin: 0 0 1.5rem;
                    text-align: center;
                    color: #333;
                }
                input {
                    width: 100%;
                    padding: 0.75rem;
                    margin: 0.5rem 0;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    box-sizing: border-box;
                }
                button {
                    width: 100%;
                    padding: 0.75rem;
                    background: #007bff;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 1rem;
                    margin-top: 1rem;
                }
                button:hover {
                    background: #0056b3;
                }
                .error {
                    color: #dc3545;
                    margin-top: 0.5rem;
                    text-align: center;
                    display: none;
                }
            </style>
        </head>
        <body>
            <div class="login-form">
                <h2>邮件登录</h2>
                <form id="loginForm">
                    <input type="email" name="email" placeholder="邮箱地址" required>
                    <input type="password" name="password" placeholder="密码" required>
                    <div id="error" class="error"></div>
                    <button type="submit">登录</button>
                </form>
            </div>
            <script>
                document.getElementById('loginForm').onsubmit = async (e) => {
                    e.preventDefault();
                    const errorDiv = document.getElementById('error');
                    const formData = new FormData(e.target);
                    
                    try {
                        const response = await fetch('/login', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                email: formData.get('email'),
                                password: formData.get('password')
                            })
                        });
                        
                        if (response.ok) {
                            window.location.href = '/mail';
                        } else {
                            const data = await response.json();
                            errorDiv.textContent = data.error || '登录失败';
                            errorDiv.style.display = 'block';
                        }
                    } catch (error) {
                        errorDiv.textContent = '登录失败: ' + error.message;
                        errorDiv.style.display = 'block';
                    }
                };
            </script>
        </body>
        </html>
        """
        return web.Response(text=html_content, content_type='text/html')

    async def login(self, request):
        try:
            data = await request.json()
            email = data.get('email')
            password = data.get('password')
            
            if not email or not password:
                return web.json_response({"error": "邮箱和密码不能为空"}, status=400)

            async with self.session_factory() as session:
                result = await session.execute(
                    select(User).where(User.email == email)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    return web.json_response({"error": "邮箱或密码错误"}, status=401)

                if not user.verify_password(password):
                    return web.json_response({"error": "邮箱或密码错误"}, status=401)

                token = self._create_token(email)
                response = web.json_response({"message": "登录成功"})
                response.set_cookie('token', token, httponly=True, secure=False)
                return response
                
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return web.json_response({"error": "登录失败"}, status=500)

    async def mail_page(self, request):
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>邮件客户端 - weizart.com</title>
            <meta charset="UTF-8">
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 0;
                    padding: 0;
                    display: flex;
                    height: 100vh;
                }
                .sidebar {
                    width: 200px;
                    background: #f8f9fa;
                    padding: 1rem;
                    border-right: 1px solid #ddd;
                }
                .main-content {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                }
                .toolbar {
                    padding: 1rem;
                    background: #fff;
                    border-bottom: 1px solid #ddd;
                    display: flex;
                    gap: 1rem;
                }
                .mail-list {
                    flex: 1;
                    overflow-y: auto;
                    background: #fff;
                }
                .mail-item {
                    padding: 1rem;
                    border-bottom: 1px solid #eee;
                    cursor: pointer;
                }
                .mail-item:hover {
                    background: #f8f9fa;
                }
                .mail-item.unread {
                    font-weight: bold;
                }
                .mail-preview {
                    padding: 1rem;
                    background: #fff;
                    border-left: 1px solid #ddd;
                    width: 50%;
                }
                button {
                    padding: 0.5rem 1rem;
                    background: #007bff;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                }
                button:hover {
                    background: #0056b3;
                }
                .compose-btn {
                    background: #28a745;
                }
                .compose-btn:hover {
                    background: #218838;
                }
            </style>
        </head>
        <body>
            <div class="sidebar">
                <h3>文件夹</h3>
                <ul id="folders">
                    <li><a href="#" data-folder="INBOX">收件箱</a></li>
                    <li><a href="#" data-folder="SENT">已发送</a></li>
                    <li><a href="#" data-folder="DRAFT">草稿箱</a></li>
                    <li><a href="#" data-folder="TRASH">垃圾箱</a></li>
                </ul>
            </div>
            <div class="main-content">
                <div class="toolbar">
                    <button class="compose-btn" onclick="composeMail()">写邮件</button>
                    <button onclick="refreshMails()">刷新</button>
                </div>
                <div class="mail-list" id="mailList"></div>
            </div>
            <div class="mail-preview" id="mailPreview"></div>
            <script>
                let currentFolder = 'INBOX';
                
                async function loadMails() {
                    try {
                        const response = await fetch(`/mails?folder=${currentFolder}`);
                        const mails = await response.json();
                        
                        const mailList = document.getElementById('mailList');
                        mailList.innerHTML = '';
                        
                        mails.forEach(mail => {
                            const div = document.createElement('div');
                            div.className = `mail-item ${mail.unread ? 'unread' : ''}`;
                            div.innerHTML = `
                                <div>${mail.sender}</div>
                                <div>${mail.subject}</div>
                                <div>${new Date(mail.date).toLocaleString()}</div>
                            `;
                            div.onclick = () => showMail(mail.id);
                            mailList.appendChild(div);
                        });
                    } catch (error) {
                        console.error('Failed to load mails:', error);
                    }
                }
                
                async function showMail(mailId) {
                    try {
                        const response = await fetch(`/mails/${mailId}`);
                        const mail = await response.json();
                        
                        const preview = document.getElementById('mailPreview');
                        preview.innerHTML = `
                            <h2>${mail.subject}</h2>
                            <div>发件人: ${mail.sender}</div>
                            <div>收件人: ${mail.recipients.join(', ')}</div>
                            <div>时间: ${new Date(mail.date).toLocaleString()}</div>
                            <hr>
                            <div>${mail.body}</div>
                        `;
                    } catch (error) {
                        console.error('Failed to load mail:', error);
                    }
                }
                
                function composeMail() {
                    const preview = document.getElementById('mailPreview');
                    preview.innerHTML = `
                        <h2>写邮件</h2>
                        <form id="composeForm">
                            <div>
                                <label>收件人:</label>
                                <input type="text" name="recipients" required>
                            </div>
                            <div>
                                <label>主题:</label>
                                <input type="text" name="subject" required>
                            </div>
                            <div>
                                <label>内容:</label>
                                <textarea name="body" rows="10" required></textarea>
                            </div>
                            <button type="submit">发送</button>
                        </form>
                    `;
                    
                    document.getElementById('composeForm').onsubmit = async (e) => {
                        e.preventDefault();
                        const formData = new FormData(e.target);
                        
                        try {
                            const response = await fetch('/mails', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json'
                                },
                                body: JSON.stringify({
                                    recipients: formData.get('recipients').split(',').map(r => r.trim()),
                                    subject: formData.get('subject'),
                                    body: formData.get('body')
                                })
                            });
                            
                            if (response.ok) {
                                alert('发送成功');
                                loadMails();
                            } else {
                                alert('发送失败');
                            }
                        } catch (error) {
                            console.error('Failed to send mail:', error);
                            alert('发送失败');
                        }
                    };
                }
                
                function refreshMails() {
                    loadMails();
                }
                
                // 初始加载
                loadMails();
                
                // 每30秒自动刷新
                setInterval(loadMails, 30000);
            </script>
        </body>
        </html>
        """
        return web.Response(text=html_content, content_type='text/html')

    async def get_mails(self, request):
        try:
            folder = request.query.get('folder', 'INBOX')
            async with self.session_factory() as session:
                result = await session.execute(
                    select(Email).where(
                        Email.folder == folder,
                        Email.recipient == request['user']['email']
                    ).order_by(Email.date.desc())
                )
                mails = result.scalars().all()
                
                return web.json_response([
                    {
                        "id": mail.id,
                        "sender": mail.sender,
                        "subject": mail.subject,
                        "date": mail.date.isoformat(),
                        "unread": mail.unread
                    }
                    for mail in mails
                ])
        except Exception as e:
            logger.error(f"Failed to get mails: {str(e)}")
            return web.json_response({"error": "获取邮件失败"}, status=500)

    async def get_mail(self, request):
        try:
            mail_id = int(request.match_info['mail_id'])
            async with self.session_factory() as session:
                result = await session.execute(
                    select(Email).where(Email.id == mail_id)
                )
                mail = result.scalar_one_or_none()
                
                if not mail:
                    return web.json_response({"error": "邮件不存在"}, status=404)
                
                # 标记为已读
                mail.unread = False
                await session.commit()
                
                return web.json_response({
                    "id": mail.id,
                    "sender": mail.sender,
                    "recipients": [mail.recipient],
                    "subject": mail.subject,
                    "body": mail.body,
                    "date": mail.date.isoformat()
                })
        except Exception as e:
            logger.error(f"Failed to get mail: {str(e)}")
            return web.json_response({"error": "获取邮件失败"}, status=500)

    async def send_mail(self, request):
        try:
            data = await request.json()
            recipients = data.get('recipients', [])
            subject = data.get('subject', '')
            body = data.get('body', '')
            
            if not recipients or not subject or not body:
                return web.json_response({"error": "缺少必要参数"}, status=400)
            
            async with self.session_factory() as session:
                for recipient in recipients:
                    mail = Email(
                        sender=request['user']['email'],
                        recipient=recipient,
                        subject=subject,
                        body=body,
                        folder='SENT',
                        unread=False
                    )
                    session.add(mail)
                
                await session.commit()
                return web.json_response({"message": "发送成功"})
        except Exception as e:
            logger.error(f"Failed to send mail: {str(e)}")
            return web.json_response({"error": "发送失败"}, status=500)

    async def setup(self):
        self.web_app = web.Application(middlewares=[self.auth_middleware])
        
        # 设置路由
        self.web_app.router.add_get('/login', self.login_page)
        self.web_app.router.add_post('/login', self.login)
        self.web_app.router.add_get('/mail', self.mail_page)
        self.web_app.router.add_get('/mails', self.get_mails)
        self.web_app.router.add_get('/mails/{mail_id}', self.get_mail)
        self.web_app.router.add_post('/mails', self.send_mail)
        
        return self.web_app 