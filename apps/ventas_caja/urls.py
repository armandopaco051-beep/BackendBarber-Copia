from django.urls import path

from .views import (
    CajaAbrirView,
    CajaCerrarView,
    CajaConsultarView,
    CajaEstadoView,
    CajaHistorialView,
    MetodoPagoDetalleView,
    MetodoPagoListCreateView,
    PlanComisionDetalleView,
    PlanComisionListCreateView,
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
]
