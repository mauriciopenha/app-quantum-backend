import decimal
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, time
from django.db.models.signals import post_save
from django.dispatch import receiver



class Proyecto(models.Model):
    nombre = models.CharField(max_length=150)
    descripcion = models.TextField(blank=True, null=True)
    fecha_inicio = models.DateField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre

class EtapaProyecto(models.Model):
    ESTADOS_COLOR = [
        ('ROJO', '🔴 Sin Iniciar / Pausado'),
        ('NARANJA', '🟠 En Proceso / Pendiente'),
        ('VERDE', '🟢 Finalizado / OK'),
    ]

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='etapas')
    nombre_etapa = models.CharField(max_length=100, help_text="Ej: Instalación de paneles, Conexión AC, etc.")
    porcentaje_avance = models.IntegerField(default=0, help_text="Progreso de 0 a 100")
    notas_progreso = models.TextField(blank=True, null=True, help_text="¿Qué falta o por qué se pausó?")
    ultima_actualizacion = models.DateTimeField(auto_now=True)

    def get_estado_color(self):
        """Calcula el estado visual basado en el porcentaje de avance"""
        if self.porcentaje_avance == 0:
            return 'ROJO'
        elif self.porcentaje_avance >= 100:
            return 'VERDE'
        else:
            return 'NARANJA'

    def __str__(self):
        return f"{self.proyecto.nombre} - {self.nombre_etapa} ({self.porcentaje_avance}%)"
    
@receiver(post_save, sender=Proyecto)
def crear_etapas_proyecto_automaticas(sender, instance, created, **kwargs):
    """
    Cada vez que se crea un proyecto nuevo, se le asignan automáticamente
    las 6 etapas estándar de una instalación solar.
    """
    if created:
        etapas_estandar = [
            "Estructura de soporte para paneles",
            "Instalación física de paneles solares",
            "Conexión eléctrica en DC (Corriente Continua)",
            "Instalación y montaje de inversor",
            "Conexión eléctrica en AC (Corriente Alterna)",
            "Sistema de puesta a tierra",
        ]
        
        for etapa in etapas_estandar:
            EtapaProyecto.objects.create(
                proyecto=instance,
                nombre_etapa=etapa,
                porcentaje_avance=0
            )

# MATERIALES

class Material(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True, null=True)
    unidad_medida = models.CharField(max_length=20, help_text="Ej. Metros, Unidades, Kg")
    stock_bodega = models.IntegerField(default=0)
    proveedor = models.CharField(max_length=100, blank=True, null=True)
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return self.nombre

class MovimientoMaterial(models.Model):
    TIPO_MOVIMIENTO = [
        ('ENTRADA_BODEGA', 'Ingreso a Bodega (Abastecimiento)'),
        ('SALIDA_PROYECTO', 'Salida a Proyecto (Obra)'),
        ('DEVOLUCION_PROYECTO', 'Devolución desde Proyecto'),
        ('COMPRA_DIRECTA', 'Compra Directa a Obra (No pasa por bodega)'), # <-- NUEVO TIPO
    ]
    ESTADO_RECEPCION = [
        ('PENDIENTE', 'Pendiente por revisar por el Técnico'),
        ('ACEPTADO', 'Aceptado por el Técnico (Checklist OK)'),
        ('RECHAZADO', 'Rechazado / Con Novedad'),
    ]

    # MODIFICADO: Ahora proyecto es OPCIONAL (null=True, blank=True) para permitir ENTRADA_BODEGA
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, null=True, blank=True)
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    cantidad = models.IntegerField()
    fecha_hora = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=20, choices=TIPO_MOVIMIENTO)
    usuario_bodega = models.ForeignKey(User, on_delete=models.CASCADE, related_name='movimientos_despachados')
    
    # NUEVO CAMPO: Proveedor opcional para compras o entradas
    proveedor = models.CharField(max_length=100, blank=True, null=True, help_text="Nombre del proveedor externo (Opcional)")

    # NUEVOS CAMPOS PARA EL CONTROL DE ENTREGA
    tecnico_receptor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='materiales_recibidos', help_text="Técnico que recibe el material en obra")
    estado_checklist = models.CharField(max_length=15, choices=ESTADO_RECEPCION, default='PENDIENTE')
    notas_novedad = models.TextField(blank=True, null=True, help_text="Notas en caso de que falte algo o llegue dañado")

    def __str__(self):
        destino = self.proyecto.nombre if self.proyecto else "Bodega Principal"
        return f"{self.tipo} - {self.cantidad} {self.material.nombre} -> {destino}"

# LOGICA ACTULIZACION DE MATERIAL
@receiver(post_save, sender=MovimientoMaterial)
def actualizar_inventario_material(sender, instance, created, **kwargs):
    """
    Se activa automáticamente cada vez que se registra un movimiento de material.
    Suma o resta el stock de la bodega según el tipo de movimiento.
    """
    if created:  # Solo se ejecuta cuando el movimiento es NUEVO
        material = instance.material
        
        if instance.tipo == 'ENTRADA_BODEGA':
            material.stock_bodega += instance.cantidad
            
        elif instance.tipo == 'SALIDA_PROYECTO':
            # Nota: Más adelante podemos validar que no saquen más de lo que hay
            material.stock_bodega -= instance.cantidad
            
        elif instance.tipo == 'DEVOLUCION_PROYECTO':
            material.stock_bodega += instance.cantidad
            
        # Guardamos los cambios en el material
        material.save()


# HERRAMIENTAS

