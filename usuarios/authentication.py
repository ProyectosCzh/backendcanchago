"""
Utilidades de autenticación JWT para el modelo Usuario personalizado.
Usa PyJWT directamente para generar y verificar tokens.
"""
import jwt
from datetime import datetime, timedelta, timezone
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import Usuario


SECRET_KEY = settings.SECRET_KEY
ACCESS_TOKEN_LIFETIME = timedelta(hours=24)
REFRESH_TOKEN_LIFETIME = timedelta(days=7)


def generar_tokens(usuario):
    """Genera access y refresh tokens para un usuario."""
    ahora = datetime.now(timezone.utc)

    access_payload = {
        'user_id': usuario.id,
        'correo': usuario.correo,
        'rol': usuario.rol,
        'type': 'access',
        'exp': ahora + ACCESS_TOKEN_LIFETIME,
        'iat': ahora,
    }

    refresh_payload = {
        'user_id': usuario.id,
        'type': 'refresh',
        'exp': ahora + REFRESH_TOKEN_LIFETIME,
        'iat': ahora,
    }

    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm='HS256')
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm='HS256')

    return {
        'access': access_token,
        'refresh': refresh_token,
    }


def verificar_token(token, token_type='access'):
    """Verifica y decodifica un token JWT."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        if payload.get('type') != token_type:
            raise AuthenticationFailed('Tipo de token inválido.')
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed('Token expirado.')
    except jwt.InvalidTokenError:
        raise AuthenticationFailed('Token inválido.')


def refrescar_access_token(refresh_token):
    """Genera un nuevo access token a partir de un refresh token."""
    payload = verificar_token(refresh_token, token_type='refresh')
    try:
        usuario = Usuario.objects.get(id=payload['user_id'])
    except Usuario.DoesNotExist:
        raise AuthenticationFailed('Usuario no encontrado.')

    tokens = generar_tokens(usuario)
    return tokens['access']


class JWTAuthentication(BaseAuthentication):
    """
    Autenticación JWT personalizada para Django REST Framework.
    Busca el token en el header: Authorization: Bearer <token>
    """
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ')[1]

        try:
            payload = verificar_token(token)
            usuario = Usuario.objects.get(id=payload['user_id'])
            # Guardamos el user_id en el request para uso en las vistas
            request.user_id = usuario.id
            request.usuario = usuario
            return (usuario, token)
        except Usuario.DoesNotExist:
            raise AuthenticationFailed('Usuario no encontrado.')
        except AuthenticationFailed:
            raise
