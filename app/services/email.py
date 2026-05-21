"""
services/email.py
─────────────────
Email sending via Gmail SMTP for password reset and welcome emails.

Setup:
1. Enable 2-Step Verification at https://myaccount.google.com/security
2. Generate App Password at https://myaccount.google.com/apppasswords
3. Set MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM in .env
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger("nutribudget.email")


def _send_email(to_email: str, subject: str, html_body: str) -> bool:
    """Internal: send email via Gmail SMTP. Returns True on success."""
    if not settings.MAIL_USERNAME or not settings.MAIL_PASSWORD:
        logger.warning(f"Email not sent (SMTP not configured). Would send to: {to_email}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
        msg["To"]      = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT) as server:
            server.starttls()
            server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
            server.sendmail(settings.MAIL_FROM, to_email, msg.as_string())

        logger.info(f"✅ Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to send email to {to_email}: {e}")
        return False


# ── Templates ─────────────────────────────────────────────────────────────────
def send_password_reset_email(to_email: str, token: str, user_name: str = "") -> bool:
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    greeting  = f"Hi {user_name.split(' ')[0]}," if user_name else "Hi,"

    html = f"""
    <!DOCTYPE html>
    <html dir="ltr">
    <head><meta charset="utf-8"></head>
    <body style="margin:0; padding:0; background:#0a1f15; font-family:-apple-system,Segoe UI,Roboto,sans-serif;">
      <div style="max-width:600px; margin:40px auto; padding:40px; background:#0f2818; border-radius:24px; border:1px solid #1a4d2c;">

        <div style="text-align:center; margin-bottom:32px;">
          <div style="display:inline-block; width:56px; height:56px; background:#4DB87A;
                      border-radius:16px; line-height:56px; font-size:28px;">🌿</div>
          <h1 style="color:#fff; margin:16px 0 4px; font-size:24px;">NutriBudget EG</h1>
          <p style="color:#7a8b80; margin:0; font-size:13px;">AI-powered nutrition for Egypt</p>
        </div>

        <h2 style="color:#fff; font-size:20px; margin-bottom:16px;">Reset your password</h2>
        <p style="color:#b8c7be; line-height:1.6; font-size:14px;">{greeting}</p>
        <p style="color:#b8c7be; line-height:1.6; font-size:14px;">
          We received a request to reset your password. Click the button below to set a new one.
          This link expires in <strong style="color:#fff;">{settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes</strong>.
        </p>

        <div style="text-align:center; margin:32px 0;">
          <a href="{reset_url}"
             style="display:inline-block; padding:14px 32px; background:#4DB87A; color:#fff;
                    text-decoration:none; border-radius:14px; font-weight:bold; font-size:14px;">
            Reset Password
          </a>
        </div>

        <p style="color:#7a8b80; font-size:12px; line-height:1.6;">
          If the button doesn't work, copy this link:<br>
          <span style="color:#4DB87A; word-break:break-all;">{reset_url}</span>
        </p>

        <hr style="border:none; border-top:1px solid #1a4d2c; margin:32px 0;">
        <p style="color:#7a8b80; font-size:12px; text-align:center;">
          Didn't request this? You can safely ignore this email.
        </p>
      </div>
    </body>
    </html>
    """
    return _send_email(to_email, "Reset your NutriBudget password", html)


def send_welcome_email(to_email: str, user_name: str = "") -> bool:
    greeting = f"Welcome {user_name.split(' ')[0]}!" if user_name else "Welcome!"
    login_url = f"{settings.FRONTEND_URL}/login"

    html = f"""
    <!DOCTYPE html>
    <html dir="ltr">
    <head><meta charset="utf-8"></head>
    <body style="margin:0; padding:0; background:#0a1f15; font-family:-apple-system,Segoe UI,Roboto,sans-serif;">
      <div style="max-width:600px; margin:40px auto; padding:40px; background:#0f2818; border-radius:24px; border:1px solid #1a4d2c;">

        <div style="text-align:center; margin-bottom:32px;">
          <div style="display:inline-block; width:56px; height:56px; background:#4DB87A;
                      border-radius:16px; line-height:56px; font-size:28px;">🌿</div>
          <h1 style="color:#fff; margin:16px 0 4px; font-size:24px;">{greeting}</h1>
          <p style="color:#7a8b80; margin:0; font-size:13px;">Your nutrition journey starts now</p>
        </div>

        <p style="color:#b8c7be; line-height:1.6; font-size:14px;">
          Thanks for joining NutriBudget EG! Here's what you can do:
        </p>

        <ul style="color:#b8c7be; line-height:2; font-size:14px; padding-left:20px;">
          <li>🎯 <strong style="color:#fff;">Smart meal plans</strong> optimized for your goals & budget</li>
          <li>📷 <strong style="color:#fff;">Analyze meals</strong> from photos using AI</li>
          <li>💡 <strong style="color:#fff;">Personalized recipes</strong> based on what you love</li>
          <li>📊 <strong style="color:#fff;">Track everything</strong> — cost, calories, macros</li>
        </ul>

        <div style="text-align:center; margin:32px 0;">
          <a href="{login_url}"
             style="display:inline-block; padding:14px 32px; background:#4DB87A; color:#fff;
                    text-decoration:none; border-radius:14px; font-weight:bold; font-size:14px;">
            Get Started
          </a>
        </div>

        <hr style="border:none; border-top:1px solid #1a4d2c; margin:32px 0;">
        <p style="color:#7a8b80; font-size:12px; text-align:center;">
          NutriBudget EG · AI-powered nutrition for Egypt
        </p>
      </div>
    </body>
    </html>
    """
    return _send_email(to_email, "Welcome to NutriBudget EG 🌿", html)