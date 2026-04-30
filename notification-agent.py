import os
import smtplib
from dotenv import load_dotenv
from email.mime.text import MIMEText
from twilio.rest import Client

load_dotenv()

# -------------------------
# ENV Values
# -------------------------
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH")
TWILIO_WHATSAPP = os.getenv("TWILIO_WHATSAPP")

twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# -------------------------
# MANUAL DETAILS
# -------------------------
candidate_name = "Anas Javed"
candidate_email = "anas.jvd1201@gmail.com"  # <-- change here
candidate_phone = "+919045386958"         # <-- change here

# -------------------------
# Send Email
# -------------------------
def send_email():
    subject = "🎉 Resume Selected"

    body = f"""
Hi {candidate_name},

Congratulations! 🎉

Your resume has been selected for the next round.

Our HR team will contact you soon.

Best Regards,
HR Team
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = candidate_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, candidate_email, msg.as_string())
        server.quit()
        print("✅ Email Sent Successfully")

    except Exception as e:
        print("❌ Email Error:", e)

# -------------------------
# Send WhatsApp
# -------------------------
def send_whatsapp():
    try:
        twilio_client.messages.create(
            body=f"Hi {candidate_name}, 🎉 Your resume has been selected. HR team will contact you soon.",
            from_=TWILIO_WHATSAPP,
            to=f"whatsapp:{candidate_phone}"
        )
        print("✅ WhatsApp Sent Successfully")

    except Exception as e:
        print("❌ WhatsApp Error:", e)

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    send_email()
    send_whatsapp()