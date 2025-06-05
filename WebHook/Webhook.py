# WebHook.py
from flask import Flask, request, jsonify
import os
import logging
from chat.chat import ChatProcess

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("webhook.log")
    ]
)

# Obtener la ruta absoluta del directorio donde se encuentra el script
base_dir = os.path.dirname(os.path.abspath(__file__))

# Configurar Flask con la carpeta static
app = Flask(__name__,
    static_folder=os.path.join(base_dir, 'static'),
    static_url_path='/static')

# Asegurarse de que la carpeta static/audio exista
os.makedirs(os.path.join(base_dir, 'static', 'audio'), exist_ok=True)

# Inicializar el procesador de chat
chatObj = ChatProcess()

# Token de verificación para el webhook de WhatsApp
VERIFY_TOKEN = "hola"

@app.route('/webhook', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        # Verificación del webhook por parte de Facebook/WhatsApp
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')
        
        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        else:
            return "Error de verificación", 403
            
    elif request.method == 'POST':
        # Procesar eventos entrantes del webhook
        data = request.json
        logging.info(f"Evento de webhook recibido: {data}")
        
        # Procesar el mensaje a través de nuestro sistema
        chatObj.ProcessMessage(data)
        
        return jsonify({"message": "Evento recibido"}), 200

def run_webHook():
    # Iniciar el servidor
    logging.info("Iniciando servidor Flask...")
    app.run(port=5001, debug=True)

if __name__ == "__main__":
    run_webHook()