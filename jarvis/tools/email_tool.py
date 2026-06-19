"""
tools/email_tool.py — Работа с электронной почтой.

Позволяет отправлять и читать письма по протоколах SMTP/IMAP.
Настройки почты должны быть в .env:
EMAIL_SMTP_SERVER
EMAIL_SMTP_PORT
EMAIL_IMAP_SERVER
EMAIL_IMAP_PORT
EMAIL_ADDRESS
EMAIL_PASSWORD
"""
from __future__ import annotations

import email
import imaplib
import logging
import os
import smtplib
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _get_email_config():
    """Получить настройки почты из переменных окружения."""
    from jarvis import config
    
    address = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_PASSWORD")
    
    if not address or not password:
        raise ValueError(
            "Не настроена электронная почта. Укажите EMAIL_ADDRESS и EMAIL_PASSWORD в файле .env"
        )
        
    return {
        "address": address,
        "password": password,
        "smtp_server": os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("EMAIL_SMTP_PORT", "465")),
        "imap_server": os.getenv("EMAIL_IMAP_SERVER", "imap.gmail.com"),
        "imap_port": int(os.getenv("EMAIL_IMAP_PORT", "993"))
    }


def send_email(to_address: str, subject: str, body: str) -> str:
    """
    Отправить электронное письмо.

    ⚠️ Требует подтверждения.

    Args:
        to_address: Email получателя.
        subject: Тема письма.
        body: Текст письма.
    """
    try:
        conf = _get_email_config()
        
        msg = MIMEMultipart()
        msg['From'] = conf["address"]
        msg['To'] = to_address
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Подключаемся по SSL
        if conf["smtp_port"] == 465:
            server = smtplib.SMTP_SSL(conf["smtp_server"], conf["smtp_port"])
        else:
            server = smtplib.SMTP(conf["smtp_server"], conf["smtp_port"])
            server.starttls()
            
        server.login(conf["address"], conf["password"])
        server.send_message(msg)
        server.quit()
        
        logger.info("email: отправлено письмо на %s", to_address)
        return f"Письмо успешно отправлено на адрес {to_address}."
        
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error("email: ошибка отправки: %s", e)
        return f"Ошибка при отправке письма: {e}"


def _decode_header_str(header: str | None) -> str:
    """Декодировать заголовок письма."""
    if not header:
        return ""
    
    decoded = []
    for text, charset in decode_header(header):
        if isinstance(text, bytes):
            decoded.append(text.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded.append(text)
    return "".join(decoded)


def read_emails(count: int = 5, unread_only: bool = True) -> str:
    """
    Прочитать последние входящие письма.

    Args:
        count: Количество писем для чтения (по умолчанию 5).
        unread_only: Читать только непрочитанные письма (по умолчанию True).
    """
    try:
        conf = _get_email_config()
        
        mail = imaplib.IMAP4_SSL(conf["imap_server"], conf["imap_port"])
        mail.login(conf["address"], conf["password"])
        mail.select("inbox")
        
        search_criterion = "UNSEEN" if unread_only else "ALL"
        status, messages = mail.search(None, search_criterion)
        
        if status != "OK":
            return "Ошибка поиска писем."
            
        message_nums = messages[0].split()
        if not message_nums:
            return "Новых писем нет." if unread_only else "Папка входящих пуста."
            
        # Берём последние `count` писем
        latest_nums = message_nums[-count:]
        
        result_lines = [f"Найдено {len(message_nums)} писем. Показываю последние {len(latest_nums)}:", ""]
        
        for num in reversed(latest_nums):
            status, msg_data = mail.fetch(num, "(RFC822)")
            if status != "OK":
                continue
                
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    subject = _decode_header_str(msg.get("Subject"))
                    from_header = _decode_header_str(msg.get("From"))
                    date_header = msg.get("Date")
                    
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                                break
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='replace')
                    
                    # Ограничиваем длину тела письма
                    body_preview = body.strip()[:200]
                    if len(body.strip()) > 200:
                        body_preview += "..."
                        
                    result_lines.append(f"От: {from_header}")
                    result_lines.append(f"Дата: {date_header}")
                    result_lines.append(f"Тема: {subject}")
                    result_lines.append(f"Текст:\n{body_preview}")
                    result_lines.append("-" * 40)
        
        mail.logout()
        return "\n".join(result_lines)
        
    except ValueError as e:
        return str(e)
    except Exception as e:
        logger.error("email: ошибка чтения: %s", e)
        return f"Ошибка при чтении почты: {e}"
