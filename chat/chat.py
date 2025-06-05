from EnvioMensajes.Envio import WhatsAppSender
from PeticionesRequests.Download_Audio_Wha import obtener_audio_whatsapp 
from PeticionesRequests.Pich_To_Text import transcribir_audio
from PeticionesRequests.Text_To_Speech import texto_a_voz
import json
import logging
import os
import time
from datetime import datetime
import re
import string
import random


# Intentamos importar NLTK y otras bibliotecas
try:
    import nltk
    import numpy as np
    
    # Intentar descargar recursos de NLTK de manera segura
    try:
        logging.info("Descargando recursos necesarios para NLTK...")
        nltk.download('punkt', quiet=True)
        nltk.download('wordnet', quiet=True)
        nltk.download('stopwords', quiet=True)
        nltk.download('averaged_perceptron_tagger', quiet=True)
        logging.info("Recursos descargados correctamente.")
    except Exception as e:
        logging.error(f"Error al descargar recursos NLTK: {e}")
        logging.info("Se utilizarán funciones alternativas.")
    
    nltk_available = True
except ImportError:
    logging.warning("NLTK no está disponible. Se usarán funciones simplificadas.")
    nltk_available = False

# Función segura para intentar importar bibliotecas
def importar_seguro(biblioteca, mensaje_alt=""):
    try:
        return __import__(biblioteca)
    except ImportError:
        logging.warning(f"No se pudo importar {biblioteca}. {mensaje_alt}")
        return None

# Intentar cargar spaCy (opcional)
spacy = importar_seguro("spacy", "El análisis será simplificado.")

# Funciones alternativas si las bibliotecas fallan
def tokenize_simple(texto):
    """Función simple de tokenización como alternativa a NLTK"""
    # Eliminar puntuación y convertir a minúsculas
    texto = texto.lower()
    # Eliminar puntuación
    texto = ''.join([char for char in texto if char not in string.punctuation])
    # Dividir por espacios
    return texto.split()

def pos_tag_simple(tokens):
    """Etiquetado POS simplificado cuando NLTK falla"""
    # Simplemente asumimos que todas las palabras son sustantivos (NN)
    return [(token, "NN") for token in tokens]

