import re
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class ReporteVozInterpreterService:
    BUSINESS_TIMEZONE = ZoneInfo('America/La_Paz')
    REPORTES = [
        {
            'id': 'productos-vendidos',
            'keywords': ['productos vendidos', 'producto vendido', 'ventas de productos'],
        },
        {
            'id': 'servicios-realizados',
            'keywords': ['servicios realizados', 'servicios atendidos', 'atenciones', 'servicios del dia'],
        },
        {
            'id': 'caja-movimientos',
            'keywords': ['movimientos de caja', 'cierre de caja', 'apertura', 'caja'],
        },
        {
            'id': 'inventario',
            'keywords': ['productos en stock', 'stock bajo', 'sin stock', 'inventario', 'stock'],
        },
        {
            'id': 'comisiones',
            'keywords': ['ganancia de barberos', 'porcentaje de barberos', 'comisiones', 'comision'],
        },
        {
            'id': 'servicios-promocion',
            'keywords': ['servicios con promocion', 'servicios con promociones', 'promocion', 'promociones', 'descuentos'],
        },
        {
            'id': 'ventas',
            'keywords': ['ingresos', 'cobros', 'venta', 'ventas'],
        },
    ]

    REPORTES_CON_ESTADO_VENTA = {'ventas', 'productos-vendidos', 'servicios-realizados', 'comisiones'}
    @staticmethod
    def normalizar_texto(texto):
        texto = (texto or '').lower().strip()
        texto = ''.join(
            caracter for caracter in unicodedata.normalize('NFD', texto)
            if unicodedata.category(caracter) != 'Mn'
        )
        return re.sub(r'\s+', ' ', texto)

    @classmethod
    def _detectar_accion(cls, texto):
        if any(keyword in texto for keyword in ['generar', 'descargar', 'exportar', 'crear archivo']):
            return 'download'
        if any(keyword in texto for keyword in ['mostrar', 'ver', 'consultar', 'vista previa']):
            return 'preview'
        return 'preview'

    @classmethod
    def _detectar_formato(cls, texto, accion):
        if any(keyword in texto for keyword in ['excel', 'xlsx', 'xls']):
            return 'excel'
        if 'pdf' in texto:
            return 'pdf'
        if accion == 'download':
            return 'pdf'
        return None

    @classmethod
    def _detectar_tipo_reporte(cls, texto):
        mejor_reporte = None
        mejor_puntaje = 0

        for reporte in cls.REPORTES:
            puntaje = sum(1 for keyword in reporte['keywords'] if keyword in texto)
            if puntaje > mejor_puntaje:
                mejor_puntaje = puntaje
                mejor_reporte = reporte['id']

        return mejor_reporte

    @classmethod
    def _detectar_rango_fechas(cls, texto):
        hoy = datetime.now(cls.BUSINESS_TIMEZONE).date()

        if 'hoy' in texto:
            return {
                'fecha_inicio': hoy.isoformat(),
                'fecha_fin': hoy.isoformat(),
            }

        if 'ayer' in texto:
            ayer = hoy - timedelta(days=1)
            return {
                'fecha_inicio': ayer.isoformat(),
                'fecha_fin': ayer.isoformat(),
            }

        if 'este mes' in texto or 'mes actual' in texto:
            inicio_mes = hoy.replace(day=1)
            return {
                'fecha_inicio': inicio_mes.isoformat(),
                'fecha_fin': hoy.isoformat(),
            }

        if 'mes pasado' in texto:
            fin_mes_anterior = hoy.replace(day=1) - timedelta(days=1)
            inicio_mes_anterior = fin_mes_anterior.replace(day=1)
            return {
                'fecha_inicio': inicio_mes_anterior.isoformat(),
                'fecha_fin': fin_mes_anterior.isoformat(),
            }

        return {}

    @classmethod
    def _detectar_estado_venta(cls, texto, tipo_reporte):
        if tipo_reporte not in cls.REPORTES_CON_ESTADO_VENTA:
            return {}

        if 'pagadas' in texto or 'pagada' in texto:
            return {'estado_venta': 'PAGADA'}
        if 'pendientes' in texto or 'pendiente' in texto:
            return {'estado_venta': 'PENDIENTE_PAGO'}
        if any(keyword in texto for keyword in ['canceladas', 'cancelada', 'anuladas', 'anulada']):
            return {'estado_venta': 'ANULADA'}
        return {}

    @classmethod
    def _detectar_filtros(cls, texto, tipo_reporte):
        filtros = {}
        filtros.update(cls._detectar_rango_fechas(texto))
        filtros.update(cls._detectar_estado_venta(texto, tipo_reporte))

        if 'stock bajo' in texto:
            filtros['stock_bajo'] = True
        if any(keyword in texto for keyword in ['sin stock', 'agotado', 'agotados']):
            filtros['sin_stock'] = True
        if any(keyword in texto for keyword in ['con diferencia', 'diferencia de caja', 'faltante', 'sobrante']):
            filtros['con_diferencia'] = True

        if tipo_reporte == 'servicios-promocion':
            filtros['promocion_aplicada'] = True

        return filtros

    @classmethod
    def interpretar(cls, texto):
        texto_normalizado = cls.normalizar_texto(texto)
        accion = cls._detectar_accion(texto_normalizado)
        formato = cls._detectar_formato(texto_normalizado, accion)
        tipo_reporte = cls._detectar_tipo_reporte(texto_normalizado)

        if not tipo_reporte:
            return {
                'accion': 'needs_clarification',
                'tipo_reporte': None,
                'formato': formato,
                'filtros_detectados': {},
                'mensaje': 'No se pudo identificar el reporte solicitado. Prueba con: Mostrar ventas de hoy, Descargar inventario en Excel o Consultar movimientos de caja con diferencia.',
            }

        return {
            'accion': accion,
            'tipo_reporte': tipo_reporte,
            'formato': formato,
            'filtros_detectados': cls._detectar_filtros(texto_normalizado, tipo_reporte),
            'mensaje': 'Comando de voz interpretado correctamente.',
        }
