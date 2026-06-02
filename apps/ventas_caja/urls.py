from django.urls import path

from .views import (
    MetodoPagoDetalleView,
    MetodoPagoListCreateView,
    PlanComisionDetalleView,
    PlanComisionListCreateView,
)


# Rutas del paquete ventas_caja.
# En este ciclo solo se implementan CU13 y CU14.
urlpatterns = [
    path('metodos-pago/', MetodoPagoListCreateView.as_view(), name='metodo-pago-list-create'),
    path('metodos-pago/<int:id_metodo_pago>/', MetodoPagoDetalleView.as_view(), name='metodo-pago-detalle'),
    path('planes-comision/', PlanComisionListCreateView.as_view(), name='plan-comision-list-create'),
    path('planes-comision/<int:id_plan_comision>/', PlanComisionDetalleView.as_view(), name='plan-comision-detalle'),
]
