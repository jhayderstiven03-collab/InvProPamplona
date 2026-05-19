import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ADMIN     = 'admin'
    OPERADOR  = 'operador'
    CONSULTOR = 'consultor'

    ROL_CHOICES = [
        (ADMIN,     'Administrador'),
        (OPERADOR,  'Operador'),
        (CONSULTOR, 'Consultor'),
    ]

    id  = models.UUIDField(primary_key=True,
            default=uuid.uuid4, editable=False)
    rol = models.CharField(max_length=10,
            choices=ROL_CHOICES, default=OPERADOR)
    nombre_completo = models.CharField(max_length=200, blank=True)
    correo          = models.EmailField(blank=True)
    telefono        = models.CharField(max_length=20, blank=True)
    direccion       = models.TextField(blank=True)

    def es_admin(self):
        return self.rol == self.ADMIN

    def es_operador(self):
        return self.rol == self.OPERADOR

    def es_consultor(self):
        return self.rol == self.CONSULTOR

    class Meta:
        verbose_name        = 'Usuario'
        verbose_name_plural = 'Usuarios'