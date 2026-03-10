"""
Email alert channel using Python's smtplib.

Works with any SMTP server: Gmail (with app password), SMTP2Go, etc.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


@dataclass
class EmailAlert:
    """Send alerts via SMTP email."""

    smtp_host: str
    smtp_port: int
    username: str
    password: str
    from_addr: str
    to_addr: str
    use_tls: bool = True
    subject_prefix: str = "[gh-sentinel]"

    def send(self, message: str) -> None:
        """Send message as an email."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"{self.subject_prefix} GitHub Activity Alert"
        msg["From"] = self.from_addr
        msg["To"] = self.to_addr

        # Plain text body
        msg.attach(MIMEText(message, "plain"))

        # Simple HTML version
        html_body = "<pre>" + message.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"
        msg.attach(MIMEText(html_body, "html"))

        try:
            if self.use_tls:
                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.starttls()
                    server.login(self.username, self.password)
                    server.sendmail(self.from_addr, [self.to_addr], msg.as_string())
            else:
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=15) as server:
                    server.login(self.username, self.password)
                    server.sendmail(self.from_addr, [self.to_addr], msg.as_string())
        except smtplib.SMTPException as e:
            raise RuntimeError(f"Email send failed: {e}") from e
        except OSError as e:
            raise RuntimeError(f"SMTP connection failed: {e}") from e
