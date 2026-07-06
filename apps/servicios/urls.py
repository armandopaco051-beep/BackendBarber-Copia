from django.urls import path

from .views import (
    CategoriaServicioDetalleView,
    CategoriaServicioListCreateView,
    PaqueteServicioActivarView,
    PaqueteServicioDetalleView,
    PaqueteServicioListCreateView,
    RecomendacionCuidadoActivarView,
    RecomendacionCuidadoDetalleView,
    RecomendacionCuidadoListCreateView,
    ServicioDetalleView,
    ServicioListCreateView,
)


# Rutas del paquete servicios.
# CU6 usa /categorias/, CU10 usa /servicios/, CU28 usa /paquetes/
# y CU29 usa /recomendaciones/.
urlpatterns = [
    # CRUD de categorias de servicios.
    path('categorias/', CategoriaServicioListCreateView.as_view(), name='categoria-servicio-list-create'),
    path('categorias/<int:id_categoria>/', CategoriaServicioDetalleView.as_view(), name='categoria-servicio-detalle'),

    # CRUD de servicios.
    path('servicios/', ServicioListCreateView.as_view(), name='servicio-list-create'),
    path('servicios/<int:id_servicio>/', ServicioDetalleView.as_view(), name='servicio-detalle'),

    # CU28: paquetes de servicios.
    path('paquetes/', PaqueteServicioListCreateView.as_view(), name='paquete-servicio-list-create'),
    path('paquetes/<int:id_paquete>/', PaqueteServicioDetalleView.as_view(), name='paquete-servicio-detalle'),
    path('paquetes/<int:id_paquete>/activar/', PaqueteServicioActivarView.as_view(), name='paquete-servicio-activar'),

    # CU29: recomendaciones de cuidado posteriores al servicio.
    path('recomendaciones/', RecomendacionCuidadoListCreateView.as_view(), name='recomendacion-cuidado-list-create'),
    path('recomendaciones/<int:id_recomendacion>/', RecomendacionCuidadoDetalleView.as_view(), name='recomendacion-cuidado-detalle'),
    path('recomendaciones/<int:id_recomendacion>/activar/', RecomendacionCuidadoActivarView.as_view(), name='recomendacion-cuidado-activar'),
]
