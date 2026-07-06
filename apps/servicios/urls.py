from django.urls import path

from .views import (
    CategoriaServicioDetalleView,
    CategoriaServicioListCreateView,
    DiagnosticoCapilarDetalleView,
    DiagnosticoCapilarListCreateView,
    PaqueteServicioActivarView,
    PaqueteServicioDetalleView,
    PaqueteServicioListCreateView,
    RecomendacionCuidadoActivarView,
    RecomendacionCuidadoDetalleView,
    RecomendacionCuidadoListCreateView,
    ServicioDetalleView,
    ServicioListCreateView,
    TrabajoPortafolioDetalleView,
    TrabajoPortafolioListCreateView,
    TrabajoPortafolioRevisionView,
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

    # Registrar diagnostico capilar del cliente.
    path('diagnosticos-capilares/', DiagnosticoCapilarListCreateView.as_view(), name='diagnostico-capilar-list-create'),
    path('diagnosticos-capilares/<int:id_diagnostico>/', DiagnosticoCapilarDetalleView.as_view(), name='diagnostico-capilar-detalle'),

    # Gestionar portafolio de trabajos realizados.
    path('portafolio-trabajos/', TrabajoPortafolioListCreateView.as_view(), name='trabajo-portafolio-list-create'),
    path('portafolio-trabajos/<int:id_trabajo>/', TrabajoPortafolioDetalleView.as_view(), name='trabajo-portafolio-detalle'),
    path('portafolio-trabajos/<int:id_trabajo>/revisar/', TrabajoPortafolioRevisionView.as_view(), name='trabajo-portafolio-revisar'),
]
