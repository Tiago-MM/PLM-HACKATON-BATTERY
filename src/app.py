from flask import Flask, render_template, request, jsonify
from neo4j import GraphDatabase

from google import genai
from google.genai import types

# --- CONFIGURATION ---
URI = "neo4j://127.0.0.1:7687" # Assure-toi que c'est la bonne adresse (bolt:// ou neo4j://)
AUTH = ("neo4j", "12345678")   # Remplace par ton mot de passe

app = Flask(__name__)



# --- NOUVELLE REQUÊTE : HISTORIQUE ---
# On récupère l'historique lié à un Passeport ID donné
# --- REQUÊTE ENRICHIE ---
# --- REQUÊTE SIMPLIFIÉE (SANS PROPRIÉTAIRE) ---
history_query = """
MATCH (p:BatteryPassport {passportID: $passportID})
MATCH (b:BatteryInstance)-[:HAS_DIGITAL_TWIN]->(p)
MATCH (model:BatteryModel)-[:HAS_INSTANCE]->(b)
OPTIONAL MATCH (model)-[:HAS_COMPOSITION]->(comp:CellComposition)
OPTIONAL MATCH (p)-[:OWNED_BY]->(op:EconomicOperator)

MATCH (b)-[:HAS_HISTORY_LOG]->(log:HealthLog)

RETURN 
    b.serialNumber AS Serial,
    model.manufacturer AS Manufacturer,
    model.chemistry AS Chemistry,
    model.nominalCapacity_kWh AS Capacity,
    comp.cathodeMaterial AS Cathode,
    comp.recyclabilityIndex AS Recyclability,
    p.carbonFootprint AS Carbon,
    op.name AS Operator,
    op.address AS OperatorAddress,
    
    log.id AS LogID, 
    toString(log.date) AS Date,
    log.soh AS SoH,
    log.cycleCount AS Cycles,
    log.voltage AS Voltage,
    log.status AS Statut

ORDER BY 
    log.date DESC, 
    
    // --- CORRECTION DE L'ORDRE D'AFFICHAGE ---
    // On force un ordre logique pour les événements du même jour
    CASE 
        // Niveau 3 (Le plus haut) : Statut Final
        WHEN log.status IN ['revalorise', 'recycled'] THEN 3 
        
        // Niveau 2 : Au Centre de Tri
        WHEN log.status IN ['Sent to Sorting', 'recycling center'] THEN 2 
        
        // Niveau 1 : Diagnostics Garagiste (Warning, Good, etc.)
        ELSE 1 
    END DESC
"""

import uuid # N'oublie pas d'importer uuid tout en haut du fichier

# --- AJOUT D'UN DIAGNOSTIC (AVEC DATE MANUELLE) ---
def add_diagnostic_log(tx, passport_id, voltage, soh, status, cycle_count, log_date):
    query = """
    MATCH (b:BatteryInstance)-[:HAS_DIGITAL_TWIN]->(p:BatteryPassport {passportID: $passportID})
    
    // Création d'un nouveau log
    CREATE (log:HealthLog {
        id: $logID,
        date: date($logDate),        // <--- ON UTILISE LA DATE PASSÉE EN PARAMÈTRE
        voltage: toFloat($voltage),
        soh: toInteger($soh),
        status: $status,
        cycleCount: toInteger($cycleCount)
    })
    
    // On relie le log à la batterie
    CREATE (b)-[:HAS_HISTORY_LOG]->(log)
    """
    
    import uuid
    # On passe log_date dans les paramètres de la requête
    tx.run(query, 
           passportID=passport_id, 
           logID=str(uuid.uuid4()), 
           logDate=log_date,         ##<--- C'EST ICI QUE ÇA SE JOUE
           voltage=voltage, 
           soh=soh, 
           status=status, 
           cycleCount=cycle_count)
    

def fetch_history_data(tx, passport_id):
    result = tx.run(history_query, passportID=passport_id)
    return [record.data() for record in result]

@app.route("/")
def home():
    return render_template("index.html")
import uuid # Import nécessaire si pas déjà fait
from datetime import date # Import nécessaire

