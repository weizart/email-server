# web_admin.py
import logging
from aiohttp import web
import jwt
from datetime import datetime, timedelta
import bcrypt
from sqlalchemy.exc import IntegrityError
from models import User, Folder
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

class WebAdmin:
    def __init__(self, config, storage, session_factory):
        self.config = config
        self.storage = storage
        self.session_factory = session_factory
        self.jwt_secret = self.config.jwt_secret
        logger.info("WebAdmin initialized with config domain: %s", self.config.domain)

    def _create_token(self, username: str) -> str:
        try:
            expiration = datetime.utcnow() + timedelta(hours=24)
            token = jwt.encode(
                payload={"user": username, "exp": expiration},
                key=self.jwt_secret,
                algorithm="HS256"
            )
            logger.info("Token created successfully for user: %s", username)
            return token
        except Exception as e:
            logger.error("Token creation failed: %s", str(e))
            raise

    @web.middleware
    async def auth_middleware(self, request, handler):
        logger.info("Auth middleware processing request: %s %s", request.method, request.path)
        
        # 不需要认证的路径
        if request.path == '/admin/login' and request.method in ['GET', 'POST']:
            logger.info("Skipping auth for login request")
            return await handler(request)
        
        if request.path == '/favicon.ico':
            logger.info("Skipping auth for favicon")
            return await handler(request)
        
        # 获取并验证token
        token = request.cookies.get('token')

        logger.info("Received token from cookie: %s", token[:20] + '...' if token else 'None')
        
        if not token:
            logger.warning("No token provided in cookie")
            return web.json_response({"error": "未授权"}, status=401)
        
        try:
            decoded = jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            logger.info("Token decoded successfully for user: %s", decoded.get('user'))
            request['user'] = decoded
            return await handler(request)
        except jwt.ExpiredSignatureError:
            logger.error("Token expired")
            return web.json_response({"error": "令牌已过期"}, status=401)
        except jwt.InvalidTokenError as e:
            logger.error("Invalid token: %s", str(e))
            return web.json_response({"error": "无效的令牌"}, status=401)
        except Exception as e:
            logger.error("Unexpected error in auth middleware: %s", str(e))
            return web.json_response({"error": "认证失败"}, status=401)

    async def login_page(self, request):
        logger.info("Serving login page")
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Mail Server Admin Login</title>
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
                <h2>管理员登录</h2>
                <form id="loginForm">
                    <input type="text" name="username" placeholder="用户名" required>
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
                        console.log('Attempting login...');
                        const response = await fetch('/admin/login', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                username: formData.get('username'),
                                password: formData.get('password')
                            })
                        });
                        
                        if (response.ok) {
                            const data = await response.json();
                            console.log('Login successful, redirecting...');
                            window.location.href = data.redirect || '/admin/mailboxes';
                        } else {
                            const data = await response.json();
                            console.error('Login failed:', data.error);
                            errorDiv.textContent = data.error || '登录失败';
                            errorDiv.style.display = 'block';
                        }
                    } catch (error) {
                        console.error('Login error:', error);
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
            username = data.get('username')
            password = data.get('password')
            
            logger.info("Login attempt for username: %s", username)

            if not username or not password:
                logger.warning("Login attempt with missing credentials")
                return web.json_response({"error": "用户名和密码不能为空"}, status=400)

            if username != self.config.admin_user or password != self.config.admin_password:
                logger.warning("Failed login attempt for username: %s", username)
                return web.json_response({"error": "用户名或密码错误"}, status=401)

            token = self._create_token(username)
            logger.info("Successful login for username: %s", username)
            response = web.json_response({"message": "登录成功", "redirect": "/admin/mailboxes"})
            response.set_cookie(
                'token', token, 
                max_age=24*3600,
                httponly=True,
                secure=False,
                samesite='Lax',
                path='/'
            )
            return response
            
        except Exception as e:
            logger.error("Login error: %s", str(e))
            return web.json_response({"error": "登录失败"}, status=500)

    async def mailboxes_page(self, request):
        logger.info("Serving mailboxes page")
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>邮箱管理 - weizart.com</title>
            <meta charset="UTF-8">
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }
                .container {
                    max-width: 800px;
                    margin: 0 auto;
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }
                th, td {
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }
                th {
                    background-color: #f8f9fa;
                }
                .actions {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }
                button {
                    padding: 8px 16px;
                    background: #007bff;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                }
                button:hover {
                    background: #0056b3;
                }
                .delete-btn {
                    background: #dc3545;
                }
                .delete-btn:hover {
                    background: #c82333;
                }
                .refresh-btn {
                    background: #28a745;
                }
                .refresh-btn:hover {
                    background: #218838;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="actions">
                    <h2>邮箱管理</h2>
                    <div>
                        <button class="refresh-btn" onclick="loadMailboxes()">刷新列表</button>
                        <button onclick="createMailbox()">创建邮箱</button>
                    </div>
                </div>
                <table id="mailboxTable">
                    <thead>
                        <tr>
                            <th>邮箱地址</th>
                            <th>创建时间</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
            <script>
                async function loadMailboxes() {
                    try {
                        console.log('Loading mailboxes...');
                        const response = await fetch('/admin/mailboxes/list', {
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            credentials: 'include'
                        });
                        
                        if (!response.ok) {
                            if (response.status === 401) {
                                console.log('Unauthorized, redirecting to login...');
                                window.location.href = '/admin/login';
                            }
                            throw new Error(`HTTP error! status: ${response.status}`);
                        }
                        
                        const data = await response.json();
                        console.log('Mailboxes data:', data);
                        
                        const tbody = document.querySelector('#mailboxTable tbody');
                        tbody.innerHTML = '';
                        
                        data.mailboxes.forEach(mailbox => {
                            const tr = document.createElement('tr');
                            tr.innerHTML = `
                                <td>${mailbox.email}</td>
                                <td>${new Date(mailbox.created_at).toLocaleString()}</td>
                                <td>
                                    <button class="delete-btn" onclick="deleteMailbox('${mailbox.email}')">
                                        删除
                                    </button>
                                </td>
                            `;
                            tbody.appendChild(tr);
                        });
                    } catch (error) {
                        console.error('Failed to load mailboxes:', error);
                        alert('加载邮箱列表失败: ' + error.message);
                    }
                }

                async function createMailbox() {
                    const email = prompt('请输入邮箱地址（@weizart.com）:');
                    if (!email) return;
                    
                    if (!email.endsWith('@weizart.com')) {
                        alert('邮箱地址必须以@weizart.com结尾');
                        return;
                    }
                    
                    const password = prompt('请输入密码:');
                    if (!password) return;

                    try {
                        const response = await fetch('/admin/mailboxes/create', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            credentials: 'include',
                            body: JSON.stringify({ email, password })
                        });
                        
                        const data = await response.json();
                        if (response.ok) {
                            alert('创建成功');
                            loadMailboxes();  // 创建成功后刷新列表
                        } else {
                            alert(data.error || '创建失败');
                        }
                    } catch (error) {
                        console.error('Failed to create mailbox:', error);
                        alert('创建失败: ' + error.message);
                    }
                }

                async function deleteMailbox(email) {
                    if (!confirm(`确定要删除邮箱 ${email} 吗？`)) return;

                    try {
                        const response = await fetch('/admin/mailboxes/delete', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            credentials: 'include',
                            body: JSON.stringify({ email })
                        });
                        
                        const data = await response.json();
                        if (response.ok) {
                            alert('删除成功');
                            loadMailboxes();  // 删除成功后刷新列表
                        } else {
                            alert(data.error || '删除失败');
                        }
                    } catch (error) {
                        console.error('Failed to delete mailbox:', error);
                        alert('删除失败: ' + error.message);
                    }
                }

                // 初始加载
                loadMailboxes();
                
                // 每30秒自动刷新一次
                setInterval(loadMailboxes, 30000);
            </script>
        </body>
        </html>
        """
        return web.Response(text=html_content, content_type='text/html')

    async def list_mailboxes(self, request):
        try:
            logger.info("Attempting to list mailboxes")
            async with self.session_factory() as session:
                result = await session.execute(
                    select(User.email, User.created_at).order_by(User.created_at.desc())
                )
                users = result.all()
                logger.info("Found %d mailboxes", len(users))

            mailboxes = [
                {
                    "email": user.email,
                    "created_at": user.created_at.isoformat() if user.created_at else None
                } 
                for user in users
            ]
            return web.json_response({"mailboxes": mailboxes})
        except Exception as e:
            logger.error("Failed to list mailboxes: %s", str(e))
            return web.json_response({"error": "获取邮箱列表失败"}, status=500)

    async def create_mailbox(self, request):
        try:
            data = await request.json()
            email = data.get('email')
            password = data.get('password')
            
            logger.info("Attempting to create mailbox: %s", email)

            if not email or not password:
                logger.warning("Missing required parameters for mailbox creation")
                return web.json_response({"error": "缺少必要参数"}, status=400)

            if not email.endswith(f"@{self.config.domain}"):
                logger.warning("Invalid email domain: %s", email)
                return web.json_response({"error": f"无效的邮箱域名，必须使用@{self.config.domain}"}, status=400)

            # 创建用户
            password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode('utf-8')

            async with self.session_factory() as session:
                user = User(email=email, password_hash=password_hash)
                session.add(user)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    logger.warning("Mailbox already exists: %s", email)
                    return web.json_response({"error": "邮箱已存在"}, status=400)

                # 创建默认文件夹
                default_folders = ['INBOX', 'Sent', 'Trash', 'Drafts', 'Spam']
                folders = [Folder(user_email=email, name=folder) for folder in default_folders]
                session.add_all(folders)
                await session.commit()

            logger.info("Successfully created mailbox: %s", email)
            return web.json_response({"message": "邮箱创建成功"})
        except Exception as e:
            logger.error("Failed to create mailbox: %s", str(e))
            return web.json_response({"error": "创建邮箱失败"}, status=500)

    async def delete_mailbox(self, request):
        try:
            data = await request.json()
            email = data.get('email')
            
            logger.info("Attempting to delete mailbox: %s", email)

            if not email:
                logger.warning("Missing email address for deletion")
                return web.json_response({"error": "缺少邮箱地址"}, status=400)

            async with self.session_factory() as session:
                result = await session.execute(
                    select(User).where(User.email == email)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    logger.warning("Mailbox not found for deletion: %s", email)
                    return web.json_response({"error": "邮箱不存在"}, status=404)

                # 删除相关文件夹和邮件（如果有相关联的删除逻辑，需要实现）
                await session.delete(user)
                await session.commit()

            logger.info("Successfully deleted mailbox: %s", email)
            return web.json_response({"message": "邮箱删除成功"})
        except Exception as e:
            logger.error("Failed to delete mailbox: %s", str(e))
            return web.json_response({"error": "删除邮箱失败"}, status=500)

    async def setup(self):
        try:
            # Initialize the database
            await init_db()

            # Initialize the Web admin interface
            self.web_admin = WebAdmin(self.config, self.storage, AsyncSessionLocal)
            self.web_app = web.Application(middlewares=[self.web_admin.auth_middleware])

            # Set up routes
            self.web_app.router.add_get('/admin/login', self.web_admin.login_page)
            self.web_app.router.add_post('/admin/login', self.web_admin.login)
            self.web_app.router.add_get('/admin/mailboxes', self.web_admin.mailboxes_page)
            self.web_app.router.add_get('/admin/mailboxes/list', self.web_admin.list_mailboxes)
            self.web_app.router.add_post('/admin/mailboxes/create', self.web_admin.create_mailbox)
            self.web_app.router.add_post('/admin/mailboxes/delete', self.web_admin.delete_mailbox)

            logger.info('Mail server setup completed successfully')
        except Exception as e:
            logger.error(f'Setup failed: {str(e)}')
            raise