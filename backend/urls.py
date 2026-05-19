from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework.routers import DefaultRouter
from usuarios.views import (
    LocalViewSet, CanchaViewSet, ReservaViewSet, ResenaViewSet,
    registro_view, login_view, me_view, refresh_token_view,
    dueno_estadisticas_view, admin_estadisticas_view,
    disponibilidad_cancha_view,
    notificaciones_view, marcar_notificaciones_leidas_view,
)

router = DefaultRouter()
router.register('locales', LocalViewSet, basename='locales')
router.register('canchas', CanchaViewSet, basename='canchas')
router.register('reservas', ReservaViewSet)
router.register('resenas', ResenaViewSet, basename='resenas')

urlpatterns = [
    path('admin/', admin.site.urls),

    # Autenticación
    path('api/registro/', registro_view),
    path('api/login/', login_view),
    path('api/me/', me_view),
    path('api/token/refresh/', refresh_token_view),

    # Disponibilidad individual de cancha
    path('api/disponibilidad/<int:cancha_id>/', disponibilidad_cancha_view),

    # Notificaciones
    path('api/notificaciones/<int:usuario_id>/', notificaciones_view),
    path('api/notificaciones/<int:usuario_id>/leer/', marcar_notificaciones_leidas_view),

    # Estadísticas
    path('api/estadisticas/dueno/<int:dueno_id>/', dueno_estadisticas_view),
    path('api/estadisticas/admin/', admin_estadisticas_view),

    # REST API (includes /api/locales/, /api/canchas/, /api/reservas/, /api/resenas/)
    # Local availability: /api/locales/<id>/disponibilidad/
    path('api/', include(router.urls)),
]

# Servir archivos de media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)