#!/usr/bin/env python3
"""
Google Drive Upload via gog CLI (OAuth statt Service Account)
"""

import os
import subprocess
import json
import tempfile
import base64

GOG_ACCOUNT = "planungalmastest@gmail.com"
os.environ["GOG_KEYRING_PASSWORD"] = "lexibot2026"

def run_gog(args):
    """Führt gog Befehl aus und gibt Ergebnis zurück."""
    cmd = ["gog"] + args + ["--account", GOG_ACCOUNT, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"gog error: {result.stderr}")
    try:
        return json.loads(result.stdout)
    except:
        return result.stdout

def find_folder(name, parent_id):
    """Sucht einen Ordner nach Name im Parent."""
    result = subprocess.run(
        ["gog", "drive", "ls", parent_id, "--account", GOG_ACCOUNT],
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
        ["gog", "drive", "mkdir", name, "--parent", parent_id, "--account", GOG_ACCOUNT, "--json"],
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

def upload_file(filepath, parent_id):
    """Lädt eine Datei hoch."""
    result = subprocess.run(
        ["gog", "drive", "upload", filepath, "--parent", parent_id, "--account", GOG_ACCOUNT, "--json"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise Exception(f"upload error: {result.stderr}")
    data = json.loads(result.stdout)
    return data.get("id"), data.get("webViewLink", f"https://drive.google.com/file/d/{data.get('id')}/view")

def upload_base64_image(parent_id, filename, data_url):
    """Lädt ein Base64-kodiertes Bild hoch."""
    # Extrahiere Daten aus data URL
    if ',' in data_url:
        header, b64data = data_url.split(',', 1)
    else:
        b64data = data_url
    
    # Dekodiere und speichere temporär
    image_data = base64.b64decode(b64data)
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
        f.write(image_data)
        temp_path = f.name
    
    try:
        file_id, link = upload_file(temp_path, parent_id)
        # Rename
        subprocess.run(
            ["gog", "drive", "rename", file_id, filename, "--account", GOG_ACCOUNT],
            capture_output=True
        )
        return file_id, link
    finally:
        os.unlink(temp_path)


if __name__ == "__main__":
    # Test
    print(find_folder("test", "1ZDx6daN3XrfZiB_6DNaf8sg0MFsiqpwk"))
