import requests
import json
import logging
import os
import uuid
from Enviroment import Enviroments as env

class WhatsAppSender:
    """
    Clase para enviar mensajes de WhatsApp a través de la API oficial
    """
    
    def __init__(self):
        """
        Inicializa el sender de WhatsApp
        """
        self.token = env.ACCESS_TOKEN_WHATSAPP
        
        if not self.token:
            logging.warning("No se ha proporcionado token de WhatsApp")
    
        self.api_url = env.URL_ENVIO
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }
    
    def SendText(self, num, body, message_id=None):
        """
        Envía un mensaje de texto a un número de WhatsApp
        
        Args:
            num (str): Número de teléfono del destinatario
            body (str): Texto del mensaje
            message_id (str, optional): ID del mensaje al que se responde
            
        Returns:
            dict: Respuesta de la API de WhatsApp
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": num,
            "type": "text",
            "text": {
                "body": body
            }
        }
        
        if message_id is not None:
            payload["context"] = {
                "message_id": message_id
            }
        
        return self._send_request(payload)
    
    def SendAudio(self, num, audio_bytes, message_id=None):
        """
        Envía un mensaje de audio a un número de WhatsApp usando bytes directamente
        
        Args:
            num (str): Número de teléfono del destinatario
            audio_bytes (bytes): Los bytes del audio a enviar
            message_id (str, optional): ID del mensaje al que se responde
        """
        try:
            # Detectar automáticamente la ruta correcta del proyecto
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Comprobar si estamos dentro de una subcarpeta
            # y encontrar la carpeta principal
            parent_dir = os.path.dirname(current_dir)
            
            # Buscar la carpeta WebHook en varias posibles ubicaciones
            webhook_dir = None
            possible_paths = [
                os.path.join(parent_dir, 'WebHook'),  # Si estamos en el mismo nivel que WebHook
                os.path.join(os.path.dirname(parent_dir), 'WebHook'),  # Si estamos un nivel más profundo
                parent_dir,  # Si ya estamos en la carpeta principal
                current_dir  # Si todo falla, usar la carpeta actual
            ]
            
            for path in possible_paths:
                if os.path.exists(path) and os.path.isdir(path):
                    webhook_dir = path
                    break
            
            if not webhook_dir:
                webhook_dir = current_dir
                
            # La carpeta static debe estar dentro de la carpeta principal
            audio_dir = os.path.join(webhook_dir, 'static', 'audio')
            os.makedirs(audio_dir, exist_ok=True)
            
            # Generar nombre único para el archivo
            filename = f"audio_{uuid.uuid4()}.mp3"
            filepath = os.path.join(audio_dir, filename)
            
            # Guardar el archivo
            with open(filepath, 'wb') as f:
                f.write(audio_bytes)
            
            # Log para depuración
            logging.info(f"Audio guardado en: {filepath}")
            
            # Construir URL para la API de WhatsApp
            audio_url = f"{env.URL_CLOUDFLARE}/static/audio/{filename}"
            
            # Log para depuración
            logging.info(f"URL para WhatsApp: {audio_url}")
            
            # Preparar payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": num,
                "type": "audio",
                "audio": {
                    "link": audio_url
                }
            }
            
            # Añadir contexto si hay message_id
            if message_id is not None:
                payload["context"] = {
                    "message_id": message_id
                }
            
            # Enviar la petición
            return self._send_request(payload)
            
        except Exception as e:
            logging.error(f"Error al enviar audio: {str(e)}", exc_info=True)
            return {"error": f"Error al enviar audio: {str(e)}"}
    
    def SendVoiceNote(self, num, audio_bytes, message_id=None):
        """
        Envía un mensaje de audio como nota de voz a un número de WhatsApp
        
        Args:
            num (str): Número de teléfono del destinatario
            audio_bytes (bytes): Los bytes del audio a enviar
            message_id (str, optional): ID del mensaje al que se responde
        """
        try:
            # Detectar automáticamente la ruta correcta del proyecto
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            
            # Buscar la carpeta principal en varias posibles ubicaciones
            webhook_dir = None
            possible_paths = [
                os.path.join(parent_dir, 'WebHook'),
                os.path.join(os.path.dirname(parent_dir), 'WebHook'),
                parent_dir,
                current_dir
            ]
            
            for path in possible_paths:
                if os.path.exists(path) and os.path.isdir(path):
                    webhook_dir = path
                    break
            
            if not webhook_dir:
                webhook_dir = current_dir
                
            # La carpeta static debe estar dentro de la carpeta principal
            audio_dir = os.path.join(webhook_dir, 'static', 'audio')
            os.makedirs(audio_dir, exist_ok=True)
            
            # Generar nombre único para el archivo
            filename = f"voice_{uuid.uuid4()}.mp3"
            filepath = os.path.join(audio_dir, filename)
            
            # Guardar el archivo
            with open(filepath, 'wb') as f:
                f.write(audio_bytes)
            
            logging.info(f"Nota de voz guardada en: {filepath}")
            
            # Construir URL para la API de WhatsApp
            audio_url = f"{env.URL_CLOUDFLARE}/static/audio/{filename}"
            logging.info(f"URL para WhatsApp: {audio_url}")
            
            # Preparar payload para una nota de voz
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": num,
                "type": "audio",  # WhatsApp usa el mismo tipo "audio" tanto para audios como para notas de voz
                "audio": {
                    "link": audio_url
                }
            }
            
            # Añadir contexto si hay message_id
            if message_id is not None:
                payload["context"] = {
                    "message_id": message_id
                }
            
            # Enviar la petición
            return self._send_request(payload)
            
        except Exception as e:
            logging.error(f"Error al enviar nota de voz: {str(e)}", exc_info=True)
            return {"error": f"Error al enviar nota de voz: {str(e)}"}

    def SendImage(self, num, image_url, caption=None, message_id=None):
        """
        Envía una imagen a un número de WhatsApp
        
        Args:
            num (str): Número de teléfono del destinatario
            image_url (str): URL de la imagen a enviar
            caption (str, optional): Descripción de la imagen
            message_id (str, optional): ID del mensaje al que se responde
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": num,
            "type": "image",
            "image": {
                "link": image_url
            }
        }
        
        if caption:
            payload["image"]["caption"] = caption
            
        if message_id is not None:
            payload["context"] = {
                "message_id": message_id
            }
        
        return self._send_request(payload)
        
    def SendWriting(self, num, message_id=None):
        """
        Muestra el indicador de escritura al usuario
        
        Args:
            num (str): Número de teléfono del destinatario
            message_id (str, opcional): ID del mensaje recibido al que estás respondiendo
            
        Returns:
            dict: Respuesta de la API de WhatsApp
        """
        # Si no hay message_id, envía un mensaje con tres puntos como alternativa
        if message_id is None:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": num,
                "type": "text",
                "text": {
                    "body": "..."
                }
            }
        else:
            # Implementación oficial del indicador de escritura
            payload = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
                "typing_indicator": {
                    "type": "text"
                }
            }
        
        return self._send_request(payload)
                
    def SendDocument(self, num, document_url, filename=None, caption=None, message_id=None):
        """
        Envía un documento a un número de WhatsApp
        
        Args:
            num (str): Número de teléfono del destinatario
            document_url (str): URL del documento a enviar
            filename (str, optional): Nombre del archivo
            caption (str, optional): Descripción del documento
            message_id (str, optional): ID del mensaje al que se responde
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": num,
            "type": "document",
            "document": {
                "link": document_url
            }
        }
        
        if filename:
            payload["document"]["filename"] = filename
        if caption:
            payload["document"]["caption"] = caption
        if message_id is not None:
            payload["context"] = {
                "message_id": message_id
            }
        
        return self._send_request(payload)
    
    def SendTemplate(self, num, template_name, language="es", components=None, message_id=None):
        """
        Envía un mensaje con plantilla a un número de WhatsApp
        
        Args:
            num (str): Número de teléfono del destinatario
            template_name (str): Nombre de la plantilla
            language (str): Código del idioma (por defecto "es")
            components (list, optional): Componentes para personalizar la plantilla
            message_id (str, optional): ID del mensaje al que se responde
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": num,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language
                }
            }
        }
        
        if components:
            payload["template"]["components"] = components
        if message_id is not None:
            payload["context"] = {
                "message_id": message_id
            }
            
        return self._send_request(payload)
    
    def _send_request(self, payload):
        """
        Realiza la petición a la API de WhatsApp
        
        Args:
            payload (dict): Datos a enviar en la petición
            
        Returns:
            dict: Respuesta de la API o diccionario con el error
        """
        try:
            logging.debug(f"Enviando petición a WhatsApp API: {json.dumps(payload)[:100]}...")
            response = requests.post(
                self.api_url,
                headers=self.headers,
                data=json.dumps(payload)
            )
            
            if response.status_code == 200:
                result = response.json()
                logging.debug(f"Respuesta de WhatsApp API: {result}")
                return result
            else:
                error_msg = f"Error {response.status_code} al enviar mensaje: {response.text}"
                logging.error(error_msg)
                return {"error": error_msg, "status_code": response.status_code}
                
        except requests.exceptions.RequestException as e:
            error_msg = f"Error de conexión al enviar mensaje: {str(e)}"
            logging.error(error_msg, exc_info=True)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Error inesperado al enviar mensaje: {str(e)}"
            logging.error(error_msg, exc_info=True)
            return {"error": error_msg}