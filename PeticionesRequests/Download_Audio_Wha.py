import json
import requests
import logging
from Enviroment import Enviroments as env

def obtener_audio_whatsapp(webhook_data):
    """
    Descarga un archivo de audio del webhook de WhatsApp
    
    Args:
        webhook_data: Datos relevantes del webhook de WhatsApp
        
    Returns:
        bytes: Contenido binario del archivo de audio
    """
    print("Iniciando descarga de audio...")
    access_token = env.ACCESS_TOKEN_WHATSAPP
    
    try:
        # Extraer el ID del audio - acceso directo
        audio_id = None
        try:
            if isinstance(webhook_data, dict) and "changes" in webhook_data:
                audio_id = webhook_data["changes"][0]["value"]["messages"][0]["audio"]["id"]
            else:
                audio_id = webhook_data["entry"][0]["changes"][0]["value"]["messages"][0]["audio"]["id"]
            print(f"ID de audio identificado: {audio_id}")
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"No se pudo extraer el ID del audio: {str(e)}")
        
        # Paso 1: Obtener la URL temporal del archivo
        url = f"{env.URL_INFO_MEDIA}/{audio_id}"
        print(f"Solicitando información del medio: {url}")
        
        info_response = requests.get(
            url=url,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if info_response.status_code != 200:
            raise RuntimeError(f"Error al obtener URL del audio: {info_response.status_code}")
        
        # Extraer la URL temporal
        media_url = info_response.json().get("url")
        if not media_url:
            raise ValueError("No se pudo obtener la URL del medio")
            
        print(f"URL temporal obtenida correctamente")
        
        # Paso 2: Descargar el archivo desde esa URL
        print("Descargando contenido del audio...")
        
        audio_response = requests.get(
            media_url,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if audio_response.status_code != 200:
            raise RuntimeError(f"Error al descargar el audio: {audio_response.status_code}")
            
        print("Audio descargado correctamente")
        return audio_response.content
        
    except Exception as e:
        logging.error(f"Error al obtener audio de WhatsApp: {str(e)}")
        raise