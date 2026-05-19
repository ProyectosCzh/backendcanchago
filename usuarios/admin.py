from django.contrib import admin
from .models import Usuario, Local, Cancha, Reserva, Resena, Notificacion

admin.site.register(Usuario)
admin.site.register(Local)
admin.site.register(Cancha)
admin.site.register(Reserva)
admin.site.register(Resena)
admin.site.register(Notificacion)