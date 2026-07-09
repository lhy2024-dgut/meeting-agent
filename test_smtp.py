"""SMTP 连接诊断脚本，运行后会逐步输出问题所在"""
import smtplib
import ssl
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

host     = os.getenv("SMTP_HOST", "")
port     = int(os.getenv("SMTP_PORT", "587"))
user     = os.getenv("SMTP_USER", "")
password = os.getenv("SMTP_PASSWORD", "")

print("=== SMTP 配置 ===")
print(f"  HOST    : {host!r}")
print(f"  PORT    : {port}")
print(f"  USER    : {user!r}")
print(f"  PASSWORD: {'*' * len(password)!r}  (长度={len(password)})")
print()

if not all([host, user, password]):
    print("[ERROR] 配置不完整，请检查 .env 文件")
    sys.exit(1)

print(f"[1] 正在连接 {host}:{port} ...")
try:
    if port == 465:
        ctx = ssl.create_default_context()
        srv = smtplib.SMTP_SSL(host, port, context=ctx, timeout=10)
    else:
        srv = smtplib.SMTP(host, port, timeout=10)
        srv.ehlo()
        srv.starttls()
        srv.ehlo()
    print("[1] 连接成功")
except Exception as e:
    print(f"[ERROR] 连接失败: {e}")
    sys.exit(1)

print(f"[2] 正在登录 {user} ...")
try:
    srv.login(user, password)
    print("[2] 登录成功！SMTP 配置完全正确")
    srv.quit()
except smtplib.SMTPAuthenticationError as e:
    print(f"[ERROR] 认证失败: {e}")
    print()
    print("可能原因：")
    print("  1. 授权码填写错误（注意不是登录密码，是在163邮箱设置里生成的授权码）")
    print("  2. 授权码已过期或被重置，请重新生成")
    print("  3. 账号未开启 SMTP 服务（163邮箱→设置→POP3/SMTP/IMAP→开启SMTP服务）")
    print("  4. 账号被临时封禁（尝试登录网页版确认账号状态）")
    srv.close()
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] 登录时发生其他错误: {e}")
    srv.close()
    sys.exit(1)
