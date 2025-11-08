import base64
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import google.generativeai as ga
from dotenv import load_dotenv
import random

load_dotenv()

def generate_decoys(real_message, num_decoys=5):
    """
    Generate password decoys using Gemini AI.
    Returns a list of contextually relevant decoy passwords.
    """
    try:
        # Configure Gemini
        import google.generativeai as genai
        
        # Configure your API key
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        
        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-pro')
        
        # Create prompt for password generation
        prompt = f"""
        Generate {num_decoys} unique password decoys that are different from '{real_message}'.
        The passwords should:
        - Be realistic and similar in complexity to the real password
        - Include numbers and special characters
        - Be between 8-16 characters
        - Not be exactly like the real password
        - Return only the passwords, one per line, no explanations
        """
        
        # Generate response
        response = model.generate_content(prompt)
        
        # Process the response
        if response.text:
            # Split response into lines and clean up
            decoys = [line.strip() for line in response.text.split('\n') 
                     if line.strip() and line.strip() != real_message]
            
            # Ensure we have enough decoys
            while len(decoys) < num_decoys:
                decoys.append(f"Password{random.randint(100,999)}!")
                
            # Take only the required number of decoys
            return decoys[:num_decoys]
            
    except Exception as e:
        # Fallback to basic password generation if Gemini fails
        return fallback_generate_decoys(real_message, num_decoys)

def fallback_generate_decoys(real_message, num_decoys=3):
    """
    Fallback function for generating password decoys if Gemini fails.
    """
    import random
    import string
    
    def generate_password():
        patterns = [
            lambda: f"Pass{random.randint(100,999)}{'!@#$'[random.randint(0,3)]}",
            lambda: f"Secure{random.randint(10,99)}{'@#$'[random.randint(0,2)]}",
            lambda: f"P@ssw0rd{random.randint(10,99)}",
            lambda: f"Secret{random.randint(100,999)}{'!#'[random.randint(0,1)]}"
        ]
        return random.choice(patterns)()
    
    decoys = set()
    while len(decoys) < num_decoys:
        decoy = generate_password()
        if decoy != real_message:
            decoys.add(decoy)
    
    return list(decoys)

def send_email(subject, to_email, body):
    """
    Send an email using SMTP.
    """
    smtp_server = "smtp.gmail.com" 
    smtp_port = 587 
    sender_email = os.getenv('SENDER_EMAIL')
    email_password = os.getenv('EMAIL_PASSWORD')

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, email_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def generate_decoy_message(real_message):
    """
    Generate a decoy message using Gemini AI that provides completely wrong information.
    """
    try:
        # Configure Gemini
        import google.generativeai as genai

        # Configure your API key
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

        # Initialize Gemini model
        model = genai.GenerativeModel('gemini-pro')

        # Create a more targeted prompt for misleading information
        prompt = f"""
        The real message is: '{real_message}'. 
        Imagine a completely different scenario that involves different people, places, and times.
        Generate a decoy message that:
        - Describes a situation unrelated to the original message.
        - Refers to a different activity or event.
        - Creates a plausible and realistic, alternative context.
        - Be similar in length to the original message.
        """

        # Generate response
        response = model.generate_content(prompt)

        # Process the response
        if response.text:
            return response.text.strip()
        else:
            return "Decoy message generation failed."
    except Exception as e:
        return f"Decoy message generation failed: {e}"