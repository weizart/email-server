import smtplib
from email.mime.text import MIMEText

# 邮件服务器配置
smtp_server = 'smtp.silan.tech'  # SMTP 服务器地址
smtp_port = 2525  # SMTP 服务器端口，根据您的配置

# 发件人邮箱账户和密码
email_address = 'Qingbolan@silan.tech'
password = '123456'

# 收件人邮箱地址
recipient = 'silan.hu@u.nus.edu'

# 邮件内容
subject = '测试邮件 - 来自 Python 脚本'
body = '您好，这是一封通过 Python 脚本发送的测试邮件。'

# 创建 MIMEText 邮件对象
msg = MIMEText(body, 'plain', 'utf-8')
msg['Subject'] = subject
msg['From'] = email_address
msg['To'] = recipient

try:
    # 建立与 SMTP 服务器的连接
    smtp = smtplib.SMTP(smtp_server, smtp_port)
    smtp.set_debuglevel(1)  # 启用调试日志，便于查看详细的连接和交互信息

    # 如果服务器支持 STARTTLS，并且您已配置，请取消注释以下行
    # smtp.starttls()

    # 登录邮件服务器
    smtp.login(email_address, password)
    print('登录成功')

    # 发送邮件
    smtp.sendmail(email_address, recipient, msg.as_string())
    print('邮件发送成功')

    # 关闭连接
    smtp.quit()
except Exception as e:
    print(f'邮件发送失败: {e}')