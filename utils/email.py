from datetime import datetime
from email.message import EmailMessage
from html import escape

import aiosmtplib

from config import settings


async def send_email(
    email_from: str,
    email_to: str,
    subject: str,
    plain_text: str,
    html_content: str | None,
):
    message = EmailMessage()
    message["FROM"] = email_from
    message["TO"] = email_to
    message["SUBJECT"] = subject

    message.set_content(plain_text)
    if html_content:
        message.add_alternative(html_content, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_server,
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password.get_secret_value(),
        start_tls=True,
    )


async def send_reset_password_email(email_to: str, username: str, token: str):

    reset_url = f"{settings.frontend_url}/reset-password?token={token}"
    safe_username = escape(username)

    plain_text = (
        f"Hi {username},\n\n"
        "We received a request to reset password for your Quizee account.\n"
        f"Reset it by visiting this link:\n{reset_url}\n\n"
        "This link expires in 1 hour. If you didn't request this, ignore this email "
        "and your password will remain unchanged.\n\n"
        "- Quizee Team"
    )

    html_content = f"""\
<!DOCTYPE html>
<html>
  <head>
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <style>
      body {{ background-color:#f7f7f9; }}
      .card {{ background-color:#ffffff; border-color:rgba(0,0,0,0.08); }}
      .header {{ background-color:#4550d4; }}
      .text {{ color:#0e0e14; }}
      .muted {{ color:#6b6b82; }}
      .link, .btn {{ background-color:#4550d4; color:#4550d4; }}
      .footer {{ background-color:#eeeef5; }}

      @media (prefers-color-scheme: dark) {{
        body {{ background-color:#0d0d14 !important; }}
        .card {{ background-color:#15151f !important; border-color:rgba(255,255,255,0.08) !important; }}
        .header {{ background-color:#3a41ad !important; }}
        .text {{ color:#ededf5 !important; }}
        .muted {{ color:#8888a4 !important; }}
        .link {{ color:#636df0 !important; }}
        .btn {{ background-color:#636df0 !important; }}
        .footer {{ background-color:#1d1d2a !important; }}
      }}
    </style>
  </head>
  <body style="margin:0;padding:0;background-color:#f7f7f9;font-family:Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="body" style="background-color:#f7f7f9;padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" class="card" style="background-color:#ffffff;border-radius:8px;overflow:hidden;border:1px solid rgba(0,0,0,0.08);">
            <tr>
              <td class="header" style="background-color:#4550d4;padding:24px 32px;">
                <h1 style="margin:0;color:#ffffff;font-size:20px;">Quizee</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <h2 class="text" style="margin:0 0 16px;color:#0e0e14;font-size:18px;">Reset your password</h2>
                <p class="text" style="margin:0 0 16px;color:#0e0e14;font-size:14px;line-height:1.6;">
                  Hi {safe_username},
                </p>
                <p class="text" style="margin:0 0 24px;color:#0e0e14;font-size:14px;line-height:1.6;">
                  We received a request to reset the password for your Quizee account.
                  Click the button below to choose a new one. This link expires in 1 hour.
                </p>
                <table role="presentation" cellpadding="0" cellspacing="0">
                  <tr>
                    <td class="btn" style="border-radius:6px;background-color:#4550d4;">
                      <a href="{reset_url}"
                         style="display:inline-block;padding:12px 24px;
                                text-decoration:none;">
                        <span style="color:#ffffff;font-size:14px;font-weight:bold;text-decoration:none;">Reset Password</span>
                      </a>
                    </td>
                  </tr>
                </table>
                <p class="muted" style="margin:24px 0 0;color:#6b6b82;font-size:13px;line-height:1.6;">
                  If the button doesn't work, copy and paste this link into your browser:<br>
                  <a href="{reset_url}" class="link" style="color:#4550d4;word-break:break-all;">{reset_url}</a>
                </p>
                <p class="muted" style="margin:24px 0 0;color:#6b6b82;font-size:12px;line-height:1.6;">
                  If you didn't request a password reset, you can safely ignore this email —
                  your password will remain unchanged.
                </p>
              </td>
            </tr>
            <tr>
              <td class="footer" style="padding:16px 32px;background-color:#eeeef5;">
                <p class="muted" style="margin:0;color:#6b6b82;font-size:12px;">&copy; Quizee</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""

    await send_email(
        email_from=settings.mail_from,
        email_to=email_to,
        subject="Reset your Quizee password",
        plain_text=plain_text,
        html_content=html_content,
    )


async def send_theft_notification_email(email_to: str, username: str, time: datetime):
    safe_username = escape(username)
    plain_text = (
        f"Hi {username},\n\n"
        "We detected a suspicious login attempt to your Quizee account.\n"
        f"Time: {time}\n\n"
        "If this was you, you can safely ignore this email. If not, we recommend changing your password immediately.\n\n"
        "- Quizee Team"
    )

    html_content = f"""\
