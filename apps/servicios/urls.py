from django.urls import path

from .views import (
    CategoriaServicioDetalleView,
    CategoriaServicioListCreateView,
    ServicioDetalleView,
    ServicioListCreateView,
)


# Rutas del paquete servicios.
# CU6 usa /categorias/ y CU10 usa /servicios/.
urlpatterns = [
    # CRUD de categorias de servicios.
    path('categorias/', CategoriaServicioListCreateView.as_view(), name='categoria-servicio-list-create'),
    path('categorias/<int:id_categoria>/', CategoriaServicioDetalleView.as_view(), name='categoria-servicio-detalle'),

    # CRUD de servicios.
    path('servicios/', ServicioListCreateView.as_view(), name='servicio-list-create'),
    path('servicios/<int:id_servicio>/', ServicioDetalleView.as_view(), name='servicio-detalle'),
]
