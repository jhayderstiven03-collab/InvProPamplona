import uuid
from django.db import models
from django.conf import settings

class HistorialOperacion(models.Model):
    TIPOS = [
        ('crear_producto', 'Creó producto'),
        ('editar_producto', 'Editó producto'),
        ('eliminar_producto', 'Eliminó producto'),
        ('crear_categoria', 'Creó categoría'),
        ('editar_categoria', 'Editó categoría'),
        ('eliminar_categoria', 'Eliminó categoría'),
        ('registrar_movimiento', 'Registró movimiento'),
        ('registro_usuario', 'Registró usuario'),
        ('activar_2fa', 'Activó 2FA'),
        ('desactivar_2fa', 'Desactivó 2FA'),
    ]

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    autor      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='historial')
    tipo       = models.CharField(max_length=30, choices=TIPOS)
    detalle    = models.TextField(blank=True, default='')
    metadata   = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Historial de Operación'
        verbose_name_plural = 'Historial de Operaciones'
        ordering            = ['-created_at']

    def __str__(self):
        return f"{self.autor} - {self.get_tipo_display()} - {self.created_at.strftime('%d/%m/%Y %H:%M')}"