@app.route("/garagiste", methods=["GET", "POST"])
def garagiste_dashboard():
    passport_input = request.args.get("passport_id") or request.form.get("passport_id")
    data = None
    error = None
    success_msg = None # Pour confirmer l'ajout
    
    # Listes pour le graphique
    dates = []
    soh_values = []

    # --- CAS 1 : ENREGISTREMENT D'UN NOUVEAU DIAGNOSTIC (POST) ---
    if request.method == "POST":
        try:
            # Récupération des champs
            new_voltage = request.form.get("voltage")
            new_soh = request.form.get("soh")
            new_status = request.form.get("status")
            new_cycles = request.form.get("cycles")
            
            # --- NOUVEAU : Récupération de la date ---
            new_date = request.form.get("log_date") 
            
            # Sécurité : Si l'utilisateur n'a pas mis de date, on met celle d'aujourd'hui
            if not new_date:
                from datetime import date
                new_date = str(date.today())

            if passport_input and new_voltage:
                with GraphDatabase.driver(URI, auth=AUTH) as driver:
                    with driver.session() as session:
                        # On appelle la nouvelle version de la fonction avec new_date
                        session.execute_write(add_diagnostic_log, 
                                            passport_input, 
                                            new_voltage, 
                                            new_soh, 
                                            new_status, 
                                            new_cycles, 
                                            new_date) # <--- AJOUT ICI
                success_msg = "✅ Diagnostic ajouté avec succès !"
                
        except Exception as e:
            error = f"Erreur lors de l'enregistrement : {e}"
    # --- CAS 2 : AFFICHAGE DES DONNÉES (GET & POST) ---
    if passport_input:
        passport_input = passport_input.strip()
        try:
            with GraphDatabase.driver(URI, auth=AUTH) as driver:
                with driver.session() as session:
                    # On reprend ta requête existante (history_query)
                    data = session.execute_read(fetch_history_data, passport_input)
            
            if not data:
                if not error: error = f"Aucun historique trouvé pour : {passport_input}"
            else:
                for row in data:
                    dates.append(row['Date'])
                    soh_values.append(row['SoH'])

        except Exception as e:
            error = f"Erreur Neo4j : {e}"

    return render_template(
        "dashboard.html", 
        data=data, 
        passport=passport_input, 
        error=error,
        success=success_msg, # On passe le message de succès au HTML
        graph_dates=dates, 
        graph_soh=soh_values
    )

# --- 1. Récupérer la liste des Constructeurs (EconomicOperator) ---
def get_all_owners(tx):
    # On cherche les opérateurs liés à des passeports
    query = """
    MATCH (p:BatteryPassport)-[:OWNED_BY]->(op:EconomicOperator)
    RETURN DISTINCT op.name AS name
    ORDER BY op.name
    """
    result = tx.run(query)
    return [record.data() for record in result]

# --- 2. Récupérer les batteries d'un Constructeur spécifique ---
def get_batteries_by_owner(tx, owner_name):
    # On filtre par le nom de l'opérateur économique
    query = """
    MATCH (op:EconomicOperator {name: $ownerName})<-[:OWNED_BY]-(p:BatteryPassport)
    MATCH (b:BatteryInstance)-[:HAS_DIGITAL_TWIN]->(p)
    
    // Récupération du dernier log pour avoir le statut actuel
    OPTIONAL MATCH (b)-[:HAS_HISTORY_LOG]->(lastLog:HealthLog)
    WITH op, p, b, lastLog ORDER BY lastLog.date DESC
    WITH op, p, b, head(collect(lastLog)) as currentStatus
    
    RETURN 
        b.serialNumber AS Serial,
        p.passportID AS PassportID,
        op.address AS Location,  // On utilise l'adresse du fabricant comme "Lieu"
        coalesce(currentStatus.status, 'Inconnu') AS Status,
        currentStatus.soh AS SoH
    """
    result = tx.run(query, ownerName=owner_name)
    return [record.data() for record in result]

# --- ROUTE CONSTRUCTEUR / PASSEPORT ---
@app.route("/owner", methods=["GET"])
def owner_dashboard():
    # 1. Si aucun constructeur choisi -> Page de Login
    if not request.args.get("owner_name"):
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            with driver.session() as session:
                owners = session.execute_read(get_all_owners)
        return render_template("owner_login.html", owners=owners)

    # 2. Si constructeur connecté
    owner_name = request.args.get("owner_name")
    selected_passport = request.args.get("passport_id")
    
    batteries = []
    passport_data = None # On renomme 'data' en 'passport_data' pour être plus clair
    
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session() as session:
            # A. Liste des batteries du constructeur (Sidebar)
            batteries = session.execute_read(get_batteries_by_owner, owner_name)
            
            # B. Sélection par défaut si besoin
            if not selected_passport and batteries:
                selected_passport = batteries[0]['PassportID']
            
            # C. Chargement du PASSEPORT COMPLET pour la batterie active
            if selected_passport:
                # On utilise la requête complète définie plus tôt
                passport_data = session.execute_read(fetch_history_data, selected_passport)

    return render_template(
        "owner_dashboard.html", 
        owner_name=owner_name,
        batteries=batteries,
        data=passport_data, # On envoie les données complètes
        current_passport=selected_passport
    )
from flask import redirect # Assure-toi d'avoir importé 'redirect' en haut du fichier

