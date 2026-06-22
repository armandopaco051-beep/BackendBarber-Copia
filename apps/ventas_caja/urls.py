from django.urls import path

from .views import (
    CajaAbrirView,
    CajaCerrarView,
    CajaConsultarView,
    CajaEstadoView,
    CajaHistorialView,
    CajaResumenView,
    MetodoPagoDetalleView,
    MetodoPagoListCreateView,
    MovimientoCajaAnularView,
    MovimientoCajaDetalleView,
    MovimientoCajaListCreateView,
    PlanComisionDetalleView,
    PlanComisionListCreateView,
    VentaAnularView,
    VentaConfirmarView,
    VentaComprobanteView,
    VentaDetalleView,
    VentaListCreateView,
)


# Rutas del paquete ventas_caja.
# En este ciclo se implementan CU13, CU14 y CU18.
urlpatterns = [
    path('metodos-pago/', MetodoPagoListCreateView.as_view(), name='metodo-pago-list-create'),
    path('metodos-pago/<int:id_metodo_pago>/', MetodoPagoDetalleView.as_view(), name='metodo-pago-detalle'),
    path('planes-comision/', PlanComisionListCreateView.as_view(), name='plan-comision-list-create'),
    path('planes-comision/<int:id_plan_comision>/', PlanComisionDetalleView.as_view(), name='plan-comision-detalle'),
    path('caja/estado/', CajaEstadoView.as_view(), name='caja-estado'),
    path('caja/abrir/', CajaAbrirView.as_view(), name='caja-abrir'),
    path('caja/consultar/', CajaConsultarView.as_view(), name='caja-consultar'),
    path('caja/historial/', CajaHistorialView.as_view(), name='caja-historial'),
    path('caja/cerrar/', CajaCerrarView.as_view(), name='caja-cerrar'),
    path('caja/resumen/', CajaResumenView.as_view(), name='caja-resumen'),
    path('caja/movimientos/', MovimientoCajaListCreateView.as_view(), name='movimiento-caja-list-create'),
    path('caja/movimientos/<int:id_movimiento_caja>/', MovimientoCajaDetalleView.as_view(), name='movimiento-caja-detalle'),
    path('caja/movimientos/<int:id_movimiento_caja>/anular/', MovimientoCajaAnularView.as_view(), name='movimiento-caja-anular'),
    path('ventas/', VentaListCreateView.as_view(), name='venta-list-create'),
    path('ventas/<int:id_venta>/', VentaDetalleView.as_view(), name='venta-detalle'),
    path('ventas/<int:id_venta>/confirmar/', VentaConfirmarView.as_view(), name='venta-confirmar'),
    path('ventas/<int:id_venta>/anular/', VentaAnularView.as_view(), name='venta-anular'),
    path('ventas/<int:id_venta>/comprobante/', VentaComprobanteView.as_view(), name='venta-comprobante'),
]
