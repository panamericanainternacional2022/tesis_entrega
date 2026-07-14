from typing import Any, List, Optional


class EmailAttachment:
    def __init__(self, pdf_data: Any, filename: str = "report.pdf") -> None:
        if isinstance(pdf_data, bytes):
            from io import BytesIO
            pdf_data = BytesIO(pdf_data)
        self.pdf_data = pdf_data
        self.filename = filename


class EmailConfig:
    def __init__(
        self,
        risk_level: str,
        subject: str,
        body: str,
        attachment: Optional[EmailAttachment] = None,
        recipients: Optional[List[str]] = None,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
    ) -> None:
        self.risk_level = risk_level
        self.subject = subject
        self.body = body
        self.attachment = attachment
        self.recipients = recipients
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
