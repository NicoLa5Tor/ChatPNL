import requests
from Enviroment import Enviroments as env
import logging

def transcribir_audio(audio_bytes):
    """
    Envía un audio a la API de transcripción
    
    Args:
        audio_bytes: Contenido binario del archivo de audio
        
    Returns:
        str: Texto transcrito
    """
    url = env.URL_VOZ_TEXTO
    print(f"Enviando audio para transcripción a {url}")
    
    try:
        files = {
            "audio_file": ("audio.ogg", audio_bytes, "audio/ogg")
        }
        
        response = requests.post(url, files=files, timeout=10000) # Agregado timeout para evitar esperas infinitas
        
        if response.status_code == 200:
            result = response.json()
            transcripcion = result.get("transcription", "")
            print(f"Transcripción exitosa: {transcripcion[:50]}...") # Mostrar primeros 50 caracteres
            return transcripcion
        else:
            error_msg = f"Error {response.status_code} al transcribir: {response.text}"
            logging.error(error_msg)
            return f"Error en la transcripción: {response.status_code}"
            
    except requests.exceptions.Timeout:
        logging.error("Timeout al transcribir el audio")
        return "Error: Timeout al transcribir el audio"
    except Exception as e:
        error_msg = f"Error al transcribir audio: {str(e)}"
        logging.error(error_msg)
        return "Error en la transcripción"