class Herramienta(models.Model):
    ESTADOS = [
        ('BUENO', 'Buen Estado'),
        ('MANTENIMIENTO', 'En Mantenimiento'),
        ('DEBAJA', 'Dada de Baja / Dañada'),
    ]

    nombre = models.CharField(max_length=100)
    codigo_serie = models.CharField(max_length=50, unique=True, help_text="Código único o número de serie")
    estado = models.CharField(max_length=20, choices=ESTADOS, default='BUENO')
    
    # Control de ubicación actual de la herramienta
    en_bodega = models.BooleanField(default=True)
    proyecto_actual = models.ForeignKey(Proyecto, on_delete=models.SET_NULL, blank=True, null=True)
    tecnico_actual = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='herramientas_a_cargo')

    def __str__(self):
        return f"{self.nombre} ({self.codigo_serie})"
    
# PRESTAMO DE HERRAMIENTAS

class TransaccionHerramienta(models.Model):
    ESTADOS_TRANSPASO = [
        ('PENDIENTE', 'Pendiente de Aceptación'),
        ('ACEPTADO', 'Aceptado (Traspaso Exitoso)'),
        ('RECHAZADO', 'Rechazado'),
    ]

    herramienta = models.ForeignKey(Herramienta, on_delete=models.CASCADE)
    tecnico_origen = models.ForeignKey(User, on_delete=models.PROTECT, related_name='traspasos_enviados', help_text="Quién entrega")
    tecnico_destino = models.ForeignKey(User, on_delete=models.PROTECT, related_name='traspasos_recibidos', help_text="Quién recibe")
    proyecto = models.ForeignKey(Proyecto, on_delete=models.SET_NULL, blank=True, null=True, help_text="Proyecto al que va la herramienta")
    estado = models.CharField(max_length=20, choices=ESTADOS_TRANSPASO, default='PENDIENTE')
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_confirmacion = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Traspaso de {self.herramienta.nombre} - Estado: {self.estado}"

# PRESTAMOS DE HERRAMIENTA
@receiver(post_save, sender=TransaccionHerramienta)
def procesar_traspaso_herramienta(sender, instance, created, **kwargs):
    """
    Se activa cuando se crea o actualiza un traspaso de herramienta.
    Solo cambia el dueño real de la herramienta cuando el estado pasa a 'ACEPTADO'.
    """
    # Si la transacción fue aceptada
    if instance.estado == 'ACEPTADO':
        herramienta = instance.herramienta
        
        # Hacemos el cambio oficial de dueño y proyecto
        herramienta.tecnico_actual = instance.tecnico_destino
        herramienta.proyecto_actual = instance.proyecto
        herramienta.en_bodega = False  # Ya está en manos de un técnico en campo
        
        # Guardamos los cambios en la herramienta
        herramienta.save()


# GEOLOCALIZACION
class Asistencia(models.Model):
    TIPO_MARCACION = [
        ('ENTRADA', 'Marcación de Entrada'),
        ('SALIDA', 'Marcación de Salida'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    fecha_hora = models.DateTimeField(auto_now_add=True)
    tipo = models.CharField(max_length=10, choices=TIPO_MARCACION)
    
    # Campos para guardar la geolocalización de la app móvil
    latitud = models.DecimalField(max_digits=9, decimal_places=6)
    longitud = models.DecimalField(max_digits=9, decimal_places=6)

    # RECOPILAR HORAS EXTRAS
    horas_totales_dia = models.DecimalField(max_digits=4, decimal_places=2, default=0.0)
    horas_extras_dia = models.DecimalField(max_digits=4, decimal_places=2, default=0.0)
    
    def __str__(self):
        return f"{self.usuario.username} - {self.tipo} - {self.fecha_hora.strftime('%d/%m/%Y %H:%M')}"
    

#CALCULAR HORAS EXTRAS
@receiver(post_save, sender=Asistencia)
def calcular_horas_jornada(sender, instance, created, **kwargs):
    """
    Cuando se registra una SALIDA, busca la ENTRADA del técnico del mismo día
    y calcula las horas totales y las extras automáticas.
    """
    if created and instance.tipo == 'SALIDA':
        # Buscamos la marcación de ENTRADA del mismo usuario el día de hoy
        fecha_hoy = instance.fecha_hora.date()
        entrada = Asistencia.objects.filter(
            usuario=instance.usuario,
            tipo='ENTRADA',
            fecha_hora__date=fecha_hoy
        ).first()
        
        if entrada:
            # Calculamos la diferencia de tiempo entre entrada y salida
            diferencia = instance.fecha_hora - entrada.fecha_hora
            segundos_totales = diferencia.total_seconds()
            horas_totales = decimal.Decimal(segundos_totales / 3600)
            
            # Restamos 1 hora de almuerzo obligatoria si trabajó más de 5 horas
            if horas_totales > 5:
                horas_laboradas = horas_totales - decimal.Decimal(1.0)
            else:
                horas_laboradas = horas_totales
                
            # Las horas ordinarias son 8. Lo que pase de 8 son extras.
            horas_extras = horas_laboradas - decimal.Decimal(8.0)
            if horas_extras < 0:
                horas_extras = decimal.Decimal(0.0)
                
            # Guardamos los cálculos en la marcación de salida usando 'update' 
            # para evitar que la señal se ejecute en un bucle infinito
            Asistencia.objects.filter(id=instance.id).update(
                horas_totales_dia=round(horas_laboradas, 2),
                horas_extras_dia=round(horas_extras, 2)
            )


class MaterialCompraDirecta(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name='compras_directas')
    nombre_material = models.CharField(max_length=150, help_text="Nombre escrito a mano en la app")
    cantidad = models.IntegerField()
    fecha_hora = models.DateTimeField(auto_now_add=True)
    proveedor = models.CharField(max_length=100, blank=True, null=True)
    usuario_bodega = models.ForeignKey(User, on_delete=models.CASCADE, related_name='compras_directas_despachadas')
    notas = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.nombre_material} (x{self.cantidad}) - Proyecto: {self.proyecto.nombre}"