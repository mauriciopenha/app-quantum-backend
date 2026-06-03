from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Proyecto, Material, MovimientoMaterial, Herramienta, TransaccionHerramienta, Asistencia, EtapaProyecto

# 1. CONFIGURACIÓN AVANZADA PARA VER EL ID DE LOS PROYECTOS
@admin.register(Proyecto)
class ProyectoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre') # <-- Muestra el ID y el Nombre
    search_fields = ('nombre',)

# 2. CONFIGURACIÓN AVANZADA PARA VER EL ID DE LOS MATERIALES
@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'stock_bodega', 'unidad_medida') # <-- Muestra el ID, Nombre y Stock
    search_fields = ('nombre',)

# Estos se quedan igual por ahora de forma simple
admin.site.register(MovimientoMaterial)
admin.site.register(Herramienta)
admin.site.register(TransaccionHerramienta)


# Configuración avanzada para ver la Asistencia en el panel
@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    # Columnas que se verán en la lista de asistencias
    list_display = ('usuario', 'tipo', 'fecha_hora_formateada', 'horas_totales_dia', 'horas_extras_dia', 'ver_mapa')
    # Filtros laterales para buscar rápido por técnico o tipo
    list_filter = ('tipo', 'usuario', 'fecha_hora')

    def fecha_hora_formateada(self, obj):
        # Muestra la fecha más amigable
        return obj.fecha_hora.strftime('%d/%m/%Y %H:%M')
    fecha_hora_formateada.short_description = 'Fecha y Hora'

    def ver_mapa(self, obj):
        # Crea un enlace web real que abre Google Maps con las coordenadas guardadas
        url = f"https://www.google.com/maps?q={obj.latitud},{obj.longitud}"
        return format_html('<a href="{}" target="_blank" style="color: #264b5d; font-weight: bold; text-decoration: underline;">📍 Ver en mapa</a>', url)
    ver_mapa.short_description = 'Ubicación GPS'


@admin.register(EtapaProyecto)
class EtapaProyectoAdmin(admin.ModelAdmin):
    list_display = ('proyecto', 'nombre_etapa', 'porcentaje_avance', 'semaforo_estado', 'notas_progreso', 'ultima_actualizacion')
    list_filter = ('proyecto', 'nombre_etapa')
    list_editable = ('porcentaje_avance', 'notas_progreso') # Te permite cambiar el avance rápido sin abrir el registro

    def semaforo_estado(self, obj):
        color = obj.get_estado_color()
        if color == 'ROJO':
            return mark_safe('<span style="background-color: #ffcccc; color: #cc0000; padding: 5px 10px; border-radius: 5px; font-weight: bold;">🔴 SIN INICIAR</span>')
        elif color == 'NARANJA':
            return mark_safe('<span style="background-color: #ffe6cc; color: #cc6600; padding: 5px 10px; border-radius: 5px; font-weight: bold;">🟠 EN PROCESO</span>')
        else:
            return mark_safe('<span style="background-color: #d4edda; color: #155724; padding: 5px 10px; border-radius: 5px; font-weight: bold;">🟢 FINALIZADO</span>')
            
    semaforo_estado.short_description = 'Estado Visual'