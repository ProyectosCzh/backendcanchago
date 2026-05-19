from datetime import date, timedelta
from django.db.models import Count, Q, Avg
from django.db.models.functions import TruncDate, TruncMonth
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import api_view, permission_classes, parser_classes, action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from .models import Usuario, Local, Cancha, Reserva, Resena, Notificacion
from .serializers import (
    UsuarioSerializer, RegistroSerializer, LoginSerializer, PerfilSerializer,
    LocalSerializer, LocalDetalleSerializer,
    CanchaSerializer, ReservaSerializer, ResenaSerializer,
    NotificacionSerializer
)
from .authentication import generar_tokens


# =============================================
#  AUTENTICACIÓN
# =============================================

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def registro_view(request):
    serializer = RegistroSerializer(data=request.data)
    if serializer.is_valid():
        usuario = serializer.save()
        tokens = generar_tokens(usuario)
        return Response({
            'usuario': UsuarioSerializer(usuario).data,
            'tokens': tokens,
        }, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        usuario = serializer.validated_data['usuario']
        tokens = generar_tokens(usuario)
        return Response({
            'usuario': UsuarioSerializer(usuario).data,
            'tokens': tokens,
        })
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PATCH'])
def me_view(request):
    if not hasattr(request, 'usuario'):
        return Response({'error': 'No autenticado'}, status=401)

    if request.method == 'PATCH':
        serializer = PerfilSerializer(
            request.usuario, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(UsuarioSerializer(request.usuario).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    return Response(UsuarioSerializer(request.usuario).data)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def refresh_token_view(request):
    from .authentication import refrescar_access_token
    refresh = request.data.get('refresh')
    if not refresh:
        return Response({'error': 'Refresh token requerido'}, status=400)
    try:
        new_access = refrescar_access_token(refresh)
        return Response({'access': new_access})
    except Exception as e:
        return Response({'error': str(e)}, status=401)


# =============================================
#  LOCALES (Complejos Deportivos)
# =============================================

class LocalViewSet(viewsets.ModelViewSet):
    serializer_class = LocalSerializer
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LocalDetalleSerializer
        return LocalSerializer

    def get_serializer_context(self):
        return {'request': self.request}

    def get_queryset(self):
        queryset = Local.objects.all().order_by('-created_at')

        # Filtro por dueño
        dueno = self.request.query_params.get('dueno')
        if dueno:
            queryset = queryset.filter(dueno_id=dueno)

        # Búsqueda por nombre o dirección
        buscar = self.request.query_params.get('buscar')
        if buscar:
            queryset = queryset.filter(
                Q(nombre__icontains=buscar) | Q(direccion__icontains=buscar)
            )

        # Filtro por tipo de cancha dentro del local
        tipo = self.request.query_params.get('tipo')
        if tipo:
            queryset = queryset.filter(canchas__tipo=tipo).distinct()

        # Filtro por rango de precio (precio mínimo de las canchas del local)
        precio_min = self.request.query_params.get('precio_min')
        precio_max = self.request.query_params.get('precio_max')
        if precio_min:
            queryset = queryset.filter(canchas__precio_por_hora__gte=precio_min).distinct()
        if precio_max:
            queryset = queryset.filter(canchas__precio_por_hora__lte=precio_max).distinct()

        # Filtro geográfico (bounding box)
        lat_min = self.request.query_params.get('lat_min')
        lat_max = self.request.query_params.get('lat_max')
        lng_min = self.request.query_params.get('lng_min')
        lng_max = self.request.query_params.get('lng_max')
        if all([lat_min, lat_max, lng_min, lng_max]):
            queryset = queryset.filter(
                latitud__gte=lat_min, latitud__lte=lat_max,
                longitud__gte=lng_min, longitud__lte=lng_max,
            )

        return queryset

    @action(detail=True, methods=['get'])
    def disponibilidad(self, request, pk=None):
        """Disponibilidad unificada de TODAS las canchas del local para una fecha."""
        local = self.get_object()
        fecha_str = request.query_params.get('fecha')

        if fecha_str:
            try:
                from datetime import datetime
                fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            except ValueError:
                return Response({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}, status=400)
        else:
            fecha = date.today()

        canchas = local.canchas.all().order_by('nombre')
        resultado = []

        for cancha in canchas:
            reservas = Reserva.objects.filter(
                cancha=cancha,
                fecha=fecha,
                estado__in=['pendiente', 'confirmada']
            ).order_by('hora_inicio')

            slots_ocupados = [
                {
                    'hora_inicio': str(r.hora_inicio)[:5],
                    'hora_fin': str(r.hora_fin)[:5],
                    'estado': r.estado,
                }
                for r in reservas
            ]

            resultado.append({
                'cancha_id': cancha.id,
                'cancha_nombre': cancha.nombre,
                'tipo': cancha.tipo,
                'precio_por_hora': str(cancha.precio_por_hora),
                'slots_ocupados': slots_ocupados,
            })

        return Response({
            'local_id': local.id,
            'local_nombre': local.nombre,
            'fecha': str(fecha),
            'hora_apertura': str(local.hora_apertura)[:5],
            'hora_cierre': str(local.hora_cierre)[:5],
            'canchas': resultado,
        })


# =============================================
#  CANCHAS
# =============================================

class CanchaViewSet(viewsets.ModelViewSet):
    serializer_class = CanchaSerializer
    permission_classes = [permissions.AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_context(self):
        return {'request': self.request}

    def get_queryset(self):
        queryset = Cancha.objects.all().select_related('local', 'local__dueno').order_by('-created_at')

        # Filtro por local
        local = self.request.query_params.get('local')
        if local:
            queryset = queryset.filter(local_id=local)

        # Filtro por dueño (a través del local)
        dueno = self.request.query_params.get('dueno')
        if dueno:
            queryset = queryset.filter(local__dueno_id=dueno)

        # Búsqueda por nombre o dirección del local
        buscar = self.request.query_params.get('buscar')
        if buscar:
            queryset = queryset.filter(
                Q(nombre__icontains=buscar) | Q(local__direccion__icontains=buscar)
            )

        # Filtro por tipo de cancha
        tipo = self.request.query_params.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)

        # Filtro por rango de precio
        precio_min = self.request.query_params.get('precio_min')
        precio_max = self.request.query_params.get('precio_max')
        if precio_min:
            queryset = queryset.filter(precio_por_hora__gte=precio_min)
        if precio_max:
            queryset = queryset.filter(precio_por_hora__lte=precio_max)

        # Ordenar
        ordenar = self.request.query_params.get('ordenar')
        if ordenar == 'precio_asc':
            queryset = queryset.order_by('precio_por_hora')
        elif ordenar == 'precio_desc':
            queryset = queryset.order_by('-precio_por_hora')
        elif ordenar == 'calificacion':
            queryset = queryset.annotate(
                avg_cal=Avg('resenas__calificacion')
            ).order_by('-avg_cal')
        elif ordenar == 'popular':
            queryset = queryset.annotate(
                total_res=Count('reservas')
            ).order_by('-total_res')

        return queryset


class ReservaViewSet(viewsets.ModelViewSet):
    queryset = Reserva.objects.all()
    serializer_class = ReservaSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = Reserva.objects.all().select_related(
            'cancha', 'cancha__local', 'cancha__local__dueno', 'cliente'
        ).order_by('-created_at')

        cliente = self.request.query_params.get('cliente')
        cancha = self.request.query_params.get('cancha')
        dueno = self.request.query_params.get('dueno')
        local = self.request.query_params.get('local')

        if cliente:
            queryset = queryset.filter(cliente_id=cliente)
        if cancha:
            queryset = queryset.filter(cancha_id=cancha)
        if dueno:
            queryset = queryset.filter(cancha__local__dueno_id=dueno)
        if local:
            queryset = queryset.filter(cancha__local_id=local)

        return queryset

    def perform_create(self, serializer):
        """Al crear una reserva, notificar al dueño."""
        reserva = serializer.save()
        Notificacion.objects.create(
            usuario=reserva.cancha.local.dueno,
            titulo='Nueva reserva',
            mensaje=f'{reserva.cliente.nombre} reservó {reserva.cancha.nombre} '
                    f'({reserva.cancha.local.nombre}) '
                    f'para el {reserva.fecha} de {reserva.hora_inicio} a {reserva.hora_fin}.',
            tipo='reserva_nueva'
        )

    def perform_update(self, serializer):
        """Al cambiar estado, notificar al cliente."""
        reserva = serializer.save()
        if 'estado' in serializer.validated_data:
            estado = serializer.validated_data['estado']
            if estado == 'confirmada':
                Notificacion.objects.create(
                    usuario=reserva.cliente,
                    titulo='Reserva confirmada ✅',
                    mensaje=f'Tu reserva en {reserva.cancha.nombre} '
                            f'({reserva.cancha.local.nombre}) para el {reserva.fecha} '
                            f'ha sido confirmada.',
                    tipo='reserva_confirmada'
                )
            elif estado == 'cancelada':
                Notificacion.objects.create(
                    usuario=reserva.cliente,
                    titulo='Reserva cancelada ❌',
                    mensaje=f'Tu reserva en {reserva.cancha.nombre} '
                            f'({reserva.cancha.local.nombre}) para el {reserva.fecha} '
                            f'ha sido cancelada.',
                    tipo='reserva_cancelada'
                )


# =============================================
#  DISPONIBILIDAD DE CANCHA (individual)
# =============================================

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def disponibilidad_cancha_view(request, cancha_id):
    """Devuelve los slots ocupados de una cancha para una fecha dada o la semana."""
    fecha_str = request.query_params.get('fecha')

    if fecha_str:
        # Slots para un día específico
        try:
            from datetime import datetime
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Formato de fecha inválido. Use YYYY-MM-DD'}, status=400)

        reservas = Reserva.objects.filter(
            cancha_id=cancha_id,
            fecha=fecha,
            estado__in=['pendiente', 'confirmada']
        ).order_by('hora_inicio')

        slots_ocupados = [
            {
                'hora_inicio': str(r.hora_inicio)[:5],
                'hora_fin': str(r.hora_fin)[:5],
                'estado': r.estado,
            }
            for r in reservas
        ]

        return Response({
            'cancha_id': cancha_id,
            'fecha': str(fecha),
            'slots_ocupados': slots_ocupados,
        })
    else:
        # Slots para los próximos 7 días
        hoy = date.today()
        resultado = []

        for i in range(7):
            dia = hoy + timedelta(days=i)
            reservas = Reserva.objects.filter(
                cancha_id=cancha_id,
                fecha=dia,
                estado__in=['pendiente', 'confirmada']
            ).order_by('hora_inicio')

            slots = [
                {
                    'hora_inicio': str(r.hora_inicio)[:5],
                    'hora_fin': str(r.hora_fin)[:5],
                    'estado': r.estado,
                }
                for r in reservas
            ]

            resultado.append({
                'fecha': str(dia),
                'dia_semana': ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'][dia.weekday()],
                'slots_ocupados': slots,
            })

        return Response({
            'cancha_id': cancha_id,
            'disponibilidad': resultado,
        })


# =============================================
#  RESEÑAS
# =============================================

class ResenaViewSet(viewsets.ModelViewSet):
    serializer_class = ResenaSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = Resena.objects.all().order_by('-created_at')
        cancha = self.request.query_params.get('cancha')
        if cancha:
            queryset = queryset.filter(cancha_id=cancha)
        return queryset

    def perform_create(self, serializer):
        """Al crear una reseña, notificar al dueño."""
        resena = serializer.save()
        Notificacion.objects.create(
            usuario=resena.cancha.local.dueno,
            titulo='Nueva reseña ⭐',
            mensaje=f'{resena.cliente.nombre} dejó una reseña de '
                    f'{resena.calificacion}⭐ en {resena.cancha.nombre} '
                    f'({resena.cancha.local.nombre}).',
            tipo='resena_nueva'
        )


# =============================================
#  NOTIFICACIONES
# =============================================

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def notificaciones_view(request, usuario_id):
    """Lista de notificaciones de un usuario."""
    notificaciones = Notificacion.objects.filter(usuario_id=usuario_id)[:30]
    no_leidas = Notificacion.objects.filter(usuario_id=usuario_id, leida=False).count()
    return Response({
        'notificaciones': NotificacionSerializer(notificaciones, many=True).data,
        'no_leidas': no_leidas,
    })


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def marcar_notificaciones_leidas_view(request, usuario_id):
    """Marcar todas las notificaciones como leídas."""
    Notificacion.objects.filter(usuario_id=usuario_id, leida=False).update(leida=True)
    return Response({'ok': True})


# =============================================
#  HELPERS
# =============================================

def _calcular_ingresos(queryset):
    total = 0
    for r in queryset.select_related('cancha'):
        horas = (
            r.hora_fin.hour + r.hora_fin.minute / 60
            - r.hora_inicio.hour - r.hora_inicio.minute / 60
        )
        total += float(r.cancha.precio_por_hora) * max(horas, 0)
    return round(total, 2)


# =============================================
#  ESTADÍSTICAS DUEÑO
# =============================================

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def dueno_estadisticas_view(request, dueno_id):
    hoy = date.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)
    inicio_ano = hoy.replace(month=1, day=1)

    reservas = Reserva.objects.filter(cancha__local__dueno_id=dueno_id)
    canchas = Cancha.objects.filter(local__dueno_id=dueno_id)
    locales = Local.objects.filter(dueno_id=dueno_id)
    reservas_activas = reservas.filter(estado__in=['confirmada', 'pendiente'])

    por_estado = dict(
        reservas.values_list('estado')
        .annotate(total=Count('id'))
        .values_list('estado', 'total')
    )

    hace_30 = hoy - timedelta(days=30)
    reservas_por_dia = (
        reservas.filter(fecha__gte=hace_30)
        .values('fecha')
        .annotate(total=Count('id'))
        .order_by('fecha')
    )

    cancha_popular = (
        canchas.annotate(total_reservas=Count('reservas'))
        .order_by('-total_reservas')
        .first()
    )

    return Response({
        'reservas': {
            'hoy': reservas.filter(fecha=hoy).count(),
            'semana': reservas.filter(fecha__gte=inicio_semana).count(),
            'mes': reservas.filter(fecha__gte=inicio_mes).count(),
            'ano': reservas.filter(fecha__gte=inicio_ano).count(),
        },
        'ingresos': {
            'hoy': _calcular_ingresos(reservas_activas.filter(fecha=hoy)),
            'semana': _calcular_ingresos(reservas_activas.filter(fecha__gte=inicio_semana)),
            'mes': _calcular_ingresos(reservas_activas.filter(fecha__gte=inicio_mes)),
            'ano': _calcular_ingresos(reservas_activas.filter(fecha__gte=inicio_ano)),
        },
        'por_estado': {
            'pendiente': por_estado.get('pendiente', 0),
            'confirmada': por_estado.get('confirmada', 0),
            'cancelada': por_estado.get('cancelada', 0),
        },
        'reservas_por_dia': [
            {'fecha': str(r['fecha']), 'total': r['total']}
            for r in reservas_por_dia
        ],
        'cancha_popular': {
            'nombre': cancha_popular.nombre if cancha_popular else None,
            'total_reservas': cancha_popular.total_reservas if cancha_popular else 0,
        },
        'total_canchas': canchas.count(),
        'total_locales': locales.count(),
    })


# =============================================
#  ESTADÍSTICAS ADMIN
# =============================================

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def admin_estadisticas_view(request):
    hoy = date.today()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)
    inicio_ano = hoy.replace(month=1, day=1)

    por_estado = dict(
        Reserva.objects.values_list('estado')
        .annotate(total=Count('id'))
        .values_list('estado', 'total')
    )

    hace_12_meses = hoy - timedelta(days=365)
    crecimiento_usuarios = (
        Usuario.objects.filter(created_at__date__gte=hace_12_meses)
        .annotate(mes=TruncMonth('created_at'))
        .values('mes')
        .annotate(total=Count('id'))
        .order_by('mes')
    )

    hace_30 = hoy - timedelta(days=30)
    reservas_por_dia = (
        Reserva.objects.filter(created_at__date__gte=hace_30)
        .values(dia=TruncDate('created_at'))
        .annotate(total=Count('id'))
        .order_by('dia')
    )

    top_canchas = (
        Cancha.objects.select_related('local')
        .annotate(total_reservas=Count('reservas'))
        .order_by('-total_reservas')[:5]
    )

    usuarios_activos = (
        Reserva.objects.filter(created_at__date__gte=hace_30)
        .values('cliente')
        .distinct()
        .count()
    )

    return Response({
        'totales': {
            'usuarios': Usuario.objects.filter(rol='cliente').count(),
            'duenos': Usuario.objects.filter(rol='dueno').count(),
            'canchas': Cancha.objects.count(),
            'locales': Local.objects.count(),
            'reservas': Reserva.objects.count(),
        },
        'nuevos_usuarios': {
            'hoy': Usuario.objects.filter(rol='cliente', created_at__date=hoy).count(),
            'semana': Usuario.objects.filter(rol='cliente', created_at__date__gte=inicio_semana).count(),
            'mes': Usuario.objects.filter(rol='cliente', created_at__date__gte=inicio_mes).count(),
        },
        'nuevos_duenos': {
            'hoy': Usuario.objects.filter(rol='dueno', created_at__date=hoy).count(),
            'semana': Usuario.objects.filter(rol='dueno', created_at__date__gte=inicio_semana).count(),
            'mes': Usuario.objects.filter(rol='dueno', created_at__date__gte=inicio_mes).count(),
        },
        'reservas_periodo': {
            'hoy': Reserva.objects.filter(created_at__date=hoy).count(),
            'semana': Reserva.objects.filter(created_at__date__gte=inicio_semana).count(),
            'mes': Reserva.objects.filter(created_at__date__gte=inicio_mes).count(),
        },
        'ingresos': {
            'mes': _calcular_ingresos(Reserva.objects.filter(estado__in=['confirmada', 'pendiente'], fecha__gte=inicio_mes)),
            'ano': _calcular_ingresos(Reserva.objects.filter(estado__in=['confirmada', 'pendiente'], fecha__gte=inicio_ano)),
        },
        'por_estado': {
            'pendiente': por_estado.get('pendiente', 0),
            'confirmada': por_estado.get('confirmada', 0),
            'cancelada': por_estado.get('cancelada', 0),
        },
        'crecimiento_usuarios': [
            {'mes': c['mes'].strftime('%Y-%m'), 'total': c['total']}
            for c in crecimiento_usuarios
        ],
        'reservas_por_dia': [
            {'fecha': str(r['dia']), 'total': r['total']}
            for r in reservas_por_dia
        ],
        'top_canchas': [
            {'nombre': c.nombre, 'local': c.local.nombre, 'total_reservas': c.total_reservas}
            for c in top_canchas
        ],
        'usuarios_activos': usuarios_activos,
    })