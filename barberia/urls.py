"""
URL configuration for barberia project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(url='/api/docs/')),  # ← agrega esta línea
    path('admin/', admin.site.urls),

    # Ruta historica del proyecto. Se mantiene para no romper Swagger/frontend existente.
    path('api/seguridad/', include('apps.seguridad.urls')),

    # Nuevos paquetes funcionales organizados por responsabilidad.t
    path('api/usuario/', include('apps.usuario.urls')),
    path('api/servicios/', include('apps.servicios.urls')),
    path('api/citas/', include('apps.citas.urls')),
    path('api/cliente/', include('apps.cliente.urls')),
    path('api/inventario/', include('apps.inventario.urls')),
    path('api/ventas-caja/', include('apps.ventas_caja.urls')),
    path('api/reportes/', include('apps.reportes.urls')),
     # ── Documentación ────────────────────────────────────────
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

