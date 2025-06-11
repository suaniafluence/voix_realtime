#!/usr/bin/env python3
"""
Application Web Flask pour Assistant Vocal OpenAI Realtime
Interface web moderne avec gestion audio bidirectionnelle côté navigateur
"""

import os
import sys
import json
import queue
import threading
import websocket
import numpy as np
import base64
import wave
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging
from dotenv import load_dotenv
import uuid

# Force UTF-8 encoding pour Windows
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())

load_dotenv()

# Configuration Flask
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Configuration logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Variables globales OpenAI
API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = os.getenv("MODEL", "gpt-4o-realtime-preview-2024-10-01")
INSTRUCTIONS = os.getenv("INSTRUCTIONS", "Vous êtes un assistant vocal intelligent en français. Répondez de manière concise et utile.")

# Variables d'authentification
AUTH_USERNAME = os.getenv("MON_USERNAME")
AUTH_PASSWORD = os.getenv("PASSWORD")

if not API_KEY:
    logger.error("OPENAI_API_KEY manquant dans .env")
    sys.exit(1)

if not AUTH_USERNAME or not AUTH_PASSWORD:
    logger.warning("MON_USERNAME ou PASSWORD manquant dans .env - Authentification simplifiée activée")
    AUTH_USERNAME = None
    AUTH_PASSWORD = None

# Stockage des sessions actives
active_sessions = {}
session_events = {}

