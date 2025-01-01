import json
import random
import smtplib
from email.mime.text import MIMEText

#honeyencryption
def honey_encrypt(plaintext, key):
    plausible_decoys = ["Decoy1", "Decoy2", "Decoy3"]
    encrypted = json.dumps({"real": plaintext, "decoys": plausible_decoys})
    return encrypted

def honey_decrypt(encrypted, key):
    data = json.loads(encrypted)
    if key == "correct_key":
        return data["real"]
    return random.choice(data["decoys"])

def send_email(subject, recipient_email, body):
    sender_email = "your_email@example.com" 
    sender_password = "your_password"       

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = sender_email
            msg['To'] = recipient_email
            server.sendmail(sender_email, recipient_email, msg.as_string())
    except Exception as e:
        print(f"Failed to send email: {e}")