# --- ROUTE DE SUPPRESSION ---
# --- ROUTE DE SUPPRESSION ---
@app.route("/delete_log/<log_id>")
def delete_log(log_id):
    # 1. On récupère le passport_id passé dans l'URL (le lien href="...?passport_id=...")
    passport_id = request.args.get("passport_id")
    
    query_delete = "MATCH (log:HealthLog {id: $logID}) DETACH DELETE log"
    
    try:
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            with driver.session() as session:
                session.run(query_delete, logID=log_id)
    except Exception as e:
        print(f"Erreur de suppression : {e}")
        
    # --- CORRECTION ICI ---
    # Au lieu de url_for, on force la redirection vers l'URL exacte
    # Cela évite les erreurs de nommage de fonction
    if passport_id:
        return redirect(f"/garagiste?passport_id={passport_id}")
    else:
        # Si jamais on a perdu l'ID, on renvoie vers la page vide
        return redirect("/garagiste")
    


# --- ROUTE : ENVOYER AU CENTRE DE TRI ---
@app.route("/send_to_sorting")
def send_to_sorting():
    passport_id = request.args.get("passport_id")
    owner_name = request.args.get("owner_name") # Pour pouvoir revenir sur la bonne page
    
    # On ajoute un log spécial "recycling center"
    # On garde le dernier SoH connu pour la continuité
    query = """
    MATCH (b:BatteryInstance)-[:HAS_DIGITAL_TWIN]->(p:BatteryPassport {passportID: $passportID})
    MATCH (b)-[:HAS_HISTORY_LOG]->(lastLog:HealthLog)
    WITH b, lastLog ORDER BY lastLog.date DESC LIMIT 1
    
    CREATE (newLog:HealthLog {
        id: $logID,
        date: date($today),
        voltage: 0,              // Voltage nul car déconnectée
        soh: lastLog.soh,        // On garde le SoH actuel
        status: 'recycling center',
        cycleCount: lastLog.cycleCount
    })
    
    CREATE (b)-[:HAS_HISTORY_LOG]->(newLog)
    """
    
    try:
        import uuid
        from datetime import date
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            with driver.session() as session:
                session.run(query, 
                            passportID=passport_id, 
                            logID=str(uuid.uuid4()), 
                            today=str(date.today()))
    except Exception as e:
        print(f"Erreur transfert : {e}")

    # On recharge la page du constructeur
    return redirect(f"/owner?owner_name={owner_name}&passport_id={passport_id}")


# --- REQUÊTE : BATTERIES EN ATTENTE DE TRI (VERSION FINALE) ---
def get_sorting_center_stock(tx):
    query = """
MATCH (b:BatteryInstance)-[:HAS_DIGITAL_TWIN]->(p:BatteryPassport)
MATCH (model:BatteryModel)-[:HAS_INSTANCE]->(b)
OPTIONAL MATCH (model)-[:HAS_COMPOSITION]->(comp:CellComposition)

MATCH (b)-[:HAS_HISTORY_LOG]->(log:HealthLog)

WITH b, p, model, comp, log 
ORDER BY 
    log.date DESC,
    CASE 
        WHEN toLower(log.status) IN ['recycled', 'revalorise'] THEN 2
        WHEN toLower(log.status) = 'recycling center' THEN 1
        ELSE 0
    END DESC

WITH b, p, model, comp, head(collect(log)) as currentStatus

WHERE toLower(currentStatus.status) = 'recycling center'

RETURN 
    b.serialNumber AS Serial,
    p.passportID AS PassportID,
    model.chemistry AS Chemistry,
    model.manufacturer AS Manufacturer,
    comp.recyclabilityIndex AS Recyclability,
    toString(currentStatus.date) AS ArrivalDate,
    currentStatus.soh AS SoH
ORDER BY currentStatus.date DESC

    """
    result = tx.run(query)
    return [record.data() for record in result]


# --- COMPTER LES BATTERIES RECYCLÉES (TOTAL) ---
def count_recycled_batteries(tx):
    query = """
    MATCH (b:BatteryInstance)-[:HAS_HISTORY_LOG]->(log:HealthLog)
    WITH b, log ORDER BY log.date DESC
    WITH b, head(collect(log)) as currentStatus
    WHERE currentStatus.status = 'recycled'
    RETURN count(b) as total
    """
    result = tx.run(query)
    return result.single()["total"]

# --- COMPTER LES BATTERIES CRITIQUES EN ATTENTE ---
# (Parmi celles qui sont dans le stock du centre de tri)
def count_critical_stock(tx):
    query = """
    MATCH (b:BatteryInstance)-[:HAS_HISTORY_LOG]->(log:HealthLog)
    WITH b, log ORDER BY log.date DESC
    // Priorité pour trouver le statut actuel (comme vu précédemment)
    WITH b, log ORDER BY log.date DESC, 
         CASE WHEN log.status IN ['recycled', 'revalorise'] THEN 2 
              WHEN log.status = 'recycling center' THEN 1 ELSE 0 END DESC
    WITH b, head(collect(log)) as currentStatus
    
    // On regarde seulement celles qui sont 'recycling center' ET qui ont un SoH bas
    WHERE currentStatus.status = 'recycling center' AND currentStatus.soh < 50
    RETURN count(b) as total
    """
    result = tx.run(query)
    return result.single()["total"]


