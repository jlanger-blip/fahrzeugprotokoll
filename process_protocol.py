#!/usr/bin/env python3
"""
Fahrzeugprotokoll - Kompletter Workflow
1. Empfängt Protokoll-Daten
2. Lädt Fotos nach Kennzeichen sortiert zu Google Drive
3. Sendet Email mit Link an Empfänger
"""

import os
import sys
import json
import base64
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

from config import (
    PARENT_FOLDER_ID, SERVICE_ACCOUNT_FILE,
    EMAIL_RECIPIENTS, SMTP_SERVER, SMTP_PORT, 
    SMTP_USER, SMTP_PASSWORD, SMTP_FROM
)


def get_drive_service():
    """Google Drive Service mit Service Account."""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, 
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=creds)


def sanitize_filename(name):
    """Entfernt ungültige Zeichen aus Dateinamen."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def find_or_create_folder(service, name, parent_id):
    """Findet einen Ordner oder erstellt ihn."""
    query = f"name='{name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')


def upload_base64_image(service, folder_id, filename, base64_data):
    """Lädt ein Base64-Bild hoch."""
    if ',' in base64_data:
        base64_data = base64_data.split(',', 1)[1]
    
    try:
        image_bytes = base64.b64decode(base64_data)
    except Exception as e:
        print(f"  ⚠️ Fehler: {filename}: {e}")
        return None
    
    file_metadata = {'name': filename, 'parents': [folder_id]}
    media = MediaInMemoryUpload(image_bytes, mimetype='image/jpeg')
    
    file = service.files().create(
        body=file_metadata, media_body=media,
        fields='id, webViewLink'
    ).execute()
    return file


def send_email(data, folder_link, uploaded_count):
    """Sendet Email mit Protokoll-Zusammenfassung."""
    plate = data.get('plate', 'Unbekannt')
    date = data.get('date', '-')
    time = data.get('time', '-')
    process = data.get('process', '-')
    employee = data.get('employee', '-')
    customer = data.get('customer', '-')
    customer_email = data.get('customerEmail', '')
    model = data.get('model', '-')
    mileage = data.get('mileage', '-')
    location = data.get('location', '-')
    
    # Schäden sammeln
    damages = data.get('damage', [])
    damage_text = ""
    if damages:
        damage_text = "\n\n⚠️ SCHÄDEN DOKUMENTIERT:\n"
        for i, d in enumerate(damages, 1):
            damage_text += f"  {i}. {d.get('area', '-')}: {d.get('desc', '-')} ({d.get('size', '-')} cm)\n"
    
    subject = f"🚗 Fahrzeugprotokoll: {plate} - {process} ({date})"
    
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #c8102e, #8b0000); color: white; padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="margin: 0; font-size: 24px;">🚗 Fahrzeugprotokoll</h1>
                <p style="margin: 5px 0 0; opacity: 0.9;">{process} - {date} um {time}</p>
            </div>
            
            <div style="background: #f9f9f9; padding: 20px; border: 1px solid #ddd;">
                <h2 style="color: #c8102e; margin-top: 0; font-size: 18px;">Fahrzeugdaten</h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Kennzeichen:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #eee;">{plate}</td></tr>
                    <tr><td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Marke/Modell:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #eee;">{model}</td></tr>
                    <tr><td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Kilometerstand:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #eee;">{mileage} km</td></tr>
                    <tr><td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Standort:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #eee;">{location}</td></tr>
                </table>
                
                <h2 style="color: #c8102e; margin-top: 20px; font-size: 18px;">Beteiligte</h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Mitarbeiter:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #eee;">{employee}</td></tr>
                    <tr><td style="padding: 8px 0; border-bottom: 1px solid #eee;"><strong>Kunde/Fahrer:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #eee;">{customer or '-'}</td></tr>
                    <tr><td style="padding: 8px 0;"><strong>E-Mail Fahrer:</strong></td><td style="padding: 8px 0;">{customer_email or '-'}</td></tr>
                </table>
                
                {"<div style='background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 5px; margin-top: 20px;'><h3 style='color: #856404; margin: 0 0 10px;'>⚠️ Schäden dokumentiert</h3>" + "".join([f"<p style='margin: 5px 0;'><strong>{d.get('area', '-')}:</strong> {d.get('desc', '-')} ({d.get('size', '-')} cm)</p>" for d in damages]) + "</div>" if damages else ""}
            </div>
            
            <div style="background: #c8102e; color: white; padding: 20px; text-align: center; border-radius: 0 0 10px 10px;">
                <p style="margin: 0 0 15px; font-size: 16px;">📁 <strong>{uploaded_count} Fotos</strong> wurden hochgeladen</p>
                <a href="{folder_link}" style="display: inline-block; background: white; color: #c8102e; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">📂 Fotos in Google Drive öffnen</a>
            </div>
            
            <p style="text-align: center; color: #888; font-size: 12px; margin-top: 20px;">
                ALMAS INDUSTRIES AG | Floßwörthstraße 57 | D-68199 Mannheim<br>
                Diese E-Mail wurde automatisch generiert.
            </p>
        </div>
    </body>
    </html>
    """
    
    # Email erstellen
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"Fahrzeugprotokoll <{SMTP_FROM}>"
    msg['To'] = ", ".join(EMAIL_RECIPIENTS)
    
    # Plain text version
    plain = f"""
Fahrzeugprotokoll - {process}
Datum: {date} um {time}

FAHRZEUGDATEN:
- Kennzeichen: {plate}
- Marke/Modell: {model}
- Kilometerstand: {mileage} km
- Standort: {location}

BETEILIGTE:
- Mitarbeiter: {employee}
- Kunde/Fahrer: {customer or '-'}
- E-Mail Fahrer: {customer_email or '-'}
{damage_text}
📁 {uploaded_count} Fotos hochgeladen
🔗 {folder_link}

---
ALMAS INDUSTRIES AG
    """
    
    msg.attach(MIMEText(plain, 'plain'))
    msg.attach(MIMEText(html, 'html'))
    
    # Senden
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, EMAIL_RECIPIENTS, msg.as_string())
        print(f"✅ Email gesendet an: {', '.join(EMAIL_RECIPIENTS)}")
        return True
    except Exception as e:
        print(f"❌ Email-Fehler: {e}")
        return False


