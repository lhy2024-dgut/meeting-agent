"""SMTP email delivery helpers for meeting summaries."""

from __future__ import annotations

from dataclasses import dataclass
import re
import smtplib
import ssl
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import config
from logger import get_logger

logger = get_logger(__name__)


@dataclass
class SmtpSettings:
    host: str
    port: int
    user: str
    password: str
    from_addr: str


_SMTP_DEFAULTS = {
    "163.com": ("smtp.163.com", 465),
    "126.com": ("smtp.126.com", 465),
    "qq.com": ("smtp.qq.com", 465),
    "foxmail.com": ("smtp.qq.com", 465),
    "gmail.com": ("smtp.gmail.com", 465),
    "outlook.com": ("smtp.office365.com", 587),
    "hotmail.com": ("smtp.office365.com", 587),
    "live.com": ("smtp.office365.com", 587),
}


def suggest_smtp_settings(email: str) -> tuple[str, int]:
    domain = (email or "").strip().lower().partition("@")[2]
    return _SMTP_DEFAULTS.get(domain, ("", 465))


def get_global_smtp_settings() -> SmtpSettings:
    return SmtpSettings(
        host=config.SMTP_HOST,
        port=int(config.SMTP_PORT),
        user=config.SMTP_USER,
        password=config.SMTP_PASSWORD,
        from_addr=config.SMTP_FROM or config.SMTP_USER,
    )


def check_smtp_config(settings: SmtpSettings | None = None) -> tuple[bool, str | None]:
    candidate = settings or get_global_smtp_settings()
    if not candidate.host:
        return False, "SMTP_HOST is not configured"
    if not candidate.user:
        return False, "SMTP_USER is not configured"
    if not candidate.password:
        return False, "SMTP_PASSWORD is not configured"
    return True, None


def _markdown_to_email_html(text: str) -> str:
    if not text:
        return ""

    lines = text.splitlines()
    output: list[str] = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(
                '<h2 style="color:#1A1A2E;font-size:18px;font-weight:700;'
                'margin:20px 0 8px;border-bottom:2px solid #5B5EA6;padding-bottom:6px;">'
                f"{stripped[2:].strip()}</h2>"
            )
            continue
        if stripped.startswith("## ") and not stripped.startswith("### "):
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(
                '<h3 style="color:#2C3E50;font-size:15px;font-weight:600;margin:15px 0 6px;">'
                f"{stripped[3:].strip()}</h3>"
            )
            continue
        if stripped.startswith("### "):
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(
                '<h4 style="color:#34495E;font-size:14px;font-weight:600;margin:10px 0 4px;">'
                f"{stripped[4:].strip()}</h4>"
            )
            continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                output.append('<ul style="margin:8px 0;padding-left:20px;">')
                in_list = True
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped[2:].strip())
            output.append(f'<li style="margin:4px 0;line-height:1.5;">{content}</li>')
            continue
        if not stripped:
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append('<div style="height:6px;"></div>')
            continue

        if in_list:
            output.append("</ul>")
            in_list = False
        content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
        content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)
        output.append(f'<p style="margin:6px 0;line-height:1.6;font-size:14px;">{content}</p>')

    if in_list:
        output.append("</ul>")
    return "\n".join(output)


def build_email_html(
    title: str,
    date_text: str,
    minutes: str,
    action_items: str,
    resolutions: str,
) -> str:
    minutes_html = _markdown_to_email_html(minutes)
    action_html = _markdown_to_email_html(action_items)
    resolution_html = _markdown_to_email_html(resolutions)

    action_block = ""
    if action_items.strip():
        action_block = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:15px 0;">
          <tr><td style="background:#FEF3C7;border-left:4px solid #F59E0B;border-radius:6px;padding:15px;">
            <div style="color:#D97706;font-weight:700;font-size:15px;margin-bottom:10px;">待办事项</div>
            {action_html}
          </td></tr>
        </table>"""

    resolution_block = ""
    if resolutions.strip():
        resolution_block = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin:15px 0;">
          <tr><td style="background:#D1FAE5;border-left:4px solid #10B981;border-radius:6px;padding:15px;">
            <div style="color:#059669;font-weight:700;font-size:15px;margin-bottom:10px;">会议决议</div>
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
        <tr><td style="background:linear-gradient(135deg,#1A1A2E 0%,#5B5EA6 100%);padding:24px 30px;">
          <div style="color:#FFFFFF;font-size:22px;font-weight:700;margin:0;">会议纪要</div>
          <div style="color:#C7D2FE;font-size:14px;margin-top:6px;">{title}</div>
          <div style="color:#A5B4FC;font-size:13px;margin-top:4px;">日期：{date_text}</div>
        </td></tr>
        <tr><td style="padding:24px 30px;color:#374151;">
          {minutes_html}
          {action_block}
          {resolution_block}
        </td></tr>
        <tr><td style="background:#F8FAFC;padding:16px 30px;border-top:1px solid #E2E8F0;">
          <p style="color:#94A3B8;font-size:12px;margin:0;text-align:center;">
            此邮件由 Meeting Agent 自动生成
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


class EmailService:
    def __init__(self, settings: SmtpSettings | None = None) -> None:
        candidate = settings or get_global_smtp_settings()
        self.host = candidate.host
        self.port = int(candidate.port)
        self.user = candidate.user
        self.password = candidate.password
        self.from_addr = candidate.from_addr or candidate.user

    def send(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        *,
        body_html: str | None = None,
        attachments: list[str] | None = None,
        max_retries: int = 3,
        retry_interval: float = 2.0,
    ) -> tuple[bool, str | None]:
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                self._send_once(
                    to_email,
                    subject,
                    body_text,
                    body_html=body_html,
                    attachments=attachments or [],
                )
                logger.info("Email sent: %s", to_email)
                return True, None
            except smtplib.SMTPAuthenticationError as exc:
                message = f"SMTP authentication failed: {exc}"
                logger.error(message)
                return False, message
            except smtplib.SMTPRecipientsRefused as exc:
                message = f"Recipient refused for {to_email}: {exc}"
                logger.error(message)
                return False, message
            except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, OSError) as exc:
                last_error = f"SMTP connection failed on attempt {attempt}: {exc}"
                logger.warning(last_error)
            except Exception as exc:  # pragma: no cover - defensive branch
                last_error = f"Email send failed on attempt {attempt}: {exc}"
                logger.warning(last_error)

            if attempt < max_retries:
                time.sleep(retry_interval)

        return False, last_error or "Unknown email delivery failure"

    def _send_once(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        *,
        body_html: str | None,
        attachments: list[str],
    ) -> None:
        msg = MIMEMultipart("mixed")
        msg["From"] = self.from_addr
        msg["To"] = to_email
        msg["Subject"] = subject

        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html:
            alt.attach(MIMEText(body_html, "html", "utf-8"))
        msg.attach(alt)

        for attachment_path in attachments:
            path = Path(attachment_path)
            if not path.exists():
                logger.warning("Attachment does not exist, skipping: %s", attachment_path)
                continue
            with path.open("rb") as handle:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(handle.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
            msg.attach(part)

        if self.port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=30) as server:
                server.login(self.user, self.password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.ehlo()
                if self.port != 25:
                    server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)
