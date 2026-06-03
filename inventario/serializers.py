from rest_framework import serializers
from .models import Material, MovimientoMaterial, Proyecto

class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = ['id', 'nombre', 'descripcion', 'unidad_medida', 'stock_bodega', 'proveedor', 'costo_unitario']

class MovimientoMaterialSerializer(serializers.ModelSerializer):
    nombre_material = serializers.CharField(source='material.nombre', read_only=True)
    nombre_proyecto = serializers.CharField(source='proyecto.nombre', read_only=True)
    nombre_bodeguero = serializers.CharField(source='usuario_bodega.username', read_only=True)
    nombre_tecnico = serializers.CharField(source='tecnico_receptor.username', read_only=True)

    class Meta:
        model = MovimientoMaterial
        fields = [
            'id', 'proyecto', 'nombre_proyecto', 'material', 'nombre_material', 
            'cantidad', 'fecha_hora', 'tipo', 'usuario_bodega', 'nombre_bodeguero',
            'tecnico_receptor', 'nombre_tecnico', 'estado_checklist', 'notas_novedad'
        ]