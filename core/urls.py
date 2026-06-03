from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from inventario.views import (
    RegistrarAsistenciaView, 
    HistorialAsistenciaView, 
    InventarioMaterialesView, 
    ListarProyectosView,
    MaterialesPorProyectoView,
    ProyectosPorMaterialView,
    CrearMaterialCatalogoView,
    CrearProyectoRapidoView
)

urlpatterns = [
    path('admin/', admin.site.urls),

    #Crear material
    path('api/inventario/materiales/crear/', CrearMaterialCatalogoView.as_view(), name='crear-material-catalogo'),

    # NUEVA RUTA DE PROYECTOS RÁPIDOS
    path('api/inventario/proyectos/crear/', CrearProyectoRapidoView.as_view(), name='crear-proyecto-rapido'),
    
    # Rutas del Token (Login)
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Rutas de Asistencia
    path('api/asistencia/', RegistrarAsistenciaView.as_view(), name='registrar_asistencia'),
    path('api/asistencia/historial/', HistorialAsistenciaView.as_view(), name='historial_asistencia'),
    
    # Módulo de Material de Bodega
    path('api/inventario/materiales/', InventarioMaterialesView.as_view(), name='inventario_materiales'),
    path('api/inventario/proyectos/', ListarProyectosView.as_view(), name='listar_proyectos'),
    
    # Reportes cruzados (Materiales <-> Proyectos)
    path('api/inventario/proyectos/<int:proyecto_id>/materiales/', MaterialesPorProyectoView.as_view(), name='materiales_por_proyecto'),
    
    #¿En qué proyectos está este material específico?
    path('api/inventario/materiales/<int:material_id>/proyectos/', ProyectosPorMaterialView.as_view(), name='proyectos_por_material'),
]