# --- ROUTE : ACTION DE TRI (RECYCLAGE OU 2NDE VIE) ---
@app.route("/process_battery/<action>/<passport_id>")
def process_battery(action, passport_id):
    # Action peut être 'Recycled' ou 'Second Life'
    import uuid
    from datetime import date
    
    query = """
    MATCH (b:BatteryInstance)-[:HAS_DIGITAL_TWIN]->(p:BatteryPassport {passportID: $passportID})
    MATCH (b)-[:HAS_HISTORY_LOG]->(lastLog:HealthLog)
    WITH b, lastLog ORDER BY lastLog.date DESC LIMIT 1
    
    CREATE (newLog:HealthLog {
        id: $logID,
        date: date($today),
        voltage: 0,
        soh: lastLog.soh,
        status: $newStatus,
        cycleCount: lastLog.cycleCount
    })
    CREATE (b)-[:HAS_HISTORY_LOG]->(newLog)
    """
    
    try:
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            with driver.session() as session:
                session.run(query, 
                            passportID=passport_id, 
                            logID=str(uuid.uuid4()), 
                            today=str(date.today()),
                            newStatus=action) # 'Recycled' ou 'Second Life'
    except Exception as e:
        print(f"Erreur traitement : {e}")
        
    return redirect("/recycler")

# --- ROUTE : DASHBOARD CENTRE DE TRI ---
@app.route("/recycler")
def recycler_dashboard():
    stock = []
    total_recycled = 0
    critical_count = 0
    
    try:
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            with driver.session() as session:
                # 1. Le stock (liste complète)
                stock = session.execute_read(get_sorting_center_stock)
                
                # 2. Le nombre total de batteries recyclées (historique global)
                total_recycled = session.execute_read(count_recycled_batteries)
                
                # 3. Le nombre de batteries critiques dans le stock actuel
                # (On peut aussi le calculer en Python len([b for b in stock if b['SoH'] < 50]) mais SQL est mieux)
                critical_count = session.execute_read(count_critical_stock)
                
    except Exception as e:
        print(f"Erreur : {e}")
        
    return render_template(
        "recycler_dashboard.html", 
        stock=stock,
        total_recycled=total_recycled, # Nouvelle variable
        critical_count=critical_count  # Nouvelle variable
    )

# --- ROUTE 1 : LA PAGE HTML (EXISTANTE) ---
@app.route("/chatbot")
def chatbot_page():
    return render_template("chatbot.html")

from flask import Flask, request, jsonify
import os
from mistralai import Mistral

api_key = "non tu n'auras pas ma clé API"  # Remplace par ta clé API Mistral

client = Mistral(api_key=api_key)

# Votre instruction système (Persona)
SYSTEM_INSTRUCTION = """
Tu es un expert technique du Battery Passport (Règlement UE).
Tu aides à remplir les déclarations de recyclabilité et d'empreinte carbone.
Réponds de manière concise et technique.
maximum 75 mots par réponse
"""

@app.route("/api/chat", methods=["POST"])
def chat_api():
    data = request.json
    user_message = data.get("message")
    # L'historique arrive sous forme de liste de dictionnaires : 
    # [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    history = data.get("history", []) 
    
    if not user_message:
        return jsonify({"response": "Message vide."})

    try:
        # 1. Construction de la liste des messages pour Mistral
        # On commence TOUJOURS par l'instruction système
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION}
        ]

        # 2. On ajoute l'historique reçu du Frontend
        # Mistral s'attend à 'assistant' pour l'IA, pas 'model'
        for msg in history:
            role = "assistant" if msg.get("role") in ["assistant", "model"] else "user"
            messages.append({
                "role": role,
                "content": msg.get("content", "")
            })

        # 3. On ajoute le message actuel de l'utilisateur
        messages.append({"role": "user", "content": user_message})

        # 4. Appel à l'API Mistral
        chat_response = client.chat.complete(
            model="mistral-small-latest", # Le meilleur modèle pour le raisonnement complexe
            messages=messages,
            temperature=0.3
        )
        
        # 5. Extraction de la réponse
        ai_text = chat_response.choices[0].message.content
        
        return jsonify({"response": ai_text})

    except Exception as e:
        print(f"Erreur Mistral: {e}")
        return jsonify({"response": "Erreur technique lors de la communication avec Mistral."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)