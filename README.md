# Assistant Vocal OpenAI - Realtime

Ce projet fournit une petite application Flask permettant d'interagir à la voix avec les API temps réel d'OpenAI (GPT‑4o). Elle expose une interface web moderne avec audio bidirectionnel et suivi des statistiques.

## Installation

1. Cloner ce dépôt.
2. Créer un environnement Python 3.10 ou plus récent et installer les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. Créer un fichier `.env` ou définir les variables d'environnement suivantes :
   - `OPENAI_API_KEY` : clé API OpenAI (obligatoire)
   - `MODEL` : nom du modèle à utiliser (par défaut : `gpt-4o-realtime-preview-2024-10-01`)
   - `INSTRUCTIONS` : instructions système transmises au modèle (optionnel)
   - `FLASK_SECRET_KEY` : clé secrète Flask
   - `MON_USERNAME` / `PASSWORD` : identifiant et mot de passe pour l'interface (facultatif : si absent seul un nom d'utilisateur est demandé)

## Lancer l'application

```
python app.py
```

Le serveur démarre par défaut sur `http://localhost:5000`.

## Utilisation

1. Rendez‑vous sur la page d'accueil pour vous connecter.
2. Sur la page principale, cliquez sur le cercle microphone pour démarrer ou arrêter une session vocale en temps réel.
3. Les journaux et statistiques sont accessibles via les contrôles placés en bas à droite.

Vous pouvez également appeler l'endpoint `/api/generate_test_audio` pour générer un court signal audio de test.

## Fichiers principaux

- `app.py` – application Flask et communication WebSocket avec l'API OpenAI
- `templates/` – templates HTML (page de connexion et interface vocale)
- `requirements.txt` – dépendances Python
- `static/favicon.png` – icône de l'application affichée dans l'onglet du navigateur

## Licence

Ce projet est fourni tel quel, sans garantie. Utilisez-le à vos risques et périls.
Le fichier `static/favicon.png` provient du projet [twemoji](https://github.com/twitter/twemoji/blob/master/assets/72x72/1f3a4.png)
sous licence Creative Commons Attribution 4.0 (CC-BY 4.0).
