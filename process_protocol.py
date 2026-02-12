#!/usr/bin/env python3
"""
Fahrzeugprotokoll - Kompletter Workflow
1. Empfängt Protokoll-Daten
2. Lädt Fotos nach Kennzeichen sortiert zu Google Drive (via gog OAuth)
3. Sendet Email mit Link an Empfänger
"""

import os
import sys
import json
import base64
import re
import smtplib
import subprocess
import tempfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path
from io import BytesIO

import weasyprint

from config import (
    PARENT_FOLDER_ID,
    EMAIL_TO, EMAIL_BCC, SMTP_SERVER, SMTP_PORT, 
    SMTP_USER, SMTP_PASSWORD, SMTP_FROM
)

# GOG OAuth Account
GOG_ACCOUNT = "planungalmastest@gmail.com"
os.environ["GOG_KEYRING_PASSWORD"] = "lexibot2026"


def sanitize_filename(name):
    """Entfernt ungültige Zeichen aus Dateinamen."""
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()


def find_folder(name, parent_id):
    """Sucht einen Ordner nach Name im Parent."""
    result = subprocess.run(
        ["/usr/local/bin/gog", "drive", "ls", parent_id, "--account", GOG_ACCOUNT],
        capture_output=True, text=True
    )
    for line in result.stdout.strip().split('\n')[1:]:  # Skip header
        if not line.strip():
            continue
        parts = line.split('\t')
        if len(parts) >= 3 and parts[1].strip() == name and parts[2].strip() == 'folder':
            return parts[0].strip()
    return None


