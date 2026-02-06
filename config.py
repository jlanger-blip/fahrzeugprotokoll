"""
Konfiguration für Fahrzeugprotokoll Workflow
"""

# Google Drive
PARENT_FOLDER_ID = "1ZDx6daN3XrfZiB_6DNaf8sg0MFsiqpwk"  # Ordner "Autoübergabe"
SERVICE_ACCOUNT_FILE = "/root/.openclaw/workspace/google-service-account.json"

# Email-Empfänger
EMAIL_RECIPIENTS = [
    "j.langer@almas-industries.com",
    "j.langer@almas-industries.de",
    "b.berlik@almas-industries.com"
]

# SMTP (IONOS)
SMTP_SERVER = "smtp.ionos.de"
SMTP_PORT = 587
SMTP_USER = "j.langer@almas-industries.de"
SMTP_PASSWORD = "j@6f$BEc!PCo9J"
SMTP_FROM = "j.langer@almas-industries.de"
