from django.urls import path

from .views import (
    ReporteCajaMovimientosView,
    ReporteCajaMovimientosPreviewView,
    ReporteComisionesView,
    ReporteComisionesPreviewView,
    ReporteInventarioView,
    ReporteInventarioPreviewView,
    ReporteProductosVendidosView,
    ReporteProductosVendidosPreviewView,
    ReporteServiciosPromocionView,
    ReporteServiciosPromocionPreviewView,
    ReporteServiciosRealizadosView,
    ReporteServiciosRealizadosPreviewView,
    ReporteVentasView,
    ReporteVentasPreviewView,
)


urlpatterns = [
    path('ventas/', ReporteVentasView.as_view(), name='reporte-ventas'),
    path('ventas/preview/', ReporteVentasPreviewView.as_view(), name='reporte-ventas-preview'),
    path('productos-vendidos/', ReporteProductosVendidosView.as_view(), name='reporte-productos-vendidos'),
    path('productos-vendidos/preview/', ReporteProductosVendidosPreviewView.as_view(), name='reporte-productos-vendidos-preview'),
    path('servicios-realizados/', ReporteServiciosRealizadosView.as_view(), name='reporte-servicios-realizados'),
    path('servicios-realizados/preview/', ReporteServiciosRealizadosPreviewView.as_view(), name='reporte-servicios-realizados-preview'),
    path('caja-movimientos/', ReporteCajaMovimientosView.as_view(), name='reporte-caja-movimientos'),
    path('caja-movimientos/preview/', ReporteCajaMovimientosPreviewView.as_view(), name='reporte-caja-movimientos-preview'),
    path('inventario/', ReporteInventarioView.as_view(), name='reporte-inventario'),
    path('inventario/preview/', ReporteInventarioPreviewView.as_view(), name='reporte-inventario-preview'),
    path('comisiones/', ReporteComisionesView.as_view(), name='reporte-comisiones'),
    path('comisiones/preview/', ReporteComisionesPreviewView.as_view(), name='reporte-comisiones-preview'),
    path('servicios-promocion/', ReporteServiciosPromocionView.as_view(), name='reporte-servicios-promocion'),
    path('servicios-promocion/preview/', ReporteServiciosPromocionPreviewView.as_view(), name='reporte-servicios-promocion-preview'),
]
