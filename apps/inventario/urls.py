from django.urls import path

from .views import (
    CategoriaProductoDetalleView,
    CategoriaProductoListCreateView,
    InsumoDetalleView,
    InsumoListCreateView,
    InsumoStockMinimoView,
    MarcaDetalleView,
    MarcaListCreateView,
    MovimientoInventarioListView,
    ProductoDetalleView,
    ProductoListCreateView,
    ProductoStockBajoView,
)


urlpatterns = [
    path('categorias/', CategoriaProductoListCreateView.as_view(), name='categoria-producto-list-create'),
    path('categorias/<int:id_categoria>/', CategoriaProductoDetalleView.as_view(), name='categoria-producto-detalle'),
    path('marcas/', MarcaListCreateView.as_view(), name='marca-list-create'),
    path('marcas/<int:id_marca>/', MarcaDetalleView.as_view(), name='marca-detalle'),
    path('productos/', ProductoListCreateView.as_view(), name='producto-list-create'),
    path('productos/<int:id_producto>/', ProductoDetalleView.as_view(), name='producto-detalle'),
    path('productos/stock-bajo/', ProductoStockBajoView.as_view(), name='producto-stock-bajo'),
    path('insumos/', InsumoListCreateView.as_view(), name='insumo-list-create'),
    path('insumos/<int:id_insumo>/', InsumoDetalleView.as_view(), name='insumo-detalle'),
    path('insumos/stock-minimo/', InsumoStockMinimoView.as_view(), name='insumo-stock-minimo'),
    path('movimientos/', MovimientoInventarioListView.as_view(), name='movimiento-inventario-list'),
]
