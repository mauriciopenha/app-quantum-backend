from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.db import transaction  # <-- IMPORTANTE: Para asegurar que se guarden todos los ítems o ninguno
import holidays
from .models import Material, Asistencia, MovimientoMaterial, Proyecto, MaterialCompraDirecta, EtapaProyecto, ReporteAvanceDiario
from .serializers import MaterialSerializer, MovimientoMaterialSerializer
from decimal import Decimal, InvalidOperation

# 2. La función matemática y las constantes se importan desde .utils 
from .utils import calcular_distancia_haversine, LATITUD_PERMITIDA, LONGITUD_PERMITIDA, RADIO_MAXIMO_METROS


@method_decorator(csrf_exempt, name='dispatch') 
class RegistrarAsistenciaView(APIView):
    permission_classes = [IsAuthenticated] 

    def post(self, request):
        try:
            user = request.user 
            tipo = request.data.get('tipo') 
            
            try:
                latitud_celular = float(request.data.get('latitud'))
                longitud_celular = float(request.data.get('longitud'))
            except (TypeError, ValueError):
                return Response(
                    {"error": "Las coordenadas GPS enviadas no tienen un formato válido."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 1. Calculamos la distancia real
            distancia_al_sitio = calcular_distancia_haversine(
                latitud_celular, longitud_celular, 
                LATITUD_PERMITIDA, LONGITUD_PERMITIDA
            )

            print(f"--> {user.username} marcando. Distancia al objetivo: {distancia_al_sitio:.2f} metros.")

            # 2. NUEVA LOGICA DE FLEXIBILIDAD: Ya no bloqueamos. Evaluamos el rango.
            fuera_de_rango = distancia_al_sitio > RADIO_MAXIMO_METROS
            
            # Preparamos un mensaje claro para el supervisor o la respuesta
            if fuera_de_rango:
                mensaje_respuesta = f"¡Asistencia registrada FUERA DE RANGO! Estás a {round(distancia_al_sitio/1000, 2)} km del sitio."
                print(f"⚠️ ALERTA: {user.username} guardó asistencia fuera del perímetro.")
            else:
                mensaje_respuesta = f"¡Asistencia registrada con éxito en punto de trabajo!"

            # 3. Guardamos en la base de datos (Pasa directo)
            asistencia = Asistencia.objects.create(
                usuario=user, 
                tipo=tipo,
                latitud=latitud_celular,
                longitud=longitud_celular,
                fecha_hora=timezone.now()
            )

            return Response(
                {
                    "mensaje": mensaje_respuesta, 
                    "id": asistencia.id,
                    "distancia_metros": round(distancia_al_sitio, 2),
                    "fuera_de_rango": fuera_de_rango
                }, 
                status=status.HTTP_201_CREATED
            )
            
        except Exception as e:
            print(f"Error en registro de asistencia: {str(e)}")
            return Response(
                {"error": "Error interno del servidor al procesar la ubicación."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

class HistorialAsistenciaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user = request.user
            asistencias = Asistencia.objects.filter(usuario=user).order_by('-fecha_hora')
            co_holidays = holidays.Colombia(years=[2025, 2026, 2027])
            historial_data = []

            for registro in asistencias:
                fecha_local = timezone.localtime(registro.fecha_hora)
                num_dia_semana = fecha_local.weekday()
                es_festivo = fecha_local.date() in co_holidays

                if num_dia_semana == 6 or es_festivo:
                    detalle = "Festivo/Domingo"
                elif num_dia_semana == 5:
                    detalle = "Sábado"
                else:
                    detalle = "Ordinario"

                historial_data.append({
                    "id": registro.id,
                    "tipo": registro.tipo,
                    "fecha_hora": fecha_local.strftime("%d/%m/%Y %I:%M %p"),
                    "horas_normales": "Calculado al cierre",
                    "horas_extras": "Calculado al cierre",
                    "detalle_dia": detalle,
                    "latitud": registro.latitud,   
                    "longitud": registro.longitud  
                })
            
            return Response(historial_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(f"Error al obtener historial: {str(e)}")
            return Response(
                {"error": "Error al obtener el historial de asistencias."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =====================================================================
# CLASE RESTAURADA: MANEJA LOS MOVIMIENTOS Y FLUJOS DE STOCK GENERAL
# =====================================================================
class InventarioMaterialesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        materiales = Material.objects.all().order_by('nombre')
        serializer = MaterialSerializer(materiales, many=True)
        return Response(serializer.data)

    @transaction.atomic
    def post(self, request):
        try:
            items = request.data.get('items', [])
            tipo_movimiento = request.data.get('tipo_movimiento')
            proyecto_id = request.data.get('proyecto_id')

            if not items or not tipo_movimiento:
                return Response(
                    {"error": "Faltan parámetros obligatorios: 'items' o 'tipo_movimiento'."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            proyecto = None
            if proyecto_id:
                try:
                    proyecto = Proyecto.objects.get(id=proyecto_id)
                except Proyecto.DoesNotExist:
                    return Response({"error": "El proyecto especificado no existe."}, status=status.HTTP_404_NOT_FOUND)

            for item in items:
                material_id = item.get('material')
                
                # BLINDAJE DE DATOS: Convertimos a Decimal de forma segura
                try:
                    raw_cantidad = item.get('cantidad', 0)
                    cantidad = Decimal(str(raw_cantidad))
                except (ValueError, TypeError, InvalidOperation):
                    return Response(
                        {"error": f"La cantidad enviada ({raw_cantidad}) no tiene un formato numérico válido."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if cantidad <= 0:
                    continue

                # 🔀 DESVÍO CRÍTICO: Si es Compra Directa, guardamos en la nueva tabla y saltamos la bodega
                if tipo_movimiento == 'COMPRA_DIRECTA':
                    nombre_temporal = item.get('nombre_temporal', 'Insumo sin nombre')
                    
                    MaterialCompraDirecta.objects.create(
                        proyecto=proyecto,
                        nombre_material=nombre_temporal,
                        cantidad=int(cantidad),  # Lo guardamos como entero según tu modelo
                        proveedor=request.data.get('proveedor', ''),
                        usuario_bodega=request.user,
                        notas=request.data.get('notas_novedad', '')
                    )
                    continue # 🔥 Termina este ítem y salta al siguiente del bucle sin tocar la tabla Material

                # --- LÓGICA TRADICIONAL PARA BODEGA (SALIDAS, ENTRADAS, DEVOLUCIONES) ---
                try:
                    material = Material.objects.select_for_update().get(id=material_id)
                except Material.DoesNotExist:
                    return Response({"error": f"El material con ID {material_id} no existe."}, status=status.HTTP_404_NOT_FOUND)

                # VALIDACIÓN DE SEGURIDAD: Frena el movimiento ANTES de guardarlo si no hay existencias suficientes
                if tipo_movimiento == 'SALIDA_PROYECTO':
                    if material.stock_bodega < cantidad:
                        transaction.set_rollback(True)
                        return Response(
                            {"error": f"Stock insuficiente en bodega para {material.nombre}. Disponible: {material.stock_bodega}"},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                # 💡 NOTA: Removimos las líneas que sumaban/restaban stock manualmente aquí (ej. material.stock_bodega += cantidad)
                # para que el trigger/signal activo en tu modelo 'MovimientoMaterial' realice el ajuste una única vez.

                # Registro histórico tradicional para lo que SÍ pasa por bodega (Dispara tu señal interna de stock)
                MovimientoMaterial.objects.create(
                    material=material,
                    cantidad=int(cantidad),  # Asegurado como entero y usando tu campo 'cantidad'
                    tipo=tipo_movimiento,
                    proyecto=proyecto,
                    usuario_bodega=request.user,
                )

            return Response({"mensaje": "Movimientos de inventario procesados correctamente."}, status=status.HTTP_201_CREATED)

        except Exception as e:
            # Esto imprimirá el error real en tu consola para monitoreo técnico
            print(f"❌ ERROR CRÍTICO EN InventarioMaterialesView: {str(e)}")
            return Response(
                {"error": f"Error interno del servidor al procesar el inventario. Detalle: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MaterialesPorProyectoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, proyecto_id):
        try:
            # 1. Verificamos que el proyecto exista
            try:
                proyecto = Proyecto.objects.get(id=proyecto_id)
            except Proyecto.DoesNotExist:
                return Response({"error": "El proyecto especificado no existe."}, status=status.HTTP_404_NOT_FOUND)

            # 2. Buscamos movimientos de bodega tradicionales de este proyecto (excluyendo compras directas antiguas y entradas)
            movimientos_bodega = MovimientoMaterial.objects.filter(
                proyecto=proyecto
            ).exclude(tipo__in=['ENTRADA_BODEGA', 'COMPRA_DIRECTA']).select_related('material')

            # 3. 🆕 CONSULTA EN EL NUEVO ARCHIVADOR: Traemos las compras directas reales de la nueva tabla
            compras_directas_reales = MaterialCompraDirecta.objects.filter(proyecto=proyecto)

            # 4. Estructuras separadas para auditar cada origen de forma independiente
            resumen_bodega = {}
            resumen_compra_directa = []  # Cambiado a lista para acumular texto libre limpiamente

            # --- PROCESAR CASO A: MATERIAL DE BODEGA TRADICIONAL ---
            for mov in movimientos_bodega:
                mat = mov.material
                
                if mat.id not in resumen_bodega:
                    resumen_bodega[mat.id] = {
                        "id": mat.id,
                        "nombre": mat.nombre,
                        "cantidad_en_obra": 0,
                        "text_unidad": mat.unidad_medida,
                        "unidad_medida": mat.unidad_medida
                    }
                
                if mov.tipo == 'SALIDA_PROYECTO':
                    resumen_bodega[mat.id]["cantidad_en_obra"] += mov.cantidad
                elif mov.tipo == 'DEVOLUCION_PROYECTO':
                    resumen_bodega[mat.id]["cantidad_en_obra"] -= mov.cantidad

            # --- 🆕 PROCESAR CASO B: MAPEAR LAS COMPRAS DIRECTAS DESDE LA NUEVA TABLA ---
            for cd in compras_directas_reales:
                resumen_compra_directa.append({
                    "id": cd.id,  # ID de su propia tabla para que el frontend maneje llaves únicas
                    "nombre": cd.nombre_material,  # El texto libre escrito a mano en la calle
                    "cantidad_en_obra": cd.cantidad,
                    "text_unidad": "UND",  # Unidad por defecto asignada para materiales libres
                    "unidad_medida": "UND",
                    "proveedor": cd.proveedor or "No especificado",
                    "fecha": cd.fecha_hora.strftime('%d/%m/%Y')
                })

            # 5. Filtramos saldos positivos de bodega para no enviar registros en cero
            lista_bodega = [info for info in resumen_bodega.values() if info["cantidad_en_obra"] > 0]

            # 6. Retornamos la respuesta con la estructura exacta que tu App Móvil ya consume
            return Response({
                "proyecto": proyecto.nombre,
                "salido_bodega": lista_bodega,
                "compra_directa": resumen_compra_directa  # Envía el listado real de la calle
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error al obtener materiales del proyecto: {str(e)}")
            return Response(
                {"error": "Error interno al procesar el inventario del proyecto."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ListarProyectosView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        proyectos = Proyecto.objects.all().order_by('nombre')
        data = [{'id': p.id, 'nombre': p.nombre} for p in proyectos]
        return Response(data)


class ProyectosPorMaterialView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, material_id):
        try:
            try:
                material = Material.objects.get(id=material_id)
            except Material.DoesNotExist:
                return Response({"error": "El material especificado no existe."}, status=status.HTTP_404_NOT_FOUND)

            movimientos = MovimientoMaterial.objects.filter(
                material=material, 
                proyecto__isnull=False
            ).select_related('proyecto')

            distribucion_proyectos = {}

            for mov in movimientos:
                proy = mov.proyecto
                if not proy:
                    continue

                if proy.id not in distribucion_proyectos:
                    distribucion_proyectos[proy.id] = {
                        "id": proy.id,
                        "proyecto_nombre": proy.nombre,
                        "cantidad_en_obra": 0
                    }

                if mov.tipo in ['SALIDA_PROYECTO', 'COMPRA_DIRECTA']:
                    distribucion_proyectos[proy.id]["cantidad_en_obra"] += mov.cantidad
                elif mov.tipo == 'DEVOLUCION_PROYECTO':
                    distribucion_proyectos[proy.id]["cantidad_en_obra"] -= mov.cantidad

            data_final = [
                info for info in distribucion_proyectos.values() if info["cantidad_en_obra"] > 0
            ]

            return Response({
                "material": material.nombre,
                "unidad_medida": material.unidad_medida,
                "distribucion": data_final
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error al obtener distribución del material: {str(e)}")
            return Response(
                {"error": "Error interno al procesar la distribución del material."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

class CrearMaterialCatalogoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            nombre_input = request.data.get('nombre', '').strip()
            unidad_input = request.data.get('unidad_medida', '').strip().lower()

            if not nombre_input or not unidad_input:
                return Response(
                    {"error": "El nombre y la unidad de medida son campos obligatorios."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            existe_material = Material.objects.filter(nombre__iexact=nombre_input).exists()
            
            if existe_material:
                return Response(
                    {"error": f"El material '{nombre_input}' ya existe en el catálogo. Búscalo directamente en la pantalla de movimientos."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            nuevo_material = Material.objects.create(
                nombre=nombre_input,
                unidad_medida=unidad_input,
                stock_bodega=0
            )

            return Response({
                "mensaje": f"¡Material '{nuevo_material.nombre}' registrado con éxito en el catálogo!",
                "id": nuevo_material.id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"Error al crear material en catálogo: {str(e)}")
            return Response(
                {"error": "Error interno del servidor al intentar registrar el material."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

class CrearProyectoRapidoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            nombre_input = request.data.get('nombre', '').strip()

            if not nombre_input:
                return Response(
                    {"error": "El nombre del proyecto es obligatorio."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            if Proyecto.objects.filter(nombre__iexact=nombre_input).exists():
                return Response(
                    {"error": f"El proyecto '{nombre_input}' ya está registrado."}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            nuevo_proyecto = Proyecto.objects.create(nombre=nombre_input)

            return Response({
                "mensaje": f"¡Proyecto '{nuevo_proyecto.nombre}' creado con éxito!",
                "id": nuevo_proyecto.id
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"Error al crear proyecto: {str(e)}")
            return Response(
                {"error": "Error interno al registrar el proyecto."}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
# CHECKLIST PARA MONITOREAR PROYECTOS.

class DetalleChecklistProyectoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, proyecto_id):
        try:
            try:
                proyecto = Proyecto.objects.get(id=proyecto_id)
            except Proyecto.DoesNotExist:
                return Response({"error": "El proyecto especificado no existe."}, status=status.HTTP_404_NOT_FOUND)

            etapas = proyecto.etapas.all().order_by('id')
            
            etapas_data = []
            for etapa in etapas:
                # 🔍 Buscamos el último reporte físico guardado para esta etapa exacta
                ultimo_reporte = ReporteAvanceDiario.objects.filter(etapa=etapa).order_by('-fecha_reporte').first()
                
                foto_url = None
                # Si existe el reporte y el usuario adjuntó una foto, construimos su URL absoluta para el celular
                if ultimo_reporte and ultimo_reporte.foto_evidencia:
                    foto_url = request.build_absolute_uri(ultimo_reporte.foto_evidencia.url)

                etapas_data.append({
                    "id": etapa.id,
                    "nombre_etapa": etapa.nombre_etapa,
                    "porcentaje_avance": etapa.porcentaje_avance,
                    "estado_color": etapa.get_estado_color(), # Mantiene el control de colores original (Rojo, Naranja, Verde)
                    # 📸 Inyectamos de forma segura las notas y la imagen al diccionario
                    "notas_progreso": ultimo_reporte.nota_labor if ultimo_reporte else "",
                    "foto_evidencia_url": foto_url
                })

            return Response({
                "proyecto_id": proyecto.id,
                "proyecto_nombre": proyecto.nombre,
                "descripcion": proyecto.descripcion or "",
                "activo": proyecto.activo,
                "checklist": etapas_data # Tarjetas con sus metadatos de visualización integrados
            }, status=status.HTTP_200_OK)

        except Exception as e:
            print(f"Error al obtener el checklist: {str(e)}")
            return Response({"error": "Error interno al procesar el checklist."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


    def post(self, request, proyecto_id):
        """ Registra el avance diario, guarda la labor e indexa fotos/videos """
        try:
            etapa_id = request.data.get('etapa_id')
            nuevo_porcentaje = request.data.get('porcentaje_avance')
            nuevas_notas = request.data.get('notas_progreso', '').strip()
            
            # Captura de archivos multimedia enviados desde el celular
            archivo_foto = request.FILES.get('foto', None)
            archivo_video = request.FILES.get('video', None)

            if etapa_id is None or nuevo_porcentaje is None:
                return Response({"error": "Los campos 'etapa_id' y 'porcentaje_avance' son obligatorios."}, status=status.HTTP_400_BAD_REQUEST)

            # [EXCEPT 1] Validar si existe la etapa
            try:
                etapa = EtapaProyecto.objects.get(id=etapa_id, proyecto_id=proyecto_id)
            except EtapaProyecto.DoesNotExist:
                return Response({"error": "La etapa especificada no existe en este proyecto."}, status=status.HTTP_404_NOT_FOUND)

            # [EXCEPT 2 y 3] Validar que el porcentaje sea un número correcto
            try:
                progreso = int(nuevo_porcentaje)
                if progreso < 0 or progreso > 100:
                    return Response({"error": "El porcentaje debe estar entre 0 a 100."}, status=status.HTTP_400_BAD_REQUEST)
            except ValueError:
                return Response({"error": "El porcentaje debe ser un número entero válido."}, status=status.HTTP_400_BAD_REQUEST)

            # 1. Actualizamos el estado de la tarjeta principal
            etapa.porcentaje_avance = progreso
            etapa.save()

            # 🛡️ SEGURIDAD: Validamos si el usuario viene en la petición, si no, lo dejamos null para que no rompa
            user_registra = request.user if request.user.is_authenticated else None

            # 2. Creamos el reporte diario independiente con su evidencia
            ReporteAvanceDiario.objects.create(
                etapa=etapa,
                usuario=user_registra,
                porcentaje_al_momento=progreso,
                nota_labor=nuevas_notas if nuevas_notas else "Avance actualizado sin comentarios adicionales.",
                foto_evidencia=archivo_foto,
                video_evidencia=archivo_video
            )

            # Determinamos el nuevo estado de color para responderle al frontend
            color_final = "ROJO"
            if progreso >= 100:
                color_final = "VERDE"
            elif progreso > 0:
                color_final = "NARANJA"

            return Response({
                "mensaje": "¡Éxito! El reporte de labor diaria y el avance fueron registrados.",
                "nuevo_porcentaje": progreso,
                "nuevo_estado_color": color_final
            }, status=status.HTTP_200_OK)

        # [EXCEPT 4 - EL GLOBAL] ¡Aquí es donde atrapamos el error 500 real!
        except Exception as e:
            import traceback
            print("❌ ERROR REAL EN EL BACKEND AL GUARDAR FOTO:")
            print(traceback.format_exc()) # Esto te pintará en la consola la línea exacta que falló
            return Response({"error": f"Error interno en el servidor: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)