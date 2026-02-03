#!/usr/bin/env python3
"""
Fahrzeugprotokoll - Google Drive Upload Script
Sortiert Fotos nach Kennzeichen in Google Drive Ordner.

Ordner-Struktur:
  Fahrzeugprotokolle/
    └── [KENNZEICHEN]/
        └── [DATUM]_[UHRZEIT]/
            ├── 01_Front.jpg
            ├── 02_Heck.jpg
            ├── ...
            └── protokoll.json

Verwendung:
  python upload_to_drive.py < protokoll.json
  
  oder als HTTP-Handler (für n8n/Webhook):
  curl -X POST -d @protokoll.json http://localhost:8080/upload
"""

import os
import sys
import json
import base64
import re
from datetime import datetime
from pathlib import Path

# Google Drive API
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

# Konfiguration
PARENT_FOLDER_ID = "1ZDx6daN3XrfZiB_6DNaf8sg0MFsiqpwk"  # Hauptordner für Fahrzeugprotokolle
SERVICE_ACCOUNT_FILE = "/root/.openclaw/workspace/google-service-account.json"
SCOPES = ['https://www.googleapis.com/auth/drive']


def get_drive_service():
    """Google Drive Service mit Service Account authentifizieren."""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)


def sanitize_filename(name):
    """Entfernt ungültige Zeichen aus Dateinamen."""
    # Ersetze ungültige Zeichen durch Unterstrich
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def find_or_create_folder(service, name, parent_id):
    """Findet einen Ordner oder erstellt ihn."""
    # Suche nach existierendem Ordner
    query = f"name='{name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    
    # Ordner erstellen
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')


def upload_base64_image(service, folder_id, filename, base64_data):
    """Lädt ein Base64-kodiertes Bild in Google Drive hoch."""
    # Base64 dekodieren (data:image/... prefix entfernen falls vorhanden)
    if ',' in base64_data:
        base64_data = base64_data.split(',', 1)[1]
    
    try:
        image_bytes = base64.b64decode(base64_data)
    except Exception as e:
        print(f"  ⚠️ Fehler beim Dekodieren von {filename}: {e}")
        return None
    
    # Datei hochladen
    file_metadata = {
        'name': filename,
        'parents': [folder_id]
    }
    media = MediaInMemoryUpload(image_bytes, mimetype='image/jpeg')
    
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id, webViewLink'
    ).execute()
    
    return file


def process_protocol(data):
    """Verarbeitet ein Fahrzeugprotokoll und lädt Fotos hoch."""
    print("🚗 Fahrzeugprotokoll Upload gestartet...")
    
    # Pflichtfelder prüfen
    plate = data.get('plate', '').strip()
    if not plate:
        return {"success": False, "error": "Kein Kennzeichen angegeben"}
    
    date = data.get('date', datetime.now().strftime('%d.%m.%Y'))
    time = data.get('time', datetime.now().strftime('%H:%M'))
    
    # Ordnernamen erstellen
    plate_folder_name = sanitize_filename(plate.upper())
    session_folder_name = f"{date.replace('.', '-')}_{time.replace(':', '-')}"
    
    print(f"📁 Kennzeichen: {plate_folder_name}")
    print(f"📁 Session: {session_folder_name}")
    
    # Google Drive Service
    service = get_drive_service()
    
    # Ordnerstruktur erstellen
    plate_folder_id = find_or_create_folder(service, plate_folder_name, PARENT_FOLDER_ID)
    session_folder_id = find_or_create_folder(service, session_folder_name, plate_folder_id)
    
    print(f"✅ Ordner erstellt/gefunden")
    
    uploaded_files = []
    
    # Pflichtfotos hochladen
    photos = data.get('photos', [])
    for i, photo in enumerate(photos, 1):
        title = photo.get('title', f'Foto_{i}')
        data_url = photo.get('dataUrl', '')
        
        if not data_url:
            continue
        
        filename = f"{i:02d}_{sanitize_filename(title)}.jpg"
        print(f"  📷 Lade hoch: {filename}")
        
        result = upload_base64_image(service, session_folder_id, filename, data_url)
        if result:
            uploaded_files.append({"name": filename, "id": result['id'], "link": result.get('webViewLink')})
    
    # Schadensfotos hochladen
    damages = data.get('damage', [])
    for i, damage in enumerate(damages, 1):
        damage_photos = damage.get('photos', [])
        area = damage.get('area', f'Schaden_{i}')
        
        for j, photo_url in enumerate(damage_photos, 1):
            filename = f"Schaden_{i:02d}_{sanitize_filename(area)}_{j}.jpg"
            print(f"  📷 Lade hoch: {filename}")
            
            result = upload_base64_image(service, session_folder_id, filename, photo_url)
            if result:
                uploaded_files.append({"name": filename, "id": result['id'], "link": result.get('webViewLink')})
    
    # Fotos aus Sichtprüfung (exterior/interior)
    for section_name, section_key in [('Aussen', 'exterior'), ('Innen', 'interior')]:
        items = data.get(section_key, [])
        for item in items:
            item_photos = item.get('photos', [])
            area = item.get('area', 'Unbekannt')
            
            for j, photo_url in enumerate(item_photos, 1):
                filename = f"{section_name}_{sanitize_filename(area)}_{j}.jpg"
                print(f"  📷 Lade hoch: {filename}")
                
                result = upload_base64_image(service, session_folder_id, filename, photo_url)
                if result:
                    uploaded_files.append({"name": filename, "id": result['id'], "link": result.get('webViewLink')})
    
    # Protokoll-JSON speichern (ohne Bilder, nur Metadaten)
    protocol_meta = {k: v for k, v in data.items() if k not in ['photos']}
    # Bilder aus nested objects entfernen
    if 'damage' in protocol_meta:
        for d in protocol_meta['damage']:
            d.pop('photos', None)
    if 'exterior' in protocol_meta:
        for e in protocol_meta['exterior']:
            e.pop('photos', None)
    if 'interior' in protocol_meta:
        for i in protocol_meta['interior']:
            i.pop('photos', None)
    
    json_bytes = json.dumps(protocol_meta, indent=2, ensure_ascii=False).encode('utf-8')
    file_metadata = {
        'name': 'protokoll.json',
        'parents': [session_folder_id]
    }
    media = MediaInMemoryUpload(json_bytes, mimetype='application/json')
    json_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    
    # Ordner-Link generieren
    folder_link = f"https://drive.google.com/drive/folders/{session_folder_id}"
    
    print(f"\n✅ Upload abgeschlossen!")
    print(f"📁 Ordner: {folder_link}")
    print(f"📷 {len(uploaded_files)} Fotos hochgeladen")
    
    return {
        "success": True,
        "plate": plate,
        "date": date,
        "time": time,
        "driveLink": folder_link,
        "folderId": session_folder_id,
        "uploadedFiles": len(uploaded_files),
        "files": uploaded_files
    }


def main():
    """Hauptfunktion - liest JSON von stdin oder Datei."""
    if len(sys.argv) > 1:
        # Datei als Argument
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        # Von stdin lesen
        data = json.load(sys.stdin)
    
    result = process_protocol(data)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return 0 if result.get('success') else 1


if __name__ == '__main__':
    sys.exit(main())