def process_protocol(data):
    """Hauptfunktion - verarbeitet komplettes Protokoll."""
    print("🚗 Fahrzeugprotokoll wird verarbeitet...")
    
    plate = data.get('plate', '').strip()
    if not plate:
        return {"success": False, "error": "Kein Kennzeichen angegeben"}
    
    date = data.get('date', datetime.now().strftime('%d.%m.%Y'))
    time = data.get('time', datetime.now().strftime('%H:%M'))
    
    plate_folder_name = sanitize_filename(plate.upper())
    session_folder_name = f"{date.replace('.', '-')}_{time.replace(':', '-')}"
    
    print(f"📁 Kennzeichen: {plate_folder_name}")
    print(f"📁 Session: {session_folder_name}")
    
    service = get_drive_service()
    
    # Ordner erstellen
    plate_folder_id = find_or_create_folder(service, plate_folder_name, PARENT_FOLDER_ID)
    session_folder_id = find_or_create_folder(service, session_folder_name, plate_folder_id)
    
    uploaded_files = []
    
    # Pflichtfotos hochladen
    photos = data.get('photos', [])
    for i, photo in enumerate(photos, 1):
        title = photo.get('title', f'Foto_{i}')
        data_url = photo.get('dataUrl', '')
        if not data_url:
            continue
        filename = f"{i:02d}_{sanitize_filename(title)}.jpg"
        print(f"  📷 {filename}")
        result = upload_base64_image(service, session_folder_id, filename, data_url)
        if result:
            uploaded_files.append(filename)
    
    # Schadensfotos
    for i, damage in enumerate(data.get('damage', []), 1):
        for j, photo_url in enumerate(damage.get('photos', []), 1):
            area = damage.get('area', f'Schaden_{i}')
            filename = f"Schaden_{i:02d}_{sanitize_filename(area)}_{j}.jpg"
            print(f"  📷 {filename}")
            result = upload_base64_image(service, session_folder_id, filename, photo_url)
            if result:
                uploaded_files.append(filename)
    
    # Sichtprüfung Fotos
    for section_name, section_key in [('Aussen', 'exterior'), ('Innen', 'interior')]:
        for item in data.get(section_key, []):
            for j, photo_url in enumerate(item.get('photos', []), 1):
                area = item.get('area', 'Unbekannt')
                filename = f"{section_name}_{sanitize_filename(area)}_{j}.jpg"
                print(f"  📷 {filename}")
                result = upload_base64_image(service, session_folder_id, filename, photo_url)
                if result:
                    uploaded_files.append(filename)
    
    # Protokoll-JSON speichern
    protocol_meta = {k: v for k, v in data.items()}
    # Bilder entfernen für JSON
    for key in ['photos', 'signatures']:
        if key in protocol_meta:
            if key == 'photos':
                protocol_meta[key] = [{'title': p.get('title')} for p in protocol_meta[key]]
            elif key == 'signatures':
                protocol_meta[key] = {k: '(gespeichert)' for k in protocol_meta[key] if protocol_meta[key].get(k)}
    for d in protocol_meta.get('damage', []):
        d['photos'] = len(d.get('photos', []))
    for e in protocol_meta.get('exterior', []):
        e['photos'] = len(e.get('photos', []))
    for i in protocol_meta.get('interior', []):
        i['photos'] = len(i.get('photos', []))
    
    json_bytes = json.dumps(protocol_meta, indent=2, ensure_ascii=False).encode('utf-8')
    file_metadata = {'name': 'protokoll.json', 'parents': [session_folder_id]}
    media = MediaInMemoryUpload(json_bytes, mimetype='application/json')
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    
    folder_link = f"https://drive.google.com/drive/folders/{session_folder_id}"
    
    print(f"\n✅ {len(uploaded_files)} Fotos hochgeladen")
    print(f"📁 {folder_link}")
    
    # Email senden
    send_email(data, folder_link, len(uploaded_files))
    
    return {
        "success": True,
        "plate": plate,
        "date": date,
        "time": time,
        "driveLink": folder_link,
        "folderId": session_folder_id,
        "uploadedFiles": len(uploaded_files)
    }


if __name__ == '__main__':
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)
    
    result = process_protocol(data)
    print(json.dumps(result, indent=2, ensure_ascii=False))