class VoiceSession:
    """Classe pour gérer une session de dialogue vocal avec OpenAI"""
    
    def __init__(self, session_id):
        self.session_id = session_id
        self.ws = None
        self.openai_session_id = None
        self.conversation_id = None
        self.is_connected = False
        self.is_ready = False
        self.audio_log = []
        self.events = []
        self.stats = {
            'start_time': time.time(),
            'chunks_sent': 0,
            'chunks_received': 0,
            'bytes_sent': 0,
            'bytes_received': 0,
            'messages_count': 0
        }
        self.stop_event = threading.Event()
        
    def add_event(self, event_type, data, level='info'):
        """Ajoute un événement au journal"""
        event = {
            'timestamp': datetime.now().strftime('%H:%M:%S.%f')[:-3],
            'type': event_type,
            'level': level,
            'data': data
        }
        self.events.append(event)
        
        # Garder seulement les 100 derniers événements
        if len(self.events) > 100:
            self.events = self.events[-100:]
        
        # Émettre l'événement via WebSocket
        socketio.emit('new_event', event, room=self.session_id)
        
    def update_stats(self, stat_type, value):
        """Met à jour les statistiques"""
        if stat_type in self.stats:
            if stat_type.endswith('_count'):
                self.stats[stat_type] += 1
            else:
                self.stats[stat_type] += value
        
        # Émettre les stats mises à jour
        stats_with_duration = self.stats.copy()
        stats_with_duration['duration'] = time.time() - self.stats['start_time']
        socketio.emit('stats_update', stats_with_duration, room=self.session_id)

    def on_open(self, ws):
        """Callback d'ouverture WebSocket OpenAI"""
        self.is_connected = True
        self.add_event('websocket', 'Connexion WebSocket ouverte avec OpenAI')
        
        # Configuration de la session
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "voice": "alloy",
                "instructions": INSTRUCTIONS,
                "turn_detection": {"type": "server_vad", "threshold": 0.5},
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "whisper-1"}
            }
        }
        
        ws.send(json.dumps(config))
        self.add_event('config', 'Configuration de session envoyée')

    def on_message(self, ws, message):
        """Callback de réception de message OpenAI"""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "unknown")
            
            if msg_type == "session.created":
                self.openai_session_id = data.get("session", {}).get("id")
                self.add_event('session', f'Session OpenAI créée: {self.openai_session_id}')
                
            elif msg_type == "session.updated":
                self.is_ready = True
                self.add_event('session', 'Session prête pour l\'audio')
                socketio.emit('session_ready', {'ready': True}, room=self.session_id)
                
            elif msg_type == "conversation.created":
                self.conversation_id = data.get("conversation", {}).get("id")
                self.add_event('conversation', f'Nouvelle conversation: {self.conversation_id}')
                
            elif msg_type == "input_audio_buffer.speech_started":
                self.add_event('speech', 'Début de parole détecté', 'success')
                socketio.emit('speech_status', {'speaking': True}, room=self.session_id)
                
            elif msg_type == "input_audio_buffer.speech_stopped":
                self.add_event('speech', 'Fin de parole détecté', 'success')
                socketio.emit('speech_status', {'speaking': False}, room=self.session_id)
                
            elif msg_type == "conversation.item.input_audio_transcription.completed":
                transcript = data.get("transcript", "")
                self.add_event('transcript', f'Vous: "{transcript}"', 'primary')
                
            elif msg_type == "response.created":
                response_id = data.get("response", {}).get("id")
                self.add_event('response', f'Génération de réponse: {response_id}')
                
            elif msg_type == "response.audio.delta":
                audio_bytes = base64.b64decode(data["delta"])
                self.audio_log.append(audio_bytes)
                self.update_stats('chunks_received', 1)
                self.update_stats('bytes_received', len(audio_bytes))
                
                # Envoyer l'audio au navigateur client
                audio_b64 = base64.b64encode(audio_bytes).decode()
                socketio.emit('audio_output', {'audio': audio_b64}, room=self.session_id)
                
            elif msg_type == "response.audio.done":
                self.add_event('audio', 'Audio de réponse terminé', 'success')
                
            elif msg_type == "response.done":
                self.add_event('response', 'Réponse complète', 'success')
                self.update_stats('messages_count', 1)
                
            elif msg_type == "error":
                error_msg = data.get("error", {})
                self.add_event('error', f'Erreur OpenAI: {error_msg}', 'error')
                
        except Exception as e:
            self.add_event('error', f'Erreur traitement message: {str(e)}', 'error')

    def on_error(self, ws, error):
        """Callback d'erreur WebSocket"""
        self.add_event('error', f'Erreur WebSocket: {str(error)}', 'error')

    def on_close(self, ws, close_status_code, close_msg):
        """Callback de fermeture WebSocket"""
        self.is_connected = False
        self.is_ready = False
        self.add_event('websocket', f'Connexion fermée (code: {close_status_code})')
        socketio.emit('session_disconnected', {}, room=self.session_id)

    def send_audio(self, audio_data):
        """Envoie de l'audio reçu du navigateur vers OpenAI"""
        if not self.is_ready or not self.ws:
            return False
        
        try:
            message = {
                "type": "input_audio_buffer.append",
                "audio": audio_data  # Déjà en base64
            }
            
            self.ws.send(json.dumps(message))
            # Décoder pour calculer la taille réelle
            audio_bytes = base64.b64decode(audio_data)
            self.update_stats('chunks_sent', 1)
            self.update_stats('bytes_sent', len(audio_bytes))
            return True

        except Exception as e:
            self.add_event('error', f'Erreur envoi audio: {str(e)}', 'error')
            return False

    def stop_audio(self):
        """Signale la fin d'une séquence audio à OpenAI"""
        if not self.is_ready or not self.ws:
            return False

        try:
            self.ws.send(json.dumps({"type": "input_audio.buffer.stop"}))
            self.add_event('audio', 'Fin de parole envoyée', 'info')
            return True

        except Exception as e:
            self.add_event('error', f'Erreur stop audio: {str(e)}', 'error')
            return False

    def start_connection(self):
        """Démarre la connexion WebSocket avec OpenAI"""
        try:
            url = f"wss://api.openai.com/v1/realtime?model={MODEL}"
            headers = [
                f"Authorization: Bearer {API_KEY}",
                "OpenAI-Beta: realtime=v1"
            ]
            
            self.ws = websocket.WebSocketApp(
                url, header=headers,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            
            # Lancer dans un thread séparé
            def run_websocket():
                self.ws.run_forever()
            
            threading.Thread(target=run_websocket, daemon=True).start()
            self.add_event('websocket', 'Connexion WebSocket initiée')
            return True
            
        except Exception as e:
            self.add_event('error', f'Erreur démarrage WebSocket: {str(e)}', 'error')
            return False

    def disconnect(self):
        """Ferme la connexion"""
        self.stop_event.set()
        
        if self.ws:
            self.ws.close()
        
        # Sauvegarder l'audio si disponible
        if self.audio_log:
            try:
                final_audio = b''.join(self.audio_log)
                filename = f"dialogue_{self.session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
                filepath = os.path.join('static', 'recordings', filename)
                
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                with wave.open(filepath, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(24000)
                    wf.writeframes(final_audio)
                
                self.add_event('save', f'Audio sauvegardé: {filename}', 'success')
                
            except Exception as e:
                self.add_event('error', f'Erreur sauvegarde audio: {str(e)}', 'error')

# Routes Flask
@app.route('/')
def login():
    """Page de connexion"""
    return render_template('login.html')

@app.route('/voice')
def voice_interface():
    """Interface principale de l'assistant vocal"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('voice_interface.html')

@app.route('/login', methods=['POST'])
def do_login():
    """Traitement de la connexion"""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    
    # Si les variables d'environnement sont définies, les utiliser pour l'authentification
    if AUTH_USERNAME and AUTH_PASSWORD:
        if username == AUTH_USERNAME and password == AUTH_PASSWORD:
            session['user_id'] = username
            session['session_id'] = str(uuid.uuid4())
            logger.info(f"CONNECT: Utilisateur connecté: {username}")
            return redirect(url_for('voice_interface'))
        else:
            logger.warning(f"CONNECT: Tentative de connexion échouée pour: {username}")
            return render_template('login.html', error="Nom d'utilisateur ou mot de passe incorrect")
    else:
        # Mode simplifié : juste un nom d'utilisateur
        if username and len(username) >= 2:
            session['user_id'] = username
            session['session_id'] = str(uuid.uuid4())
            logger.info(f"CONNECT: Utilisateur connecté (mode simple): {username}")
            return redirect(url_for('voice_interface'))
        else:
            return render_template('login.html', error="Veuillez entrer un nom d'au moins 2 caractères")
    
    return render_template('login.html', error="Erreur de connexion")

@app.route('/logout')
def logout():
    """Déconnexion"""
    session_id = session.get('session_id')
    if session_id and session_id in active_sessions:
        active_sessions[session_id].disconnect()
        del active_sessions[session_id]
    
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/start_dialogue', methods=['POST'])
def start_dialogue():
    """Démarre une nouvelle session de dialogue"""
    if 'user_id' not in session:
        return jsonify({'error': 'Non connecté'}), 401
    
    session_id = session.get('session_id')
    
    if session_id in active_sessions:
        return jsonify({'error': 'Session déjà active'}), 400
    
    voice_session = VoiceSession(session_id)
    active_sessions[session_id] = voice_session
    
    if voice_session.start_connection():
        return jsonify({'success': True, 'session_id': session_id})
    else:
        del active_sessions[session_id]
        return jsonify({'error': 'Erreur démarrage connexion'}), 500

@app.route('/api/stop_dialogue', methods=['POST'])
def stop_dialogue():
    """Arrête la session de dialogue"""
    session_id = session.get('session_id')
    
    if session_id in active_sessions:
        active_sessions[session_id].disconnect()
        del active_sessions[session_id]
        return jsonify({'success': True})
    
    return jsonify({'error': 'Aucune session active'}), 400

@app.route('/api/send_audio', methods=['POST'])
def send_audio():
    """Envoie de l'audio reçu du navigateur à OpenAI"""
    session_id = session.get('session_id')
    
    if session_id not in active_sessions:
        return jsonify({'error': 'Aucune session active'}), 400
    
    audio_data = request.json.get('audio')
    if not audio_data:
        return jsonify({'error': 'Données audio manquantes'}), 400
    
    voice_session = active_sessions[session_id]
    if voice_session.send_audio(audio_data):
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Erreur envoi audio'}), 500

@app.route('/api/end_audio', methods=['POST'])
def end_audio():
    """Signale la fin de la parole pour déclencher la réponse"""
    session_id = session.get('session_id')

    if session_id not in active_sessions:
        return jsonify({'error': 'Aucune session active'}), 400

    voice_session = active_sessions[session_id]
    if voice_session.stop_audio():
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Erreur stop audio'}), 500

@app.route('/api/status')
def get_status():
    """État de la session"""
    session_id = session.get('session_id')
    
    if session_id not in active_sessions:
        return jsonify({'connected': False})
    
    voice_session = active_sessions[session_id]
    stats = voice_session.stats.copy()
    stats['duration'] = time.time() - stats['start_time']
    
    return jsonify({
        'connected': voice_session.is_connected,
        'ready': voice_session.is_ready,
        'openai_session_id': voice_session.openai_session_id,
        'conversation_id': voice_session.conversation_id,
        'stats': stats
    })

@app.route('/api/events')
def get_events():
    """Journal des événements"""
    try:
        session_id = session.get('session_id')
        
        if session_id not in active_sessions:
            return jsonify([])
        
        return jsonify(active_sessions[session_id].events)
        
    except Exception as e:
        logger.error(f"EVENTS: Erreur récupération événements: {e}")
        return jsonify({'error': f'Erreur récupération événements: {str(e)}'}), 500

@app.route('/api/generate_test_audio')
def generate_test_audio():
    """Génère un signal audio de test côté serveur pour validation"""
    try:
        logger.info("TEST_AUDIO: Génération signal de test")
        
        # Signal sinusoïdal 1kHz, 1 seconde
        duration = 1.0
        sample_rate = 24000
        frequency = 1000
        
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        signal = np.sin(2 * np.pi * frequency * t)
        
        # Conversion en PCM16
        pcm16 = (signal * 32767 * 0.3).astype(np.int16)  # Volume modéré
        audio_bytes = pcm16.tobytes()
        audio_b64 = base64.b64encode(audio_bytes).decode()
        
        logger.info(f"TEST_AUDIO: Signal généré ({len(audio_bytes)} bytes)")
        
        return jsonify({
            'success': True, 
            'audio': audio_b64,
            'message': 'Signal de test généré (PCM16, 24kHz, 1kHz)',
            'size': len(audio_bytes)
        })
        
    except Exception as e:
        logger.error(f"TEST_AUDIO: Erreur génération: {e}")
        return jsonify({'error': f'Erreur génération test audio: {str(e)}'}), 500

@app.route('/api/audio_devices')
def get_audio_devices():
    """Endpoint pour compatibilité - devices gérés côté navigateur"""
    return jsonify({
        'message': 'Devices audio gérés côté navigateur',
        'client_side': True
    })

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Connexion WebSocket"""
    session_id = session.get('session_id')
    if session_id:
        join_room(session_id)
        emit('connected', {'session_id': session_id})

@socketio.on('disconnect')
def handle_disconnect():
    """Déconnexion WebSocket"""
    session_id = session.get('session_id')
    if session_id:
        leave_room(session_id)

if __name__ == '__main__':
    # Créer les dossiers nécessaires
    os.makedirs('static/recordings', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    logger.info("FLASK: Démarrage de l'application Voice Assistant")
    logger.info(f"MODEL: {MODEL}")
    logger.info(f"URL: http://localhost:5000")
    
    socketio.run(app, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
