#!/usr/bin/env python3
"""
Fahrzeugprotokoll Webhook Server
Empfängt Protokolle, lädt Fotos zu Google Drive und sendet Email.

Starten mit:
  python webhook_server.py

Endpoint:
  POST http://localhost:8085/webhook/fahrzeugprotokoll
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from process_protocol import process_protocol
import traceback

app = Flask(__name__)
CORS(app)  # Erlaubt Cross-Origin Requests


@app.route('/webhook/fahrzeugprotokoll', methods=['POST'])
def handle_protocol():
    """Empfängt ein Fahrzeugprotokoll und verarbeitet es."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"success": False, "error": "Keine JSON-Daten erhalten"}), 400
        
        result = process_protocol(data)
        
        if result.get('success'):
            return jsonify(result), 200
        else:
            return jsonify(result), 400
            
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health Check Endpoint."""
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    print("🚀 Fahrzeugprotokoll Webhook Server")
    print("📍 Endpoint: http://localhost:8085/webhook/fahrzeugprotokoll")
    app.run(host='0.0.0.0', port=8085, debug=False)