<!DOCTYPE html>
<html>
    <head>
        <meta name="color-scheme" content="light dark">
        <meta name="supported-color-schemes" content="light dark">
        <style>
            body {{ background-color:#f7f7f9; }}
            .card {{ background-color:#ffffff; border-color:rgba(0,0,0,0.08); }}
            .header {{ background-color:#4550d4; }}
            .text {{ color:#0e0e14; }}
            .muted {{ color:#6b6b82; }}
            .link, .btn {{ background-color:#4550d4; color:#4550d4; }}
            .footer {{ background-color:#eeeef5; }}

            @media (prefers-color-scheme: dark) {{
                body {{ background-color:#0d0d14 !important; }}
                .card {{ background-color:#15151f !important; border-color:rgba(255,255,255,0.08) !important; }}
                .header {{ background-color:#3a41ad !important; }}
                .text {{ color:#ededf5 !important; }}
                .muted {{ color:#8888a4 !important; }}
                .link {{ color:#636df0 !important; }}
                .btn {{ background-color:#636df0 !important; }}
                .footer {{ background-color:#1d1d2a !important; }}
            }}
        </style>
    </head>
    <body style="margin:0;padding:0;background-color:#f7f7f9;font-family:Helvetica,Arial,sans-serif;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" class="body" style="background-color:#f7f7f9;padding:32px 0;">
            <tr>
                <td align="center">
                    <table role="presentation" width="480" cellpadding="0" cellspacing="0"
    class="card" style="background-color:#ffffff;border-radius:8px;overflow:hidden;border:1px solid rgba(0,0,0,0.08);">
                            <tr>
                                <td class="header" style="background-color:#4550d4;padding:24px 32px;">
                                    <h1 style="margin:0;color:#ffffff;font-size:20px;">Quizee</h1>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:32px;">
                                    <h2 class="text" style="margin:0 0 16px;color:#0e0e14;font-size:18px;">Suspicious Login Attempt Detected</h2>
                                    <p class="text" style="margin:0 0 16px;color:#0e0e14;font-size:14px;line-height:1.6;">
                                        Hi {safe_username},
                                    </p>
                                    <p class="text" style="margin:0 0 24px;color:#0e0e14;font-size:14px;line-height:1.6;">
                                        We detected a suspicious login attempt to your Quizee account.
                                        Here are the details:
                                    </p>
                                    <ul class="text" style="margin:0 0 24px;color:#0e0e14;font-size:14px;line-height:1.6;">
                                        <li>Time: {time}</li>
                                    </ul>
                                    <p class="muted" style="margin:24px 0 0;color:#6b6b82;font-size:12px;line-height:1.6;">
                                        If this was you, you can safely ignore this email. If not, we recommend changing your password immediately.
                                    </p>
                                </td>
                            </tr>
                            <tr>
                                <td class="footer" style="padding:16px 32px;background-color:#eeeef5;">
                                    <p class="muted" style="margin:0;color:#6b6b82;font-size:12px;">&copy; Quizee</p>
                                </td>
                            </tr>
                        </table>
                </td>
            </tr>
        </table>
    </body>
</html>
"""

    await send_email(
        email_from=settings.mail_from,
        email_to=email_to,
        subject="Suspicious Login Attempt Detected",
        plain_text=plain_text,
        html_content=html_content,
    )
