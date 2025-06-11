import os
import sys
import importlib
import base64
import json
import pytest

# Configurer les variables d'environnement requises avant l'import de l'application
os.environ.setdefault('OPENAI_API_KEY', 'test-key')
os.environ.pop('MON_USERNAME', None)
os.environ.pop('PASSWORD', None)

# S'assurer que le dossier parent est dans sys.path pour l'import de app
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

app = importlib.import_module('app')

# Désactiver l'authentification stricte pour les tests
app.AUTH_USERNAME = None
app.AUTH_PASSWORD = None

@pytest.fixture
def client():
    app.app.config['TESTING'] = True
    with app.app.test_client() as client:
        yield client

def test_login_page(client):
    resp = client.get('/')
    assert resp.status_code == 200


def test_login_success(client):
    resp = client.post('/login', data={'username': 'tester', 'password': ''})
    assert resp.status_code == 302
    assert '/voice' in resp.headers['Location']


def test_generate_test_audio(client):
    resp = client.get('/api/generate_test_audio')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'audio' in data
    base64.b64decode(data['audio'])  # ne doit pas lever d'erreur


def test_audio_devices(client):
    resp = client.get('/api/audio_devices')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['client_side'] is True


def test_dialogue_flow(client, monkeypatch):
    # Se connecter pour initialiser la session
    client.post('/login', data={'username': 'tester', 'password': ''})

    # Fonctions factices pour la classe VoiceSession
    def fake_start(self):
        self.is_connected = True
        self.is_ready = True
        self.openai_session_id = 's123'
        self.conversation_id = 'c123'
        return True

    def fake_send(self, audio):
        return True

    def fake_stop(self):
        return True

    def fake_disconnect(self):
        self.is_connected = False
        self.is_ready = False

    monkeypatch.setattr(app.VoiceSession, 'start_connection', fake_start)
    monkeypatch.setattr(app.VoiceSession, 'send_audio', fake_send)
    monkeypatch.setattr(app.VoiceSession, 'stop_audio', fake_stop)
    monkeypatch.setattr(app.VoiceSession, 'disconnect', fake_disconnect)

    # Démarrage
    resp = client.post('/api/start_dialogue')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    # Envoi audio
    payload = {'audio': base64.b64encode(b'test').decode()}
    resp = client.post('/api/send_audio', json=payload)
    assert resp.status_code == 200

    # Fin de parole
    resp = client.post('/api/end_audio')
    assert resp.status_code == 200

    # Statut
    resp = client.get('/api/status')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['connected'] is True

    # Récupération des événements
    resp = client.get('/api/events')
    assert resp.status_code == 200

    # Arrêt
    resp = client.post('/api/stop_dialogue')
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True

    # Déconnexion
    resp = client.get('/logout')
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/')
