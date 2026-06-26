import smtplib
import os
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_summary_email(analysis_text: str, counts: dict, log_path: str, config: dict):
    """
    Send a formatted summary email after LLM analysis completes.
    SMTP config is read from the agent config YAML under 'email' key.
    """
    email_config = config.get('email', {})

    smtp_host = email_config.get('smtp_host', 'sandbox.smtp.mailtrap.io')
    smtp_port = email_config.get('smtp_port', 2525)
    smtp_user = email_config.get('smtp_user', '')
    smtp_pass = email_config.get('smtp_pass', '')
    sender = email_config.get('sender', 'jiopc-agent@jiopc.local')
    recipient = email_config.get('recipient', '')

    if not recipient:
        print("  [Email] No recipient configured — skipping email.")
        return

    if not smtp_user or not smtp_pass:
        print("  [Email] SMTP credentials not configured — skipping email.")
        return

    # Determine PROMOTE or HOLD from analysis text
    recommendation = "UNKNOWN"
    for line in analysis_text.splitlines():
        if "PROMOTE" in line.upper():
            recommendation = "PROMOTE"
            break
        if "HOLD" in line.upper():
            recommendation = "HOLD"
            break

    # Build subject
    total = counts.get('total', 0)
    passed = counts.get('pass', 0)
    failed = counts.get('fail', 0)
    blocked = counts.get('blocked', 0)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = f"[JioPC Agent] {recommendation} — {passed}/{total} passed | {ts}"

    # Build HTML body
    color = "#2e7d32" if recommendation == "PROMOTE" else "#c62828"
    html = f"""
<html><body style="font-family: Arial, sans-serif; max-width: 700px; margin: 0 auto;">

<div style="background:{color}; color:white; padding:16px 24px; border-radius:8px 8px 0 0;">
  <h2 style="margin:0">JioPC OS Image Test Report</h2>
  <p style="margin:4px 0 0">{ts}</p>
</div>

<div style="background:#f5f5f5; padding:16px 24px;">
  <table style="width:100%; border-collapse:collapse;">
    <tr>
      <td style="padding:8px; font-size:18px; font-weight:bold; color:{color};">
        {recommendation}
      </td>
      <td style="padding:8px; text-align:right;">
        <strong>{passed}/{total}</strong> passed &nbsp;|&nbsp;
        FAIL={failed} &nbsp;|&nbsp;
        BLOCKED={blocked}
      </td>
    </tr>
  </table>
</div>

<div style="padding:24px; background:white; border:1px solid #e0e0e0;">
  <h3 style="color:#333;">LLM Analysis</h3>
  <pre style="background:#f9f9f9; padding:16px; border-radius:4px;
              font-size:13px; white-space:pre-wrap; border-left:4px solid {color};">
{analysis_text}
  </pre>
</div>

<div style="padding:12px 24px; background:#f5f5f5; border-radius:0 0 8px 8px;
            font-size:12px; color:#666;">
  Log file: {log_path}
</div>

</body></html>
"""

    # Build plain text fallback
    plain = f"""JioPC OS Image Test Report — {ts}

RECOMMENDATION: {recommendation}
Results: {passed}/{total} passed | FAIL={failed} | BLOCKED={blocked}

--- LLM Analysis ---
{analysis_text}

Log: {log_path}
"""

    # Compose email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        print(f"  [Email] Sending to {recipient} via {smtp_host}:{smtp_port}...")
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(sender, recipient, msg.as_string())
        print(f"  [Email] Sent successfully ✓")
    except Exception as e:
        print(f"  [Email] Failed to send: {e}")
