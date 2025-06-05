import requests
import json
from Enviroment import Enviroments as env

def texto_a_voz(texto, idioma='es'):
    """
    Convierte texto a voz mediante una API externa
    
    Args:
        texto (str): Texto a convertir en voz
        idioma (str): Código del idioma (por defecto 'es' para español)
        
    Returns:
        bytes: Contenido binario del audio generado, o None si hay error
    """
    url = env.URL_TEXTO_VOZ
    
    payload = {
        "text": texto,
        "language": idioma
    }
    
    response = requests.post(
        url,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=10000
    )
    
    if response.status_code == 200:
        return response.content
    
    return None