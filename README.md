# PLM-HACKATON-BATTERY
README.md
# PLM-HACKATON-BATTERY
 
Prototype Flask pour la démonstration d'un "Battery Passport" (Hackathon ESILV).
 
Ce dépôt contient une application légère permettant de :
 
- Enregistrer et consulter des passeports de batterie (BatteryPassport) et leurs historiques de santé (HealthLog) stockés dans une base de données Neo4j.
- Visualiser l'historique de l'état de santé (SoH) et ajouter des diagnostics manuels depuis une interface mécanicien.
- Fournir des vues pour le garagiste, le propriétaire et pour le centre de tri / recycleur.
- Disposer d'une interface de chatbot simple (`/chatbot`) avec un endpoint API (`/api/chat`) qui relaie le message vers un client de modèle.
 
---
 
Principe d'architecture
------------------------
 
- Serveur web : application Flask dans `src/app.py`.
- Base de données : Neo4j (driver Python `neo4j`).
- Templates : Jinja2 dans `src/templates/` (pages pour mécanicien, propriétaire, recycleur, chatbot).
- Données d'exemple : plusieurs fichiers CSV à la racine (`BatteryPassport.csv`, `BatteryModel.csv`, `BatteryInstance.csv`, `BatteryHistory.csv`, `CellComposition.csv`, `EconomicOperator.csv`, `Owners.csv`, `Thresholds.csv`).
 
Modèle de données attendu (graph)
---------------------------------
 
- `BatteryPassport` (clé `passportID`)
- `BatteryInstance` reliée via `:HAS_DIGITAL_TWIN` au passeport
- `BatteryModel` et `CellComposition` pour métadonnées de la cellule
- `EconomicOperator` (fabricant / opérateur)
- `HealthLog` stockant `id`, `date`, `voltage`, `soh`, `status`, `cycleCount` et relié à l'instance via `:HAS_HISTORY_LOG`
 
Routes importantes
------------------
 
- `GET /` — page d'accueil (`index.html`).
- `GET, POST /garagiste` — tableau mécanicien : consulter et ajouter des diagnostics via `passport_id`.
- `GET /owner` — accès propriétaire / constructeur (sélection d'`owner_name` et `passport_id`).
- `GET /recycler` — vue recycleur / centre de tri (stock, comptages).
- `GET /chatbot` — page du chatbot.
- `POST /api/chat` — endpoint utilisé par le frontend du chatbot.
- `GET /send_to_sorting?passport_id=...&owner_name=...` — ajoute un log "recycling center" et redirige.
- `GET /process_battery/<action>/<passport_id>` — ajoute un log d'action finale (`Recycled` / `Second Life`).
- `GET /delete_log/<log_id>?passport_id=...` — supprime un log et redirige.
 
Configuration
-------------
 
Ouvrir `src/app.py` et modifier les paramètres Neo4j en tête de fichier :
 
```python
URI = "neo4j://127.0.0.1:7687"
AUTH = ("neo4j", "12345678")
```
 
Remplacez par l'URI, l'utilisateur et le mot de passe adaptés à votre instance Neo4j. Pour la clé API du client Mistral, mettez la vôtre si vous utilisez la fonctionnalité chatbot.
 
Démarrage (développement)
-------------------------
 
Depuis la racine du projet :
 
```powershell
cd src
python app.py
```
 
L'application écoute sur `http://127.0.0.1:5000/` en mode debug par défaut.
 
Fichiers clés
-------------
 
- `src/app.py` : application Flask et requêtes Cypher intégrées.
- `src/templates/` : modèles Jinja2 (`index.html`, `dashboard.html`, `owner_login.html`, `owner_dashboard.html`, `recycler_dashboard.html`, `chatbot.html`).
- Fichiers CSV à la racine : jeux de données exemples.
 
 