def create_folder(name, parent_id):
    """Erstellt einen Ordner."""
    result = subprocess.run(
        ["/usr/local/bin/gog", "drive", "mkdir", name, "--parent", parent_id, "--account", GOG_ACCOUNT, "--json"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"mkdir error: {result.stderr}")
    data = json.loads(result.stdout)
    return data.get("id")


def find_or_create_folder(name, parent_id):
    """Findet oder erstellt einen Ordner."""
    folder_id = find_folder(name, parent_id)
    if folder_id:
        return folder_id
    return create_folder(name, parent_id)


def upload_file(filepath, parent_id, filename=None):
    """Lädt eine Datei hoch."""
    result = subprocess.run(
        ["/usr/local/bin/gog", "drive", "upload", filepath, "--parent", parent_id, "--account", GOG_ACCOUNT, "--json"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"upload error: {result.stderr}")
    data = json.loads(result.stdout)
    file_id = data.get("id")
    
    # Rename wenn gewünscht
    if filename and file_id:
        subprocess.run(
            ["/usr/local/bin/gog", "drive", "rename", file_id, filename, "--account", GOG_ACCOUNT],
            capture_output=True
        )
    
    return file_id, f"https://drive.google.com/file/d/{file_id}/view"


def upload_base64_image(folder_id, filename, data_url):
    """Lädt ein Base64-kodiertes Bild hoch."""
    # Extrahiere Daten aus data URL
    if ',' in data_url:
        header, b64data = data_url.split(',', 1)
    else:
        b64data = data_url
    
    try:
        image_data = base64.b64decode(b64data)
    except Exception as e:
        print(f"  ⚠️ Base64 Fehler: {filename}: {e}")
        return None
    
    # Speichere temporär
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
        f.write(image_data)
        temp_path = f.name
    
    try:
        file_id, link = upload_file(temp_path, folder_id, filename)
        return {"id": file_id, "webViewLink": link}
    except Exception as e:
        print(f"  ⚠️ Upload Fehler: {filename}: {e}")
        return None
    finally:
        os.unlink(temp_path)


def upload_json(folder_id, filename, data):
    """Lädt JSON-Daten als Datei hoch."""
    json_content = json.dumps(data, indent=2, ensure_ascii=False)
    
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w', encoding='utf-8') as f:
        f.write(json_content)
        temp_path = f.name
    
    try:
        file_id, link = upload_file(temp_path, folder_id, filename)
        return file_id
    finally:
        os.unlink(temp_path)


def generate_html_report(data):
    """Generiert HTML-Report mit allen Formulardaten inkl. eingebetteter Bilder."""
    plate = data.get('plate', '-')
    date = data.get('date', '-')
    time = data.get('time', '-')
    process = data.get('process', '-')
    employee = data.get('employee', '-')
    employee_email = data.get('employeeEmail', '-')
    model = data.get('model', '-')
    mileage = data.get('mileage', '-')
    location = data.get('location', '-')
    remarks = data.get('remarks', '-') or '-'
    
    # Helper: Fotos als HTML-Bilder
    def photos_to_html(photos):
        if not photos:
            return ""
        html = '<div class="photos">'
        for p in photos:
            if p:  # dataUrl vorhanden
                html += f'<img src="{p}" style="max-width:200px; max-height:150px; margin:5px; border:1px solid #ccc;">'
        html += '</div>'
        return html
    
    # Sichtprüfung außen mit Fotos
    exterior_rows = ""
    for item in data.get('exterior', []):
        area = item.get('area', '-')
        status = item.get('status', '-')
        comment = item.get('comment', '-') or '-'
        photos = item.get('photos', [])
        photos_html = photos_to_html(photos)
        exterior_rows += f"<tr><td>{area}</td><td>{status}</td><td>{comment}</td><td>{photos_html}</td></tr>"
    
    # Sichtprüfung innen mit Fotos
    interior_rows = ""
    for item in data.get('interior', []):
        area = item.get('area', '-')
        status = item.get('status', '-')
        comment = item.get('comment', '-') or '-'
        photos = item.get('photos', [])
        photos_html = photos_to_html(photos)
        interior_rows += f"<tr><td>{area}</td><td>{status}</td><td>{comment}</td><td>{photos_html}</td></tr>"
    
    # Schäden mit Fotos
    damage_rows = ""
    for d in data.get('damage', []):
        area = d.get('area', '-')
        desc = d.get('description', '-') or '-'
        photos = d.get('photos', [])
        photos_html = photos_to_html(photos)
        damage_rows += f"<tr><td>{area}</td><td>{desc}</td><td>{photos_html}</td></tr>"
    
    # Pflichtfotos
    pflicht_photos_html = ""
    for photo in data.get('photos', []):
        title = photo.get('title', '')
        data_url = photo.get('dataUrl', '')
        if data_url:
            pflicht_photos_html += f'''
            <div style="display:inline-block; margin:10px; text-align:center;">
                <img src="{data_url}" style="max-width:200px; max-height:150px; border:1px solid #ccc;">
                <br><small>{title}</small>
            </div>'''
    
    # Almas Logo als Base64 SVG
    almas_logo_b64 = "PHN2ZyBpZD0iQ2FscXVlXzEiIGRhdGEtbmFtZT0iQ2FscXVlIDEiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIgdmlld0JveD0iMCAwIDUzMS4zMiAxMDQuNzQiPjx0aXRsZT5sb2dvX2FsbWFzX2hvcml6b250YWw8L3RpdGxlPjxwYXRoIGQ9Ik0yNzEuOTEsNzMuNDNsMTUuNjQsMzIuMzhoLTkuMDhsLTIuNzUtNi4xSDI1OS4xMmwtMi43NSw2LjFoLTguODVsMTUuNjQtMzIuMzhaTTI2MS43Myw5NGgxMS4zOHMtNS4zNy0xMS42LTUuNjQtMTMuMTJDMjY3LjE5LDgxLjgyLDI2MS43Myw5NCwyNjEuNzMsOTRaIiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMzguNjIgLTcyLjQyKSIgc3R5bGU9ImZpbGw6IzFlMWYxZCIvPjxwYXRoIGQ9Ik0yOTkuMjksNzMuNDNWOTkuODVoMTh2NmgtMjYuMVY3My40M1oiIHRyYW5zZm9ybT0idHJhbnNsYXRlKC0zOC42MiAtNzIuNDIpIiBzdHlsZT0iZmlsbDojMWUxZjFkIi8+PHBhdGggZD0iTTM2NS4wNiwxMDUuODFoLTcuN2wuMTQtMjIuNjZhMTYuNTIsMTYuNTIsMCwwLDEsLjIzLTNjLS4yNy44Mi0uNTksMS42NS0uOTIsMi40N2wtOS42OCwyMy4yMWgtNy4zOEwzMzAuMSw4My4wNmMtLjI0LS41NS0uNDEtMS4wNi0uNi0xLjU2cy0uMjctLjkxLS40Mi0xLjM3Yy4wOSwxLC4xOSwxLjkyLjI0LDIuODhsLjA5LDIyLjhoLTcuN1Y3My40M2gxMS43NWw4LjQsMTkuODZhMjQuMjUsMjQuMjUsMCwwLDEsMS42NSw0Ljc3QTIzLjgsMjMuOCwwLDAsMSwzNDUsOTMuNjFsOC40NC0yMC4xOGgxMS42WiIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTM4LjYyIC03Mi40MikiIHN0eWxlPSJmaWxsOiMxZTFmMWQiLz48cGF0aCBkPSJNMzkzLjI1LDczLjQzbDE1LjY0LDMyLjM4aC05LjA4bC0yLjc1LTYuMUgzODAuNDVsLTIuNzUsNi4xaC04Ljg1bDE1LjY0LTMyLjM4Wk0zODMuMDYsOTRoMTEuMzhzLTUuMzctMTEuNi01LjY0LTEzLjEyQzM4OC41Miw4MS44MiwzODMuMDYsOTQsMzgzLjA2LDk0WiIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTM4LjYyIC03Mi40MikiIHN0eWxlPSJmaWxsOiMxZTFmMWQiLz48cGF0aCBkPSJNNDM2LjMxLDgyLjFhNS4xNiw1LjE2LDAsMCwwLS43NC0xLjA1Yy0yLTIuMzMtNS43OC0yLjg0LTguNjItMi44NGExNy40OSwxNy40OSwwLDAsMC0yLjcxLjE5Yy0uMjcsMC00LjU0LjM3LTQuNTQsMy41NywwLDEuNjUsMS4xNSwyLjM0LDIuNTcsMi44LDIuMjkuNjgsOC4wNywxLjUxLDEwLjQxLDJhMjkuNTIsMjkuNTIsMCwwLDEsNC40LDFjMS44OC42NSw2LjUyLDIuMjksNi41Miw4LjMsMCwyLjk0LTEuMDUsNy41Ny03LjY2LDkuNjhhMjYuODQsMjYuODQsMCwwLDEtNS4zNywxYy0xLjE1LjA5LTIuMjkuMTQtMy40NC4xNC01Ljc4LDAtOS0xLjE5LTExLjI5LTIuNDRhMTQuNDgsMTQuNDgsMCwwLDEtNS42NC01LjMyLDEwLjcxLDEwLjcxLDAsMCwxLS43OC0xLjM4bDcuMzktMS44OGMxLjkyLDQsNi45Myw1LjA1LDEwLjg3LDUuMDUuMzMsMCw0LjQsMCw2LjYxLTEuNDdhMy40NCwzLjQ0LDAsMCwwLDEuNTYtMi44LDIuNjEsMi42MSwwLDAsMC0xLjA2LTIuMTZjLTEtLjc4LTMuMTItMS4wOS02LjA1LTEuNTUtNi0uOTItOS4xNy0xLjM3LTExLjc5LTIuNjJhOC40Miw4LjQyLDAsMCwxLTUuMDktNy43LDguNjcsOC42NywwLDAsMSwzLjk0LTcuMzRjMi4wNy0xLjQyLDUuNDItMi44LDExLjE5LTIuOCw1LjUxLDAsOC40NCwxLDEwLjczLDIuMDZhMTMuODIsMTMuODIsMCwwLDEsNCwyLjc1LDEzLjY3LDEzLjY3LDAsMCwxLDIuMiwyLjk0WiIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTM4LjYyIC03Mi40MikiIHN0eWxlPSJmaWxsOiMxZTFmMWQiLz48cGF0aCBkPSJNMjUwLjU0LDExOS41MnYzMS43aC0zdi0zMS43WiIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTM4LjYyIC03Mi40MikiIHN0eWxlPSJmaWxsOiMxZTFmMWQiLz48cGF0aCBkPSJNMjkyLjEsMTUxLjIyaC0yLjgybC0yNy4xNi0yNy42NnYyNy42NmgtMi44M3YtMzEuN2gyLjgzbDI3LjE2LDI3Ljc5VjExOS41MmgyLjgyWiIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTM4LjYyIC03Mi40MikiIHN0eWxlPSJmaWxsOiMxZTFmMWQiLz48cGF0aCBkPSJNMzE3LjI0LDExOS41MmMuOTQsMCwxLjg4LDAsMi44Mi4wOWExNC4xMywxNC4xMywwLDAsMSw4LjM1LDMuMTljNS4xMiw0LjIyLDUuMzksMTAuNjksNS4zOSwxMi42N2ExOS42MiwxOS42MiwwLDAsMS0uNjMsNC45NCwxMy44NiwxMy44NiwwLDAsMS03LjQ1LDkuMmMtMy4yMywxLjQ4LTYuNTUsMS41OC0xMCwxLjYySDMwMS4zOXYtMzEuN1ptLTEyLjcxLDI5aDEwLjFjNC4yNywwLDkuMDctLjA5LDEyLjM5LTMuMjMsMS43MS0xLjYyLDMuNTktNC40OSwzLjU5LTkuN1MzMjguMzcsMTI1LDMyMywxMjNhMTUuOTEsMTUuOTEsMCwwLDAtNS43OS0uOUgzMDQuNTNaIiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMzguNjIgLTcyLjQyKSIgc3R5bGU9ImZpbGw6IzFlMWYxZCIvPjxwYXRoIGQ9Ik0zNzIuNTgsMTE5LjUydjE5YTE0Ljc4LDE0Ljc4LDAsMCwxLTEuODksNy44MWMtMS44NCwzLTQuNjIsNC4zNS03Ljk1LDUuMTJhMjYuNjksMjYuNjksMCwwLDEtNS44OC41OCwyOS43MSwyOS43MSwwLDAsMS03LjgxLS45NCwxMSwxMSwwLDAsMS03Ljc3LTYuODMsMTkuMzksMTkuMzksMCwwLDEtLjgtNi40MlYxMTkuNTJoMi45MnYxNy4wNmMwLDMtLjEzLDYsMS43MSw4LjU3LDEuNjEsMi4yNSw0Ljg5LDQsMTAuNzMsNCw3LjEzLDAsMTAuNjUtMS4zOSwxMi41My00LjY3LDEuMDgtMS44OSwxLjM1LTQsMS4zNS04LjIyVjExOS41MloiIHRyYW5zZm9ybT0idHJhbnNsYXRlKC0zOC42MiAtNzIuNDIpIiBzdHlsZT0iZmlsbDojMWUxZjFkIi8+PHBhdGggZD0iTTQwOC41NCwxMjYuNDNjLS4yNy0uMzYtLjYzLS44MS0uOTUtMS4xNy0yLjkxLTMtNy4yNy0zLjg2LTExLjI3LTMuODYtLjksMC01LjA3LDAtOC4yMSwxLjgzYTYuNDksNi40OSwwLDAsMC0yLjMzLDIuMjZhNC41OSw0LjU5LDAsMCwwLS41OSwyLjI0LDMuNzUsMy43NSwwLDAsMCwyLjQ3LDMuNDFjMS4zNS42MywyLjg3Ljg1LDUuODgsMS4yNiw2LjkyLDEsMTEuMzIsMS40NCwxNC4xLDIuNjVhNy4yNCw3LjI0LDAsMCwxLDQuNzIsNi43NCw4LjU2LDguNTYsMCwwLDEtMS40OCw0LjcxYy0yLDIuODctNi4yNCw1LjUyLTE0LDUuNTItLjg5LDAtMS43OS0uMDUtMi43NC0uMDktMS4zNS0uMDgtOC0uNC0xMS45NC00LjYyYTE3LjQzLDE3LjQzLDAsMCwxLTIuNjktNGwzLjMyLTEuMjZhOS45NCw5Ljk0LDAsMCwwLDMuNzcsNC44OWMxLjg1LDEuMjIsNSwyLjM0LDEwLjA2LDIuMzQsMS4yMSwwLDUuNTcsMCw5LjA3LTIuMDcsMS45My0xLjE3LDMuMzctMi44NywzLjM3LTUuMjFhNC4xNCw0LjE0LDAsMCwwLTEuNDktMy4zMmMtMi0xLjY3LTcuNC0yLjI1LTkuNzQtMi41Ni0xLjkzLS4yNy0zLjg2LS40OS01Ljc1LS43NmEyMi40OCwyMi40OCwwLDAsMS02LjM3LTEuNTcsNi40OCw2LjQ4LDAsMCwxLTMuNzctNS44OCw4LjMsOC4zLDAsMCwxLDQuNTMtN2MyLjgzLTEuNTYsNi44Ny0yLjE1LDEwLjA2LTIuMTUsMS45MywwLDcuOTQuMTQsMTIuNyw0YTE1LjE1LDE1LjE1LDAsMCwxLDIuMTUsMi4yWiIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTM4LjYyIC03Mi40MikiIHN0eWxlPSJmaWxsOiMxZTFmMWQiLz48cGF0aCBkPSJNNDQ0LjM1LDExOS41MnYyLjZoLTEzLjZ2MjkuMDloLTNWMTIyLjEySDQxMy41MXYtMi42WiIgdHJhbnNmb3JtPSJ0cmFuc2xhdGUoLTM4LjYyIC03Mi40MikiIHN0eWxlPSJmaWxsOiMxZTFmMWQiLz48cGF0aCBkPSJNNDgyLjUxLDE1MS4yMmgtNC4yNmwtMTIuNTMtMTQuMTRoLTE0LjV2MTQuMTRoLTMuMDZ2LTMxLjdoMjEuOTFjLjc2LDAsMS41MywwLDIuMywwLDEuMywwLDUsLjIyLDcuMjcsMy42M2E5LjI3LDkuMjcsMCwwLDEsMS4zOSw1LDguMzYsOC4zNiwwLDAsMS0zLjIyLDYuODJjLTIuMzksMS43NS01LjI2LDEuODktOCwyWm0tMzEuMjktMTYuODRoMTdjLjcyLDAsMS4zOSwwLDIuMTEsMCwyLjY1LS4xNCw1LjMtLjU4LDYuNjUtMy4yM2E3LjE4LDcuMTgsMCwwLDAsLjcyLTMuMDUsNi4wOSw2LjA5LDAsMCwwLTIuNDMtNC45Yy0xLjU3LTEtMy4zMi0xLTUuMTItMUg0NTEuMjJaIiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMzguNjIgLTcyLjQyKSIgc3R5bGU9ImZpbGw6IzFlMWYxZCIvPjxwYXRoIGQ9Ik00OTIuMjgsMTE5LjUydjMxLjdoLTN2LTMxLjdaIiB0cmFuc2Zvcm09InRyYW5zbGF0ZSgtMzguNjIgLTcyLjQyKSIgc3R5bGU9ImZpbGw6IzFlMWYxZCIvPjxwYXRoIGQ9Ik01MzEuMzksMTE5LjUydjIuNkg1MDQuMTN2MTEuMTNoMjUuMTlWMTM2SDUwNC4xM3YxMi42MmgyOC41NnYyLjY1SDUwMXYtMzEuN1oiIHRyYW5zZm9ybT0idHJhbnNsYXRlKC0zOC42MiAtNzIuNDIpIiBzdHlsZT0iZmlsbDojMWUxZjFkIi8+PHBhdGggZD0iTTU2Ni4xMiwxMjYuNDNjLS4yNy0uMzYtLjYzLS44MS0uOTQtMS4xNy0yLjkyLTMtNy4yNy0zLjg2LTExLjI3LTMuODYtLjksMC01LjA4LDAtOC4yMiwxLjgzYTYuNjQsNi42NCwwLDAsMC0yLjM0LDIuMjYsNC43Nyw0Ljc3LDAsMCwwLS41OCwyLjI0LDMuNzYsMy43NiwwLDAsMCwyLjQ3LDMuNDFjMS4zNS42MywyLjg4Ljg1LDUuODgsMS4yNiw2LjkyLDEsMTEuMzIsMS40NCwxNC4xLDIuNjVhNy4yMyw3LjIzLDAsMCwxLDQuNzIsNi43NCw4LjU2LDguNTYsMCwwLDEtMS40OCw0LjcxYy0yLDIuODctNi4yNCw1LjUyLTE0LDUuNTItLjg5LDAtMS43OS0uMDUtMi43NC0uMDktMS4zNC0uMDgtOC0uNC0xMS45NC00LjYyYTE3LjA2LDE3LjA2LDAsMCwxLTIuNy00TDU0MC40LDE0MmE5Ljk0LDkuOTQsMCwwLDAsMy43Nyw0Ljg5YzEuODQsMS4yMiw1LDIuMzQsMTAuMDUsMi4zNCwxLjIxLDAsNS41NywwLDkuMDctMi4wNywxLjkyLTEuMTcsMy4zNy0yLjg3LDMuMzctNS4yMWE0LjE5LDQuMTksMCwwLDAtMS40OC0zLjMyYy0yLTEuNjctNy40MS0yLjI1LTkuNzQtMi41Ni0xLjkzLS4yNy0zLjg2LS40OS01Ljc1LS43NmEyMi41MiwyMi41MiwwLDAsMS02LjM3LTEuNTcsNi40OCw2LjQ4LDAsMCwxLTMuNzctNS44OCw4LjMsOC4zLDAsMCwxLDQuNTQtN2MyLjgyLTEuNTYsNi44Ni0yLjE1LDEwLjA2LTIuMTUsMS45MywwLDgsLjE0LDEyLjcsNGExNS41OSwxNS41OSwwLDAsMSwyLjE2LDIuMloiIHRyYW5zZm9ybT0idHJhbnNsYXRlKC0zOC42MiAtNzIuNDIpIiBzdHlsZT0iZmlsbDojMWUxZjFkIi8+PHJlY3QgeD0iMjA5LjA4IiB5PSI5Ni43NSIgd2lkdGg9IjE5Ni41OSIgaGVpZ2h0PSI3Ljk5IiBzdHlsZT0iZmlsbDojZTQwMzJlIi8+PHBhdGggZD0iTTM4LjYyLDE2MS41M2wxNS40OSw2LjU4LS40LTMuODUtMi4zNS00LjY3LDUtMy4zMywxOS4yMS04LjQyLDkuNjQsMjcuNTRMMTExLDE2OWwtMi4xMS0yLjg2LTctMS4xOC0zLjQ1LTUuMDlMMTAxLDE0Ni4xM2wtLjgtNi44NywyNy42LTIuNC0uODgsNS4yOS0zLjI2LDcuMTEsMi4wOCw3LTMuNTMsMTUuNDUsMjYuNjEtLjMyLTEtMy4wNy01Ljg4LTIuMDYtMy4zLTQuNDJMMTQ5LDEzOS4yNmw1LjQyLS43Nyw5LTUuMTEsNi43NiwxMS4xMywxMC4zLDE0LjE3LDMuMTcsNy41OCwxMS42Niw1LjkxLDI0LjI4LS40Ni01LjgtNS4wNy04LjQ2LTEuMjktMTUtMzQuMTZjLS41MS00LjI5LTEuMzctMTIuODMtMS4zNy0xMi44M2wxNy40Ny0xMi42LDQuMzctNy40NCwxMS4zMS02Ljg3LDEuNTktNS0uMTgtMy41OGgtOC4ybC0zLjc0LTQuNThIMjA2LjJsLTYuMzEtLjctOC4xLS40NS0yLjg2LTMuNDRoLTIuNThsLTIuODYsMnYyLjg2bC0xLDIuNzYtNy44NCwzTDE2Ni45MSw4MmwtMjAuNzYsNEw5NC41OSw4MS4yOCw2Ny40NCw5OS42NmMtLjUzLjctNy4wNSwzMS4xOS03LjA1LDMxLjE5TDQ4LjA4LDE0MS4yN1oiIHRyYW5zZm9ybT0idHJhbnNsYXRlKC0zOC42MiAtNzIuNDIpIiBzdHlsZT0iZmlsbDojZTQwMzJlIi8+PC9zdmc+"
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Fahrzeugprotokoll {plate}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 3px solid #e4032e; padding-bottom: 15px; }}
        .logo {{ max-width: 200px; height: auto; }}
        h1 {{ color: #1e1f1d; margin: 0; }}
        h2 {{ color: #333; border-bottom: 2px solid #e4032e; padding-bottom: 5px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f5f5f5; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }}
        .info-item {{ padding: 10px; background: #f9f9f9; }}
        .label {{ font-weight: bold; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <img src="data:image/svg+xml;base64,{almas_logo_b64}" class="logo" alt="ALMAS INDUSTRIES">
        <h1>Fahrzeugzustandsprotokoll</h1>
    </div>
    
    <h2>Allgemeine Angaben</h2>
    <div class="info-grid">
        <div class="info-item"><span class="label">Vorgang:</span> {process}</div>
        <div class="info-item"><span class="label">Datum:</span> {date} um {time}</div>
        <div class="info-item"><span class="label">Standort:</span> {location}</div>
        <div class="info-item"><span class="label">Mitarbeiter:</span> {employee}</div>
        <div class="info-item"><span class="label">E-Mail:</span> {employee_email}</div>
    </div>
    
    <h2>Fahrzeugdaten</h2>
    <div class="info-grid">
        <div class="info-item"><span class="label">Kennzeichen:</span> {plate}</div>
        <div class="info-item"><span class="label">Marke/Modell:</span> {model}</div>
        <div class="info-item"><span class="label">Kilometerstand:</span> {mileage} km</div>
    </div>
    <p><strong>Bemerkungen:</strong> {remarks}</p>
    
    <h2>Sichtprüfung außen</h2>
    <table>
        <tr><th>Bereich</th><th>Zustand</th><th>Bemerkung</th><th>Fotos</th></tr>
        {exterior_rows if exterior_rows else "<tr><td colspan='4'>Keine Einträge</td></tr>"}
    </table>
    
    <h2>Sichtprüfung innen</h2>
    <table>
        <tr><th>Bereich</th><th>Zustand</th><th>Bemerkung</th><th>Fotos</th></tr>
        {interior_rows if interior_rows else "<tr><td colspan='4'>Keine Einträge</td></tr>"}
    </table>
    
    <h2>Schäden/Mängel</h2>
    <table>
        <tr><th>Bereich</th><th>Beschreibung</th><th>Fotos</th></tr>
        {damage_rows if damage_rows else "<tr><td colspan='3'>Keine Schäden dokumentiert</td></tr>"}
    </table>
    
    <h2>Pflichtfotos</h2>
    {pflicht_photos_html if pflicht_photos_html else "<p>Keine Pflichtfotos vorhanden</p>"}
    
    <h2>Unterschrift Mitarbeiter</h2>
    {f'<img src="{data.get("signatures", {}).get("employee", "")}" style="max-width:300px; border:1px solid #ccc;">' if data.get("signatures", {}).get("employee") else "<p>Keine Unterschrift</p>"}
    
    <p style="margin-top: 30px; color: #666; font-size: 12px;">
        Erstellt am {date} um {time} | Fahrzeugprotokoll-System
    </p>
</body>
</html>"""
    return html


def send_email(data, folder_link, uploaded_count):
    """Sendet Email mit Protokoll-Zusammenfassung und PDF-Anhang."""
    plate = data.get('plate', 'Unbekannt')
    date = data.get('date', '-')
    time = data.get('time', '-')
    process = data.get('process', '-')
    employee = data.get('employee', '-')
    model = data.get('model', '-')
    mileage = data.get('mileage', '-')
    location = data.get('location', '-')
    
    subject = f"Fahrzeugprotokoll: {plate} - {process} ({date})"
    
    body = f"""Fahrzeugprotokoll

Vorgang: {process}
Datum: {date} um {time}
Standort: {location}

Fahrzeug:
  Kennzeichen: {plate}
  Modell: {model}
  Kilometerstand: {mileage}

Mitarbeiter: {employee}

Das komplette Protokoll finden Sie im Anhang.

Mit freundlichen Grüßen
Joshua
"""
    
    msg = MIMEMultipart()
    msg['From'] = SMTP_FROM
    msg['To'] = EMAIL_TO
    msg['Subject'] = subject
    
    # CC: Mitarbeiter-Email falls vorhanden
    employee_email = data.get('employeeEmail', '').strip()
    if employee_email and '@' in employee_email:
        msg['Cc'] = employee_email
    
    # Empfängerliste für sendmail (To + CC + BCC)
    all_recipients = [EMAIL_TO, EMAIL_BCC]
    if employee_email and '@' in employee_email:
        all_recipients.append(employee_email)
    
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    # HTML-Report generieren und zu PDF konvertieren
    html_report = generate_html_report(data)
    safe_plate = sanitize_filename(plate)
    filename = f'Fahrzeugprotokoll_{safe_plate}_{date.replace(".", "-")}.pdf'
    
    try:
        # HTML → PDF mit WeasyPrint
        pdf_bytes = weasyprint.HTML(string=html_report).write_pdf()
        
        pdf_attachment = MIMEBase('application', 'pdf')
        pdf_attachment.set_payload(pdf_bytes)
        encoders.encode_base64(pdf_attachment)
        pdf_attachment.add_header('Content-Disposition', 'attachment', filename=filename)
        msg.attach(pdf_attachment)
        print(f"📄 PDF erstellt: {filename} ({len(pdf_bytes)} bytes)")
    except Exception as e:
        print(f"⚠️ PDF-Konvertierung fehlgeschlagen: {e}")
        # Fallback: HTML als Anhang
        html_attachment = MIMEBase('text', 'html')
        html_attachment.set_payload(html_report.encode('utf-8'))
        encoders.encode_base64(html_attachment)
        html_attachment.add_header('Content-Disposition', 'attachment', 
                                   filename=filename.replace('.pdf', '.html'))
        msg.attach(html_attachment)
        print("📄 Fallback: HTML-Anhang verwendet")
    
    # Senden
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, all_recipients, msg.as_string())
        cc_info = f", CC: {employee_email}" if employee_email and '@' in employee_email else ""
        print(f"✅ Email gesendet an: {EMAIL_TO}{cc_info} (BCC: {EMAIL_BCC})")
        return True
    except Exception as e:
        print(f"❌ Email-Fehler: {e}")
        return False


def process_protocol(data):
    """Hauptfunktion - verarbeitet komplettes Protokoll."""
    print("🚗 Fahrzeugprotokoll wird verarbeitet...")
    
    # DEBUG: Was kommt an?
    photos = data.get('photos', [])
    with open('/tmp/fahrzeug_debug.log', 'w') as f:
        f.write(f"📷 Anzahl Fotos erhalten: {len(photos)}\n")
        for i, p in enumerate(photos):
            has_data = bool(p.get('dataUrl'))
            data_len = len(p.get('dataUrl', '')) if has_data else 0
            f.write(f"  Foto {i+1}: {p.get('title', '?')} - dataUrl: {data_len} Zeichen\n")
        f.write(f"\nKeys im data: {list(data.keys())}\n")
    
    plate = data.get('plate', '').strip() or 'TEST'
    date = data.get('date', datetime.now().strftime('%d.%m.%Y'))
    time = data.get('time', datetime.now().strftime('%H:%M'))
    
    print(f"📋 Kennzeichen: {plate}")
    print(f"📅 Datum: {date} {time}")
    
    # TESTMODUS: Kein Upload, nur Email
    uploaded_files = []
    folder_link = "(Upload deaktiviert - Testmodus)"
    
    print(f"\n📧 Sende Email...")
    
    # Email senden
    send_email(data, folder_link, len(uploaded_files))
    
    return {
        "success": True,
        "plate": plate,
        "date": date,
        "time": time,
        "driveLink": folder_link,
        "uploadedFiles": len(uploaded_files),
        "testMode": True
    }


if __name__ == '__main__':
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)
    
    result = process_protocol(data)
    print(json.dumps(result, indent=2, ensure_ascii=False))
