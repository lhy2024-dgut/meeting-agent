"""邮件发送服务 — 基于 smtplib，支持 HTML 正文 + 多附件 + 自动重试"""

import smtplib
import ssl
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from logger import get_logger

logger = get_logger(__name__)


def _check_smtp_config():
    """校验 SMTP 配置，返回 (ok, error_msg)"""
    try:
        import config as cfg
        host = getattr(cfg, "SMTP_HOST", "")
        user = getattr(cfg, "SMTP_USER", "")
        password = getattr(cfg, "SMTP_PASSWORD", "")
        if not host:
            return False, "SMTP_HOST 未配置，请在 .env 文件中设置 SMTP 服务器地址"
        if not user:
            return False, "SMTP_USER 未配置，请在 .env 文件中设置 SMTP 用户名"
        if not password:
            return False, "SMTP_PASSWORD 未配置，请在 .env 文件中设置 SMTP 密码"
        return True, None
    except Exception as e:
        return False, f"配置读取失败: {e}"


def build_email_html(title: str, date: str, minutes: str, action_items: str, resolutions: str) -> str:
    """生成兼容主流邮件客户端（Outlook/Gmail/QQ）的内联样式 HTML"""

    def _md_to_html(text: str) -> str:
        """简单 Markdown → 内联样式 HTML"""
        import re
        if not text:
            return ""
        lines = text.split("\n")
        out = []
        in_ul = False
        for line in lines:
            # H1
            if line.startswith("# ") and not line.startswith("## "):
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                content = line[2:].strip()
                out.append(
                    f'<h2 style="color:#1A1A2E;font-size:18px;font-weight:700;'
                    f'margin:20px 0 8px 0;padding-bottom:6px;'
                    f'border-bottom:2px solid #5B5EA6;">{content}</h2>'
                )
            # H2
            elif line.startswith("## ") and not line.startswith("### "):
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                content = line[3:].strip()
                out.append(
                    f'<h3 style="color:#2C3E50;font-size:15px;font-weight:600;'
                    f'margin:15px 0 6px 0;">{content}</h3>'
                )
            # H3
            elif line.startswith("### "):
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                content = line[4:].strip()
                out.append(
                    f'<h4 style="color:#34495E;font-size:14px;font-weight:600;'
                    f'margin:10px 0 4px 0;">{content}</h4>'
                )
            # List item
            elif line.startswith("- ") or line.startswith("* "):
                if not in_ul:
                    out.append('<ul style="margin:8px 0;padding-left:20px;">')
                    in_ul = True
                content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line[2:].strip())
                out.append(f'<li style="margin:4px 0;line-height:1.5;">{content}</li>')
            # Empty line
            elif not line.strip():
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                out.append('<div style="height:6px;"></div>')
            # Normal paragraph
            else:
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
                content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)
                out.append(
                    f'<p style="margin:6px 0;line-height:1.6;font-size:14px;">{content}</p>'
                )
        if in_ul:
            out.append("</ul>")
        return "\n".join(out)

    minutes_html = _md_to_html(minutes)
    action_html = _md_to_html(action_items)
    resolution_html = _md_to_html(resolutions)

    action_block = ""
    if action_items and action_items.strip():
        action_block = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:15px 0;">
          <tr><td style="background:#FEF3C7;border-left:4px solid #F59E0B;border-radius:6px;padding:15px;">
            <div style="color:#D97706;font-weight:700;font-size:15px;margin-bottom:10px;">&#x23F0; 待办事项</div>
            {action_html}
          </td></tr>
        </table>"""

    resolution_block = ""
    if resolutions and resolutions.strip():
        resolution_block = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:15px 0;">
          <tr><td style="background:#D1FAE5;border-left:4px solid #10B981;border-radius:6px;padding:15px;">
            <div style="color:#059669;font-weight:700;font-size:15px;margin-bottom:10px;">&#x2705; 会议决议</div>
            {resolution_html}
          </td></tr>
        </table>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#F1F5F9;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#F1F5F9;padding:20px 0;">
    <tr><td align="center">
      <table width="680" cellpadding="0" cellspacing="0" style="background:#FFFFFF;border-radius:8px;overflow:hidden;">
        <!-- Header -->
        <tr><td style="background:linear-gradient(135deg,#1A1A2E 0%,#5B5EA6 100%);padding:24px 30px;">
          <div style="color:#FFFFFF;font-size:22px;font-weight:700;margin:0;">&#x1F4CB; 会议纪要</div>
          <div style="color:#C7D2FE;font-size:14px;margin-top:6px;">{title}</div>
          <div style="color:#A5B4FC;font-size:13px;margin-top:4px;">日期：{date}</div>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:24px 30px;color:#374151;">
          {minutes_html}
          {action_block}
          {resolution_block}
        </td></tr>
        <!-- Footer -->
        <tr><td style="background:#F8FAFC;padding:16px 30px;border-top:1px solid #E2E8F0;">
          <p style="color:#94A3B8;font-size:12px;margin:0;text-align:center;">
            此邮件由 Meeting Agent 智能会议助手自动生成 · 请勿直接回复
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


class EmailService:
    """SMTP 邮件发送服务，支持多附件、HTML 正文、自动重试"""

    def __init__(self):
        import config as cfg
        self.host = getattr(cfg, "SMTP_HOST", "")
        self.port = int(getattr(cfg, "SMTP_PORT", 587))
        self.user = getattr(cfg, "SMTP_USER", "")
        self.password = getattr(cfg, "SMTP_PASSWORD", "")
        self.from_addr = getattr(cfg, "SMTP_FROM", "") or self.user

    def send(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: str = None,
        attachments: list = None,
        max_retries: int = 3,
        retry_interval: float = 2.0,
    ) -> tuple[bool, str | None]:
        """发送邮件，失败时自动重试。返回 (success, error_msg)。"""
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                self._send_once(to_email, subject, body_text, body_html, attachments or [])
                logger.info("邮件发送成功: %s", to_email)
                return True, None
            except smtplib.SMTPAuthenticationError as e:
                err = f"SMTP 认证失败，请检查用户名/密码: {e}"
                logger.error(err)
                return False, err
            except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, OSError) as e:
                last_err = f"SMTP 连接失败 (第{attempt}次): {e}"
                logger.warning(last_err)
            except smtplib.SMTPRecipientsRefused as e:
                err = f"收件人地址被拒绝 {to_email}: {e}"
                logger.error(err)
                return False, err
            except Exception as e:
                last_err = f"发送失败 (第{attempt}次): {e}"
                logger.warning(last_err)

            if attempt < max_retries:
                time.sleep(retry_interval)

        logger.error("邮件发送最终失败: %s — %s", to_email, last_err)
        return False, last_err

    def send_bulk(
        self,
        recipients: list[str],
        subject: str,
        body_text: str,
        body_html: str = None,
        attachments: list = None,
    ) -> list[dict]:
        """批量发送，返回 [{"email": str, "success": bool, "error": str|None}]"""
        results = []
        for email in recipients:
            ok, err = self.send(email, subject, body_text, body_html, attachments)
            results.append({"email": email, "success": ok, "error": err})
        return results

    def _send_once(self, to_email, subject, body_text, body_html, attachments):
        msg = MIMEMultipart("mixed")
        msg["From"] = self.from_addr
        msg["To"] = to_email
        msg["Subject"] = subject

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            alt.attach(MIMEText(body_html, "html", "utf-8"))
        msg.attach(alt)

        for att_path in attachments:
            p = Path(att_path)
            if not p.exists():
                logger.warning("附件不存在，跳过: %s", att_path)
                continue
            with open(p, "rb") as fh:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(fh.read())
            encoders.encode_base64(part)
            filename = p.name.encode("utf-8").decode("ascii", errors="replace")
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)

        if self.port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=30) as srv:
                srv.login(self.user, self.password)
                srv.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=30) as srv:
                srv.ehlo()
                if self.port != 25:
                    srv.starttls()
                srv.login(self.user, self.password)
                srv.send_message(msg)
