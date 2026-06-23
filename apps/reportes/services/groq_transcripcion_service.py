import re

import requests
from django.conf import settings


class ReporteVozError(Exception):
    def __init__(self, mensaje, status_code=422):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


class GroqTranscripcionService:
    @staticmethod
    def _clean_text(texto):
        limpio = re.sub(r'\s+', ' ', texto or '').strip()
        limpio = re.sub(r'^[\s\.,;:!?\-_"\']+|[\s\.,;:!?\-_"\']+$', '', limpio)
        return limpio

    @classmethod
    def _validar_configuracion(cls):
        if not getattr(settings, 'GROQ_API_KEY', ''):
            raise ReporteVozError(
                'La transcripcion de voz no esta configurada. Agrega GROQ_API_KEY en el backend.',
                status_code=422,
            )

        if not getattr(settings, 'GROQ_BASE_URL', ''):
            raise ReporteVozError('Falta configurar GROQ_BASE_URL.', status_code=422)

        if not getattr(settings, 'GROQ_TRANSCRIPTION_MODEL', ''):
            raise ReporteVozError('Falta configurar GROQ_TRANSCRIPTION_MODEL.', status_code=422)

    @classmethod
    def transcribir_audio(cls, audio_file):
        cls._validar_configuracion()

        url = f"{settings.GROQ_BASE_URL.rstrip('/')}/audio/transcriptions"
        headers = {
            'Authorization': f'Bearer {settings.GROQ_API_KEY}',
        }
        payload = {
            'model': settings.GROQ_TRANSCRIPTION_MODEL,
            'language': 'es',
            'temperature': '0',
            'response_format': 'json',
        }
        content_type = getattr(audio_file, 'content_type', None) or 'application/octet-stream'

        try:
            audio_file.seek(0)
            response = requests.post(
                url,
                headers=headers,
                data=payload,
                files={'file': (audio_file.name, audio_file, content_type)},
                timeout=settings.GROQ_TIMEOUT,
            )
        except requests.Timeout as exc:
            raise ReporteVozError('La transcripcion de voz excedio el tiempo de espera.', status_code=422) from exc
        except requests.RequestException as exc:
            raise ReporteVozError('No se pudo conectar con el servicio de transcripcion.', status_code=422) from exc

        if not response.ok:
            try:
                data = response.json()
            except ValueError:
                data = {}
            detalle = data.get('error', {}).get('message') or data.get('message') or 'Groq no pudo transcribir el audio.'
            raise ReporteVozError(f'Error al transcribir el audio: {detalle}', status_code=422)

        try:
            data = response.json()
        except ValueError as exc:
            raise ReporteVozError('Groq devolvio una respuesta invalida.', status_code=422) from exc

        texto = cls._clean_text(data.get('text') or data.get('transcript') or '')
        if not texto:
            raise ReporteVozError('No se pudo obtener una transcripcion valida del audio.', status_code=422)
        return texto