class ChatProcess:
    def __init__(self):
        # Inicializar el sender de WhatsApp
        self.whatsapp_sender = WhatsAppSender()
        
        # Diccionario para almacenar datos de empresas
        self.empresas = {}
        self.cargar_datos()
        logging.info("Sistema de Análisis Empresarial por WhatsApp iniciado.")
        
        # Diccionario para almacenar el estado de las conversaciones por usuario
        self.conversaciones = {}
        
        # Añadir estructuras para controlar mensajes duplicados
        self.processed_messages = {}  # Almacena los IDs de mensaje ya procesados
        self.processed_messages_ttl = {}  # Almacena tiempos de expiración para cada mensaje
        
        # Verificar si tenemos acceso a las funciones de NLTK
        self.use_nltk = nltk_available
        try:
            from nltk.tokenize import word_tokenize
            from nltk.tag import pos_tag
            self.word_tokenize = word_tokenize
            self.pos_tag = pos_tag
        except (ImportError, LookupError):
            logging.info("NLTK no está disponible, se usarán funciones simplificadas.")
            self.word_tokenize = tokenize_simple
            self.pos_tag = pos_tag_simple
            self.use_nltk = False
        
        # Verificar si podemos usar spaCy
        self.use_spacy = False
        if spacy:
            try:
                self.nlp = spacy.load('es_core_news_md')
                self.use_spacy = True
                logging.info("Modelo spaCy cargado correctamente.")
            except:
                try:
                    self.nlp = spacy.load('es_core_news_sm')
                    self.use_spacy = True
                    logging.info("Usando modelo alternativo 'es_core_news_sm'")
                except:
                    logging.warning("No se pudo cargar ningún modelo de spaCy.")
    
    def debe_responder_con_audio(self):
        """
        Determina si se debe responder con audio basado en la probabilidad configurada (40%)
        
        Returns:
            bool: True si se debe responder con audio, False si solo texto
        """
        # 40% de probabilidad de responder con audio
        return random.random() < 0.4
    
    def cargar_datos(self):
        try:
            if os.path.exists("empresas_data.json"):
                with open("empresas_data.json", "r", encoding="utf-8") as file:
                    self.empresas = json.load(file)
                logging.info(f"Se cargaron datos de {len(self.empresas)} empresas.")
            else:
                logging.info("No se encontró archivo de datos. Se iniciará con una base de datos vacía.")
        except Exception as e:
            logging.error(f"Error al cargar datos: {str(e)}")
            self.empresas = {}
    
    def guardar_datos(self):
        try:
            with open("empresas_data.json", "w", encoding="utf-8") as file:
                json.dump(self.empresas, file, ensure_ascii=False, indent=4)
            logging.info("Datos guardados correctamente.")
        except Exception as e:
            logging.error(f"Error al guardar datos: {str(e)}")
    
    def _cleanup_processed_messages(self):
        """Limpia mensajes antiguos para evitar que la memoria crezca indefinidamente"""
        try:
            current_time = time.time()
            expired_messages = []
            
            # Identificar mensajes expirados
            for message_id, expiry_time in list(self.processed_messages_ttl.items()):
                if current_time > expiry_time:
                    expired_messages.append(message_id)
            
            # Eliminar mensajes expirados
            for message_id in expired_messages:
                if message_id in self.processed_messages:
                    del self.processed_messages[message_id]
                if message_id in self.processed_messages_ttl:
                    del self.processed_messages_ttl[message_id]
                    
            if expired_messages:
                logging.debug(f"Limpieza de mensajes: {len(expired_messages)} mensajes eliminados. {len(self.processed_messages)} mensajes activos.")
        except Exception as e:
            logging.error(f"Error al limpiar mensajes antiguos: {str(e)}")
    
    def ProcessMessage(self, data):
        """
        Procesa los mensajes entrantes del webhook de WhatsApp
        
        Args:
            data (dict): Datos del webhook de WhatsApp
        """
        try:
            logging.info("Procesando mensaje de WhatsApp...")
            
            # Extraer información relevante del webhook
            if "entry" not in data or not data["entry"]:
                logging.warning("Formato de webhook inválido, no contiene 'entry'")
                return
                
            # Obtener datos del mensaje
            changes = data["entry"][0]["changes"]
            if not changes:
                logging.warning("No hay cambios en el webhook")
                return
                
            value = changes[0]["value"]
            if "messages" not in value or not value["messages"]:
                logging.info("No hay mensajes en el webhook, posiblemente status update")
                return
                
            message = value["messages"][0]
            message_id = message["id"]
            from_number = message["from"]
            
            # Verificar si ya procesamos este message_id para evitar duplicados
            if message_id in self.processed_messages:
                logging.info(f"Mensaje {message_id} ya procesado anteriormente. Ignorando para evitar duplicados.")
                return
            
            # Agregar este mensaje a los procesados
            self.processed_messages[message_id] = True
            
            # Establecer un TTL (30 minutos) para este mensaje
            current_time = time.time()
            self.processed_messages_ttl[message_id] = current_time + 1800  # 1800 segundos = 30 minutos
            
            # Limpiar mensajes antiguos para que la memoria no crezca indefinidamente
            self._cleanup_processed_messages()
            
            # Primero mostrar el indicador de escritura
            self.whatsapp_sender.SendWriting(from_number, message_id)
            
            # Verificar tipo de mensaje
            if "text" in message:
                # Mensaje de texto
                text = message["text"]["body"]
                logging.info(f"Mensaje de texto recibido: {text}")
                self.procesar_mensaje_texto(from_number, text, message_id)
                
            elif "audio" in message:
                # Mensaje de audio
                logging.info("Mensaje de audio recibido, procesando...")
                try:
                    # Descargar el audio
                    audio_bytes = obtener_audio_whatsapp(data)
                    
                    # Transcribir el audio a texto
                    texto_transcrito = transcribir_audio(audio_bytes)
                    logging.info(f"Transcripción: {texto_transcrito}")
                    
                    # Verificar si la transcripción falló o está vacía
                    if not texto_transcrito or texto_transcrito.startswith("Error"):
                        self.whatsapp_sender.SendText(
                            from_number, 
                            "Lo siento, no pude entender tu mensaje de voz. ¿Podrías intentar de nuevo o enviar un mensaje de texto?",
                            message_id
                        )
                        return
                    
                    # Enviar confirmación al usuario
                    self.whatsapp_sender.SendText(
                        from_number, 
                        f"He recibido tu mensaje de voz. Te escuché decir:\n\n\"{texto_transcrito}\"\n\nProcesando tu solicitud...",
                        message_id
                    )
                    
                    # Procesar el texto transcrito
                    self.procesar_mensaje_texto(from_number, texto_transcrito, message_id)
                    
                except Exception as e:
                    logging.error(f"Error al procesar audio: {str(e)}", exc_info=True)
                    self.whatsapp_sender.SendText(
                        from_number,
                        "Lo siento, tuve problemas para procesar tu mensaje de voz. ¿Podrías intentar de nuevo o enviar un mensaje de texto?",
                        message_id
                    )
            else:
                # Otros tipos de mensajes (imágenes, documentos, etc.)
                logging.info(f"Mensaje no soportado recibido: {message.keys()}")
                self.whatsapp_sender.SendText(
                    from_number,
                    "Por ahora solo puedo procesar mensajes de texto y de voz. ¿En qué puedo ayudarte?",
                    message_id
                )
                
        except Exception as e:
            logging.error(f"Error al procesar mensaje: {str(e)}", exc_info=True)
    
    def procesar_mensaje_texto(self, numero, texto, message_id=None):
        """
        Procesa un mensaje de texto y envía la respuesta apropiada
        
        Args:
            numero (str): Número de teléfono del remitente
            texto (str): Texto del mensaje
            message_id (str, opcional): ID del mensaje para responder en contexto
        """
        # Inicializar la conversación si es nueva
        if numero not in self.conversaciones:
            self.conversaciones[numero] = {
                "estado": "inicio",
                "datos_temp": {},
                "ultimo_comando": None
            }
        
        # Obtener el estado actual de la conversación
        estado = self.conversaciones[numero]["estado"]
        datos_temp = self.conversaciones[numero]["datos_temp"]
        
        # Limpiar y preparar el texto para el procesamiento
        texto_original = texto
        texto = texto.strip()
        texto_lower = texto.lower().strip()
        
        # Mejorar la detección de comandos, incluyendo variaciones comunes
        comandos = {
            "ayuda": ["ayuda", "help", "comando", "comandos", "instrucciones", "?", "¿qué puedes hacer?", "¿qué haces?"],
            "nueva_empresa": ["nueva empresa"," Nueva empresa.", "nueva compañía", "registrar empresa", "crear empresa", "agregar empresa", "añadir empresa"],
            "listar": ["listar","Lista.","Listar.", "empresas", "lista", "listado", "mostrar empresas", "ver empresas", "listar empresas"],
            "buscar": ["buscar", "busca", "encuentra", "encontrar", "localizar", "buscame"],
            "analizar": ["analizar", "análisis", "analiza"]
        }
        
        # Intentar identificar el comando
        comando_detectado = None
        for comando, variaciones in comandos.items():
            for variacion in variaciones:
                if texto_lower == variacion or texto_lower.startswith(variacion + " "):
                    comando_detectado = comando
                    break
            if comando_detectado:
                break
            
        # Procesar comando o estado actual
        if estado == "inicio":
            if comando_detectado == "ayuda":
                self.enviar_ayuda(numero, message_id)
            elif comando_detectado == "nueva_empresa":
                # Iniciar el flujo de registro de empresa
                self.conversaciones[numero]["estado"] = "registro_nombre"
                self.whatsapp_sender.SendText(
                    numero,
                    "📋 *REGISTRO DE NUEVA EMPRESA* 📋\n\nPor favor, escribe el nombre de la empresa:",
                    message_id
                )
            elif comando_detectado == "listar":
                self.enviar_lista_empresas(numero, message_id)
            elif comando_detectado == "buscar":
                if texto_lower == "buscar" or texto_lower == "busca":
                    self.whatsapp_sender.SendText(
                        numero,
                        "Por favor, especifica qué término quieres buscar.\nEjemplo: 'buscar tecnología'",
                        message_id
                    )
                else:
                    termino = texto[len("buscar "):].strip()
                    self.buscar_empresas(numero, termino, message_id)
            elif comando_detectado == "analizar":
                if texto_lower == "analizar" or texto_lower == "analiza":
                    self.whatsapp_sender.SendText(
                        numero,
                        "Por favor, especifica qué empresa quieres analizar.\nEjemplo: 'analizar Empresa ABC'",
                        message_id
                    )
                else:
                    nombre = texto[len("analizar "):].strip()
                    self.analizar_empresa_whatsapp(numero, nombre, message_id)
            else:
                # Intentar interpretar como pregunta en lenguaje natural
                if not self.analizar_texto_whatsapp(numero, texto_original, message_id):
                    self.whatsapp_sender.SendText(
                        numero,
                        "No entiendo esa petición. Escribe *ayuda* para ver los comandos disponibles.",
                        message_id
                    )
        
        # Estados para el registro de una nueva empresa
        elif estado == "registro_nombre":
            # Guardar el nombre y solicitar el siguiente dato
            datos_temp["nombre"] = texto
            
            # Verificar si ya existe
            if texto in self.empresas:
                self.conversaciones[numero]["estado"] = "confirmar_actualizar"
                self.whatsapp_sender.SendText(
                    numero,
                    f"⚠️ La empresa *{texto}* ya existe. ¿Deseas actualizarla?\n\nResponde *sí* o *no*",
                    message_id
                )
            else:
                self.conversaciones[numero]["estado"] = "registro_valor_anual"
                self.whatsapp_sender.SendText(
                    numero,
                    "¿Cuál es el valor anual de la empresa en COP? (ingresa solo números, sin puntos ni comas)",
                    message_id
                )
        
        elif estado == "confirmar_actualizar":
            respuestas_positivas = ["si", "sí", "s", "yes", "y", "claro", "por supuesto", "vale"]
            if texto_lower in respuestas_positivas:
                self.conversaciones[numero]["estado"] = "registro_valor_anual"
                self.whatsapp_sender.SendText(
                    numero,
                    "¿Cuál es el valor anual de la empresa en COP? (ingresa solo números, sin puntos ni comas)",
                    message_id
                )
            else:
                self.conversaciones[numero]["estado"] = "inicio"
                self.whatsapp_sender.SendText(
                    numero,
                    "Operación cancelada. ¿En qué más puedo ayudarte?",
                    message_id
                )
        
        elif estado == "registro_valor_anual":
            try:
                # Limpiar el texto para convertirlo a número
                valor_texto = texto.replace(',', '').replace('.', '').strip()
                if not valor_texto.isdigit():
                    raise ValueError("No es un número")
                    
                valor = float(valor_texto)
                datos_temp["valor_anual"] = valor
                self.conversaciones[numero]["estado"] = "registro_ganancias"
                self.whatsapp_sender.SendText(
                    numero,
                    "¿Cuáles son las ganancias de la empresa en COP? (ingresa solo números, sin puntos ni comas)",
                    message_id
                )
            except ValueError:
                self.whatsapp_sender.SendText(
                    numero,
                    "⚠️ Por favor ingresa un valor numérico válido (solo números, sin puntos ni comas).",
                    message_id
                )
        
        elif estado == "registro_ganancias":
            try:
                # Limpiar el texto para convertirlo a número
                valor_texto = texto.replace(',', '').replace('.', '').strip()
                if not valor_texto.isdigit():
                    raise ValueError("No es un número")
                    
                valor = float(valor_texto)
                datos_temp["ganancias"] = valor
                self.conversaciones[numero]["estado"] = "registro_sector"
                self.whatsapp_sender.SendText(
                    numero,
                    "¿A qué sector pertenece la empresa?",
                    message_id
                )
            except ValueError:
                self.whatsapp_sender.SendText(
                    numero,
                    "⚠️ Por favor ingresa un valor numérico válido (solo números, sin puntos ni comas).",
                    message_id
                )
        
        elif estado == "registro_sector":
            datos_temp["sector"] = texto
            self.conversaciones[numero]["estado"] = "registro_empleados"
            self.whatsapp_sender.SendText(
                numero,
                "¿Cuántos empleados tiene la empresa? (ingresa solo el número)",
                message_id
            )
        
        elif estado == "registro_empleados":
            try:
                # Limpiar el texto para convertirlo a número
                valor_texto = texto.strip()
                if not valor_texto.isdigit():
                    raise ValueError("No es un número entero")
                    
                empleados = int(valor_texto)
                datos_temp["empleados"] = empleados
                self.conversaciones[numero]["estado"] = "registro_activos"
                self.whatsapp_sender.SendText(
                    numero,
                    "¿Cuál es el valor en activos de la empresa en COP? (ingresa solo números, sin puntos ni comas)",
                    message_id
                )
            except ValueError:
                self.whatsapp_sender.SendText(
                    numero,
                    "⚠️ Por favor ingresa un número entero válido.",
                    message_id
                )
        
        elif estado == "registro_activos":
            try:
                # Limpiar el texto para convertirlo a número
                valor_texto = texto.replace(',', '').replace('.', '').strip()
                if not valor_texto.isdigit():
                    raise ValueError("No es un número")
                    
                valor = float(valor_texto)
                datos_temp["activos"] = valor
                self.conversaciones[numero]["estado"] = "registro_cartera"
                self.whatsapp_sender.SendText(
                    numero,
                    "¿Cuál es el valor de la cartera de la empresa en COP? (ingresa solo números, sin puntos ni comas)",
                    message_id
                )
            except ValueError:
                self.whatsapp_sender.SendText(
                    numero,
                    "⚠️ Por favor ingresa un valor numérico válido (solo números, sin puntos ni comas).",
                    message_id
                )
        
        elif estado == "registro_cartera":
            try:
                # Limpiar el texto para convertirlo a número
                valor_texto = texto.replace(',', '').replace('.', '').strip()
                if not valor_texto.isdigit():
                    raise ValueError("No es un número")
                    
                valor = float(valor_texto)
                datos_temp["cartera"] = valor
                self.conversaciones[numero]["estado"] = "registro_deudas"
                self.whatsapp_sender.SendText(
                    numero,
                    "¿Cuál es el valor de las deudas de la empresa en COP? (ingresa solo números, sin puntos ni comas)",
                    message_id
                )
            except ValueError:
                self.whatsapp_sender.SendText(
                    numero,
                    "⚠️ Por favor ingresa un valor numérico válido (solo números, sin puntos ni comas).",
                    message_id
                )
        
        elif estado == "registro_deudas":
            try:
                # Limpiar el texto para convertirlo a número
                valor_texto = texto.replace(',', '').replace('.', '').strip()
                if not valor_texto.isdigit():
                    raise ValueError("No es un número")
                    
                valor = float(valor_texto)
                datos_temp["deudas"] = valor
                
                # Finalizar el registro
                self.finalizar_registro_empresa(numero, message_id)
                
            except ValueError:
                self.whatsapp_sender.SendText(
                    numero,
                    "⚠️ Por favor ingresa un valor numérico válido (solo números, sin puntos ni comas).",
                    message_id
                )
    
    def finalizar_registro_empresa(self, numero, message_id=None):
        """Finaliza el proceso de registro de una empresa"""
        try:
            # Obtener los datos temporales
            datos = self.conversaciones[numero]["datos_temp"]
            
            # Enviar mensaje de procesamiento
            self.whatsapp_sender.SendText(
                numero,
                "⏳ Estoy generando el análisis de la empresa...",
                message_id
            )
            
            # Generar análisis
            analisis = self.generar_analisis_nlp(
                datos["nombre"], datos["sector"], datos["valor_anual"], 
                datos["ganancias"], datos["empleados"], datos["activos"], 
                datos["cartera"], datos["deudas"]
            )
            
            # Guardar datos completos
            datos["fecha_registro"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            datos["analisis_nlp"] = analisis
            
            # Almacenar en el diccionario y guardar
            self.empresas[datos["nombre"]] = datos
            self.guardar_datos()
            
            # Crear mensaje de texto con el análisis
            resultado = self.crear_mensaje_analisis(
                datos["nombre"], datos["sector"], datos["valor_anual"], 
                datos["ganancias"], datos["empleados"], datos["activos"], 
                datos["cartera"], datos["deudas"], analisis
            )
            
            # Enviar el análisis como texto siempre
            self.whatsapp_sender.SendText(
                numero,
                resultado,
                message_id
            )
            
            # Decidir si enviar también como audio (40% probabilidad)
            if self.debe_responder_con_audio():
                resumen = f"El análisis de la empresa {datos['nombre']} ha sido completado. La salud financiera se clasifica como {analisis['evaluacion']['categoria']} con una puntuación de {analisis['evaluacion']['puntuacion']} sobre 100."
                audio_bytes = texto_a_voz(resumen)
                
                if audio_bytes:
                    self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
            
            # Restablecer el estado
            self.conversaciones[numero]["estado"] = "inicio"
            self.conversaciones[numero]["datos_temp"] = {}
            
        except Exception as e:
            logging.error(f"Error al finalizar registro: {str(e)}", exc_info=True)
            self.whatsapp_sender.SendText(
                numero,
                "❌ Ocurrió un error al procesar los datos. Por favor intenta nuevamente.",
                message_id
            )
            self.conversaciones[numero]["estado"] = "inicio"
    
    def crear_mensaje_analisis(self, nombre, sector, valor_anual, ganancias, empleados, 
                           activos, cartera, deudas, analisis):
        """Crea un mensaje de WhatsApp con el análisis de la empresa"""
        # Formatear valores monetarios
        valor_anual_fmt = f"{valor_anual:,.0f}".replace(",", ".")
        ganancias_fmt = f"{ganancias:,.0f}".replace(",", ".")
        activos_fmt = f"{activos:,.0f}".replace(",", ".")
        cartera_fmt = f"{cartera:,.0f}".replace(",", ".")
        deudas_fmt = f"{deudas:,.0f}".replace(",", ".")
        
        # Formatear indicadores
        liquidez = analisis['indicadores_financieros']['liquidez']
        margen = analisis['indicadores_financieros']['margen_ganancia']
        endeudamiento = analisis['indicadores_financieros']['ratio_endeudamiento']
        productividad = analisis['indicadores_financieros']['productividad_empleado']
        productividad_fmt = f"{productividad:,.0f}".replace(",", ".")
        
        resultado = f"""
🏢 *ANÁLISIS FINANCIERO DE {nombre.upper()}* 🏢

El análisis de la empresa *{nombre}*, perteneciente al sector *{sector}*, ha sido completado.

📊 *DATOS FINANCIEROS:*
• Valor anual: ${valor_anual_fmt} COP
• Ganancias: ${ganancias_fmt} COP
• Activos: ${activos_fmt} COP
• Cartera: ${cartera_fmt} COP
• Deudas: ${deudas_fmt} COP
• Número de empleados: {empleados}

📈 *INDICADORES CALCULADOS:*
• Ratio de liquidez: {liquidez:.2f}
• Margen de ganancia: {margen:.2f}%
• Ratio de endeudamiento: {endeudamiento:.2f}%
• Productividad por empleado: ${productividad_fmt} COP

🌟 *EVALUACIÓN GLOBAL:*
• Categoría: *{analisis['evaluacion']['categoria']}*
• Puntuación: {analisis['evaluacion']['puntuacion']}/100

📝 *DESCRIPCIÓN:*
{analisis['evaluacion']['descripcion']}

🔍 *RECOMENDACIONES:*"""

        # Generar recomendaciones
        recomendaciones = []
        if analisis['indicadores_financieros']['liquidez'] < 1:
            recomendaciones.append("• Mejorar la posición de liquidez para cubrir obligaciones a corto plazo.")
        
        if analisis['indicadores_financieros']['margen_ganancia'] < 10:
            recomendaciones.append("• Implementar estrategias para aumentar el margen de ganancia.")
        
        if analisis['indicadores_financieros']['ratio_endeudamiento'] > 50:
            recomendaciones.append("• Reducir el nivel de endeudamiento para mejorar la estabilidad financiera.")
        
        if analisis['indicadores_financieros']['productividad_empleado'] < 100000000:
            recomendaciones.append("• Revisar la productividad por empleado para optimizar recursos.")
        
        # Si no hay recomendaciones específicas
        if not recomendaciones:
            recomendaciones.append("• La empresa muestra indicadores saludables. Se recomienda mantener las estrategias actuales.")
        
        for recomendacion in recomendaciones:
            resultado += f"\n{recomendacion}"
        
        return resultado
    
    def enviar_ayuda(self, numero, message_id=None):
        """Envía el mensaje de ayuda al usuario"""
        mensaje = """
🤖 *COMANDOS DISPONIBLES* 🤖

• *ayuda* - Muestra esta información
• *nueva empresa* - Registra una nueva empresa
• *listar* - Muestra las empresas registradas
• *analizar [nombre]* - Analiza una empresa específica
• *buscar [término]* - Busca empresas por nombre o sector

También puedes hacer preguntas naturales como:
• "¿Cuál es la mejor empresa?"
• "¿Cuáles son los indicadores de [empresa]?"
• "¿Qué recomendaciones hay para [empresa]?"
• "¿Cuántas empresas hay en el sistema?"
• "¿Qué sectores hay registrados?"

Puedes enviar mensajes de texto o de voz para interactuar con el sistema.
"""
        # Enviar mensaje de texto siempre
        self.whatsapp_sender.SendText(numero, mensaje, message_id)
        
        # Decidir si enviar también como audio (40% de las veces)
        if self.debe_responder_con_audio():
            # Simplificar el mensaje para audio
            audio_mensaje = "Estos son los comandos disponibles: ayuda para mostrar información, nueva empresa para registrar, listar para ver empresas, analizar nombre para ver análisis y buscar término para encontrar empresas. También puedes hacer preguntas naturales sobre empresas."
            audio_bytes = texto_a_voz(audio_mensaje)
            if audio_bytes:
                self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
    
    def enviar_lista_empresas(self, numero, message_id=None):
        """Envía la lista de empresas registradas"""
        if not self.empresas:
            mensaje = "📭 No hay empresas registradas en el sistema."
            self.whatsapp_sender.SendText(numero, mensaje, message_id)
            
            # Decidir si enviar también como audio
            if self.debe_responder_con_audio():
                audio_bytes = texto_a_voz("No hay empresas registradas en el sistema.")
                if audio_bytes:
                    self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
            return
        
        mensaje = "📋 *EMPRESAS REGISTRADAS* 📋\n\n"
        mensaje += "*NOMBRE* | *SECTOR* | *SALUD FINANCIERA*\n"
        mensaje += "—————————————————————\n"
        
        for nombre, datos in self.empresas.items():
            mensaje += f"• *{datos['nombre']}* | {datos['sector']} | {datos['analisis_nlp']['evaluacion']['categoria']}\n"
        
        mensaje += "\nPara ver detalles de una empresa específica, escribe:\n*analizar [nombre de la empresa]*"
        
        # Enviar mensaje de texto siempre
        self.whatsapp_sender.SendText(numero, mensaje, message_id)
        
        # Decidir si enviar también como audio
        if self.debe_responder_con_audio():
            # Crear un mensaje simplificado para audio
            empresas_list = [f"{datos['nombre']} en el sector {datos['sector']}" for datos in self.empresas.values()]
            audio_mensaje = f"Empresas registradas: {', '.join(empresas_list[:5])}"
            if len(empresas_list) > 5:
                audio_mensaje += " y otras más"
            audio_bytes = texto_a_voz(audio_mensaje)
            if audio_bytes:
                self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
    
    def buscar_empresas(self, numero, termino, message_id=None):
        """Busca empresas por nombre o sector"""
        if not self.empresas:
            mensaje = "📭 No hay empresas registradas en el sistema."
            self.whatsapp_sender.SendText(numero, mensaje, message_id)
            return
        
        termino = termino.lower()
        resultados = []
        
        for nombre, datos in self.empresas.items():
            if termino in nombre.lower() or termino in datos['sector'].lower():
                resultados.append(datos)
        
        if not resultados:
            mensaje = f"🔍 No se encontraron empresas con el término *{termino}*."
            self.whatsapp_sender.SendText(numero, mensaje, message_id)
            
            # Decidir si enviar también como audio
            if self.debe_responder_con_audio():
                audio_bytes = texto_a_voz(f"No se encontraron empresas con el término {termino}.")
                if audio_bytes:
                    self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
            return
        
        mensaje = f"🔍 *RESULTADOS DE BÚSQUEDA PARA '{termino}'* 🔍\n\n"
        mensaje += "*NOMBRE* | *SECTOR* | *SALUD FINANCIERA*\n"
        mensaje += "—————————————————————\n"
        
        for datos in resultados:
            mensaje += f"• *{datos['nombre']}* | {datos['sector']} | {datos['analisis_nlp']['evaluacion']['categoria']}\n"
        
        mensaje += "\nPara ver detalles de una empresa específica, escribe:\n*analizar [nombre de la empresa]*"
        
        # Enviar mensaje de texto siempre
        self.whatsapp_sender.SendText(numero, mensaje, message_id)
        
        # Decidir si enviar también como audio
        if self.debe_responder_con_audio():
            # Crear un mensaje simplificado para audio
            resultados_list = [f"{datos['nombre']} en el sector {datos['sector']}" for datos in resultados[:3]]
            audio_mensaje = f"Encontré {len(resultados)} empresas que coinciden con {termino}: {', '.join(resultados_list)}"
            if len(resultados) > 3:
                audio_mensaje += " y otras más"
            audio_bytes = texto_a_voz(audio_mensaje)
            if audio_bytes:
                self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
    
    def analizar_empresa_whatsapp(self, numero, nombre, message_id=None):
        """Analiza una empresa y envía los resultados por WhatsApp"""
        if not nombre:
            self.whatsapp_sender.SendText(
                numero,
                "⚠️ Por favor especifica el nombre de la empresa.",
                message_id
            )
            return
            
        if nombre not in self.empresas:
            # Buscar sugerencias similares
            sugerencias = [n for n in self.empresas.keys() if nombre.lower() in n.lower()]
            
            mensaje = f"❌ No se encontró la empresa *{nombre}*."
            
            if sugerencias:
                mensaje += "\n\n¿Quizás quisiste decir?\n"
                for sugerencia in sugerencias:
                    mensaje += f"• *{sugerencia}*\n"
            
            self.whatsapp_sender.SendText(numero, mensaje, message_id)
            
            # Decidir si enviar también como audio
            if self.debe_responder_con_audio():
                audio_mensaje = f"No se encontró la empresa {nombre}."
                if sugerencias:
                    audio_mensaje += f" ¿Quizás quisiste decir {', '.join(sugerencias[:2])}?"
                audio_bytes = texto_a_voz(audio_mensaje)
                if audio_bytes:
                    self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
            return
        
        # Obtener datos de la empresa
        datos = self.empresas[nombre]
        
        # Crear mensaje de análisis
        resultado = self.crear_mensaje_analisis(
            datos["nombre"], datos["sector"], datos["valor_anual"], 
            datos["ganancias"], datos["empleados"], datos["activos"],
            datos["cartera"], datos["deudas"], datos["analisis_nlp"]
        )
        
        # Enviar mensaje de texto siempre
        self.whatsapp_sender.SendText(numero, resultado, message_id)
        
        # Decidir si enviar también como audio (40% probabilidad)
        if self.debe_responder_con_audio():
            resumen = f"Aquí está el análisis de {datos['nombre']}. La salud financiera se clasifica como {datos['analisis_nlp']['evaluacion']['categoria']} con una puntuación de {datos['analisis_nlp']['evaluacion']['puntuacion']} sobre 100."
            audio_bytes = texto_a_voz(resumen)
            
            if audio_bytes:
                self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
    
    def analizar_texto_whatsapp(self, numero, pregunta, message_id=None):
        """Analiza preguntas en lenguaje natural y responde vía WhatsApp"""
        pregunta = pregunta.lower()
        
        # Verificar si es una pregunta sobre empresas específicas
        for nombre in self.empresas.keys():
            if nombre.lower() in pregunta:
                if "indicadores" in pregunta or "financi" in pregunta:
                    datos = self.empresas[nombre]
                    liquidez = datos['analisis_nlp']['indicadores_financieros']['liquidez']
                    margen = datos['analisis_nlp']['indicadores_financieros']['margen_ganancia']
                    endeudamiento = datos['analisis_nlp']['indicadores_financieros']['ratio_endeudamiento']
                    
                    mensaje = f"📊 *INDICADORES FINANCIEROS DE {nombre}* 📊\n\n"
                    mensaje += f"• Liquidez: {liquidez:.2f}\n"
                    mensaje += f"• Margen de ganancia: {margen:.2f}%\n"
                    mensaje += f"• Ratio de endeudamiento: {endeudamiento:.2f}%\n"
                    
                    # Enviar mensaje de texto siempre
                    self.whatsapp_sender.SendText(numero, mensaje, message_id)
                    
                    # Decidir si enviar también como audio
                    if self.debe_responder_con_audio():
                        audio_mensaje = f"Indicadores financieros de {nombre}: Liquidez {liquidez:.2f}, Margen de ganancia {margen:.2f} por ciento, y Ratio de endeudamiento {endeudamiento:.2f} por ciento."
                        audio_bytes = texto_a_voz(audio_mensaje)
                        if audio_bytes:
                            self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
                    
                    return True
                    
                elif "recomend" in pregunta:
                    self.enviar_recomendaciones_whatsapp(numero, nombre, message_id)
                    return True
                else:
                    self.analizar_empresa_whatsapp(numero, nombre, message_id)
                    return True
        
        # Preguntas generales sobre todas las empresas
        if "mejor empresa" in pregunta or "empresa con mejor" in pregunta:
            self.enviar_mejor_empresa_whatsapp(numero, message_id)
            return True
        elif "peor empresa" in pregunta or "empresa con peor" in pregunta:
            self.enviar_peor_empresa_whatsapp(numero, message_id)
            return True
        elif "cuántas empresas" in pregunta or "número de empresas" in pregunta or "cuantas empresas" in pregunta:
            mensaje = f"📊 Hay *{len(self.empresas)}* empresas registradas en el sistema."
            
            # Enviar mensaje de texto siempre
            self.whatsapp_sender.SendText(numero, mensaje, message_id)
            
            # Decidir si enviar también como audio
            if self.debe_responder_con_audio():
                audio_mensaje = f"Hay {len(self.empresas)} empresas registradas en el sistema."
                audio_bytes = texto_a_voz(audio_mensaje)
                if audio_bytes:
                    self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
            
            return True
        elif "sectores" in pregunta:
            self.enviar_sectores_whatsapp(numero, message_id)
            return True
        
        # No se encontró una pregunta específica
        return False
    
    def enviar_recomendaciones_whatsapp(self, numero, nombre, message_id=None):
        """Envía recomendaciones para una empresa específica por WhatsApp"""
        if nombre not in self.empresas:
            mensaje = f"❌ No se encontró la empresa *{nombre}*."
            self.whatsapp_sender.SendText(numero, mensaje, message_id)
            return
            
        datos = self.empresas[nombre]
        analisis = datos["analisis_nlp"]
        
        mensaje = f"🔍 *RECOMENDACIONES PARA {nombre.upper()}* 🔍\n\n"
        
        # Generar recomendaciones basadas en los indicadores
        recomendaciones = []
        
        if analisis['indicadores_financieros']['liquidez'] < 1:
            recomendaciones.append("• Mejorar la posición de liquidez para cubrir obligaciones a corto plazo.")
        
        if analisis['indicadores_financieros']['margen_ganancia'] < 10:
            recomendaciones.append("• Implementar estrategias para aumentar el margen de ganancia.")
        
        if analisis['indicadores_financieros']['ratio_endeudamiento'] > 50:
            recomendaciones.append("• Reducir el nivel de endeudamiento para mejorar la estabilidad financiera.")
        
        if analisis['indicadores_financieros']['productividad_empleado'] < 100000000:
            recomendaciones.append("• Revisar la productividad por empleado para optimizar recursos.")
        
        # Si no hay recomendaciones específicas
        if not recomendaciones:
            recomendaciones.append("• La empresa muestra indicadores saludables. Se recomienda mantener las estrategias actuales.")
        
        for recomendacion in recomendaciones:
            mensaje += f"{recomendacion}\n"
        
        # Enviar mensaje de texto siempre
        self.whatsapp_sender.SendText(numero, mensaje, message_id)
        
        # Decidir si enviar también como audio (40% probabilidad)
        if self.debe_responder_con_audio():
            texto_recomendaciones = f"Recomendaciones para {nombre}: " + ", ".join([r.replace("•", "") for r in recomendaciones])
            audio_bytes = texto_a_voz(texto_recomendaciones)
            if audio_bytes:
                self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
    
    def enviar_mejor_empresa_whatsapp(self, numero, message_id=None):
        """Envía información sobre la empresa con mejor salud financiera"""
        if not self.empresas:
            mensaje = "📭 No hay empresas registradas en el sistema."
            self.whatsapp_sender.SendText(numero, mensaje, message_id)
            return
            
        mejor_empresa = None
        mejor_puntuacion = -1
        
        for nombre, datos in self.empresas.items():
            puntuacion = datos["analisis_nlp"]["evaluacion"]["puntuacion"]
            if puntuacion > mejor_puntuacion:
                mejor_puntuacion = puntuacion
                mejor_empresa = datos
        
        mensaje = f"🏆 *EMPRESA CON MEJOR SALUD FINANCIERA* 🏆\n\n"
        mensaje += f"• Nombre: *{mejor_empresa['nombre']}*\n"
        mensaje += f"• Sector: {mejor_empresa['sector']}\n"
        mensaje += f"• Puntuación: {mejor_empresa['analisis_nlp']['evaluacion']['puntuacion']}/100\n"
        mensaje += f"• Categoría: *{mejor_empresa['analisis_nlp']['evaluacion']['categoria']}*\n\n"
        mensaje += f"Para ver el análisis completo, escribe:\n*analizar {mejor_empresa['nombre']}*"
        
        # Enviar mensaje de texto siempre
        self.whatsapp_sender.SendText(numero, mensaje, message_id)
        
        # Decidir si enviar también como audio (40% probabilidad)
        if self.debe_responder_con_audio():
            texto_voz = f"La empresa con mejor salud financiera es {mejor_empresa['nombre']} del sector {mejor_empresa['sector']} con una puntuación de {mejor_empresa['analisis_nlp']['evaluacion']['puntuacion']} sobre 100."
            audio_bytes = texto_a_voz(texto_voz)
            if audio_bytes:
                self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
    
    def enviar_peor_empresa_whatsapp(self, numero, message_id=None):
        """Envía información sobre la empresa con peor salud financiera"""
        if not self.empresas:
            mensaje = "📭 No hay empresas registradas en el sistema."
            self.whatsapp_sender.SendText(numero, mensaje, message_id)
            return
            
        peor_empresa = None
        peor_puntuacion = float('inf')
        
        for nombre, datos in self.empresas.items():
            puntuacion = datos["analisis_nlp"]["evaluacion"]["puntuacion"]
            if puntuacion < peor_puntuacion:
                peor_puntuacion = puntuacion
                peor_empresa = datos
        
        mensaje = f"⚠️ *EMPRESA CON SALUD FINANCIERA MÁS BAJA* ⚠️\n\n"
        mensaje += f"• Nombre: *{peor_empresa['nombre']}*\n"
        mensaje += f"• Sector: {peor_empresa['sector']}\n"
        mensaje += f"• Puntuación: {peor_empresa['analisis_nlp']['evaluacion']['puntuacion']}/100\n"
        mensaje += f"• Categoría: *{peor_empresa['analisis_nlp']['evaluacion']['categoria']}*\n\n"
        mensaje += f"Para ver el análisis completo, escribe:\n*analizar {peor_empresa['nombre']}*"
        
        # Enviar mensaje de texto siempre
        self.whatsapp_sender.SendText(numero, mensaje, message_id)
        
        # Decidir si enviar también como audio (40% probabilidad)
        if self.debe_responder_con_audio():
            texto_voz = f"La empresa con peor salud financiera es {peor_empresa['nombre']} del sector {peor_empresa['sector']} con una puntuación de {peor_empresa['analisis_nlp']['evaluacion']['puntuacion']} sobre 100."
            audio_bytes = texto_a_voz(texto_voz)
            if audio_bytes:
                self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
    
    def enviar_sectores_whatsapp(self, numero, message_id=None):
        """Envía información sobre los sectores registrados"""
        if not self.empresas:
            mensaje = "📭 No hay empresas registradas en el sistema."
            self.whatsapp_sender.SendText(numero, mensaje, message_id)
            return
            
        sectores = {}
        for nombre, datos in self.empresas.items():
            sector = datos["sector"]
            if sector in sectores:
                sectores[sector] += 1
            else:
                sectores[sector] = 1
        
        mensaje = "🏭 *SECTORES REGISTRADOS* 🏭\n\n"
        
        for sector, cantidad in sectores.items():
            mensaje += f"• *{sector}*: {cantidad} empresa"
            if cantidad != 1:
                mensaje += "s"
            mensaje += "\n"
        
        # Enviar mensaje de texto siempre
        self.whatsapp_sender.SendText(numero, mensaje, message_id)
        
        # Decidir si enviar también como audio (40% probabilidad)
        if self.debe_responder_con_audio():
            sectores_list = [f"{sector} con {cantidad} empresas" for sector, cantidad in list(sectores.items())[:5]]
            audio_mensaje = f"Los sectores registrados son: {', '.join(sectores_list)}"
            if len(sectores) > 5:
                audio_mensaje += " y otros más"
            audio_bytes = texto_a_voz(audio_mensaje)
            if audio_bytes:
                self.whatsapp_sender.SendVoiceNote(numero, audio_bytes)
    
    def generar_analisis_nlp(self, nombre, sector, valor_anual, ganancias, 
                           empleados, activos, cartera, deudas):
        """
        Genera un análisis basado en NLP y financiero de la empresa
        
        Args:
            nombre (str): Nombre de la empresa
            sector (str): Sector de la empresa
            valor_anual (float): Valor anual de la empresa en COP
            ganancias (float): Ganancias de la empresa en COP
            empleados (int): Número de empleados
            activos (float): Valor en activos de la empresa en COP
            cartera (float): Valor de la cartera de la empresa en COP
            deudas (float): Valor de las deudas de la empresa en COP
            
        Returns:
            dict: Análisis completo de la empresa
        """
        resultado = {}
        
        # 1. Tokenización del nombre de la empresa y sector
        try:
            tokens_nombre = self.word_tokenize(nombre.lower())
            tokens_sector = self.word_tokenize(sector.lower())
        except Exception as e:
            logging.error(f"Error en tokenización: {e}")
            tokens_nombre = nombre.lower().split()
            tokens_sector = sector.lower().split()
        
        resultado["tokenizacion"] = {
            "nombre": tokens_nombre,
            "sector": tokens_sector
        }
        
        # 2. Lematización (simplificada si no hay NLTK)
        if self.use_nltk:
            try:
                from nltk.stem import WordNetLemmatizer
                lemmatizer = WordNetLemmatizer()
                lemmas_nombre = [lemmatizer.lemmatize(token) for token in tokens_nombre]
                lemmas_sector = [lemmatizer.lemmatize(token) for token in tokens_sector]
            except:
                lemmas_nombre = tokens_nombre
                lemmas_sector = tokens_sector
        else:
            # Sin NLTK, solo usamos los tokens como lemas
            lemmas_nombre = tokens_nombre
            lemmas_sector = tokens_sector
        
        resultado["lematizacion"] = {
            "nombre": lemmas_nombre,
            "sector": lemmas_sector
        }
        
        # 3. POS Tagging (Etiquetado de partes del discurso)
        try:
            pos_nombre = self.pos_tag(tokens_nombre)
            pos_sector = self.pos_tag(tokens_sector)
        except Exception as e:
            logging.error(f"Error en etiquetado POS: {e}")
            pos_nombre = [(token, "UNK") for token in tokens_nombre]
            pos_sector = [(token, "UNK") for token in tokens_sector]
        
        resultado["pos_tagging"] = {
            "nombre": pos_nombre,
            "sector": pos_sector
        }
        
        # 4. Embeddings utilizando spaCy (si está disponible)
        if self.use_spacy:
            try:
                doc_nombre = self.nlp(" ".join(tokens_nombre))
                doc_sector = self.nlp(" ".join(tokens_sector))
                # Guardar solo los valores del vector para facilitar la serialización
                resultado["embeddings"] = {
                    "nombre": doc_nombre.vector.tolist(),
                    "sector": doc_sector.vector.tolist()
                }
            except Exception as e:
                logging.error(f"Error al generar embeddings: {e}")
                resultado["embeddings"] = {
                    "nombre": [0] * 10,  # Vector vacío como fallback
                    "sector": [0] * 10
                }
        else:
            # Sin spaCy, creamos embeddings ficticios
            resultado["embeddings"] = {
                "nombre": [0] * 10,
                "sector": [0] * 10
            }
        
        # 5. Análisis financiero para categorización
        # Calcular indicadores financieros
        liquidez = activos / deudas if deudas > 0 else float('inf')
        margen_ganancia = (ganancias / valor_anual) * 100 if valor_anual > 0 else 0
        ratio_endeudamiento = (deudas / activos) * 100 if activos > 0 else float('inf')
        productividad_empleado = valor_anual / empleados if empleados > 0 else 0
        
        resultado["indicadores_financieros"] = {
            "liquidez": liquidez,
            "margen_ganancia": margen_ganancia,
            "ratio_endeudamiento": ratio_endeudamiento,
            "productividad_empleado": productividad_empleado
        }
        
        # Evaluación de la salud financiera
        puntuacion = 0
        max_puntuacion = 100
        
        # Evaluar liquidez (25%)
        if liquidez >= 2:
            puntuacion += 25
        elif liquidez >= 1.5:
            puntuacion += 20
        elif liquidez >= 1:
            puntuacion += 15
        elif liquidez >= 0.5:
            puntuacion += 10
        else:
            puntuacion += 5
        
        # Evaluar margen de ganancia (25%)
        if margen_ganancia >= 20:
            puntuacion += 25
        elif margen_ganancia >= 15:
            puntuacion += 20
        elif margen_ganancia >= 10:
            puntuacion += 15
        elif margen_ganancia >= 5:
            puntuacion += 10
        else:
            puntuacion += 5
        
        # Evaluar endeudamiento (25%)
        if ratio_endeudamiento <= 30:
            puntuacion += 25
        elif ratio_endeudamiento <= 40:
            puntuacion += 20
        elif ratio_endeudamiento <= 50:
            puntuacion += 15
        elif ratio_endeudamiento <= 60:
            puntuacion += 10
        else:
            puntuacion += 5
        
        # Evaluar productividad (25%)
        if productividad_empleado >= 200000000:  # 200 millones por empleado
            puntuacion += 25
        elif productividad_empleado >= 150000000:
            puntuacion += 20
        elif productividad_empleado >= 100000000:
            puntuacion += 15
        elif productividad_empleado >= 50000000:
            puntuacion += 10
        else:
            puntuacion += 5
        
        # Categorizar la salud financiera
        if puntuacion >= 85:
            categoria = "Excelente"
            descripcion = "La empresa muestra una salud financiera excepcional."
        elif puntuacion >= 70:
            categoria = "Muy Buena"
            descripcion = "La empresa tiene una posición financiera sólida."
        elif puntuacion >= 55:
            categoria = "Buena"
            descripcion = "La empresa presenta indicadores financieros estables."
        elif puntuacion >= 40:
            categoria = "Regular"
            descripcion = "La empresa tiene áreas que necesitan mejoras."
        elif puntuacion >= 25:
            categoria = "Deficiente"
            descripcion = "La empresa presenta problemas financieros significativos."
        else:
            categoria = "Crítica"
            descripcion = "La empresa requiere atención urgente en su gestión financiera."
        
        resultado["evaluacion"] = {
            "puntuacion": puntuacion,
            "max_puntuacion": max_puntuacion,
            "categoria": categoria,
            "descripcion": descripcion
        }
        
        return resultado