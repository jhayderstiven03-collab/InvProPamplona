import uuid
from django.db import models


class Categoria(models.Model):
    id          = models.UUIDField(primary_key=True,
                    default=uuid.uuid4, editable=False)
    nombre      = models.CharField(max_length=100, unique=True)
    prefix      = models.CharField(max_length=5, unique=True, blank=True)
    descripcion = models.TextField(blank=True, default='')
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.prefix:
            import re
            limpio = re.sub(r'[^A-Z]', '', self.nombre.upper())
            self.prefix = limpio[:3] if limpio else 'GEN'
        super().save(*args, **kwargs)

    class Meta:
        verbose_name        = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering            = ['nombre']

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    id              = models.UUIDField(primary_key=True,
                        default=uuid.uuid4, editable=False)
    nombre          = models.CharField(max_length=200)
    sku             = models.CharField(max_length=50,
                        unique=True, db_index=True)
    descripcion     = models.TextField(blank=True, default='')
    categoria       = models.ForeignKey(
                        Categoria,
                        on_delete=models.PROTECT,
                        related_name='productos')
    stock_actual    = models.DecimalField(
                        max_digits=12, decimal_places=2, default=0)
    stock_minimo    = models.DecimalField(
                        max_digits=12, decimal_places=2, default=0)
    precio_unitario = models.DecimalField(
                        max_digits=14, decimal_places=2, default=0)
    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Producto'
        verbose_name_plural = 'Productos'
        ordering            = ['nombre']
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['categoria', 'is_active']),
        ]

    def __str__(self):
        return f'{self.sku} — {self.nombre}'

    @property
    def tiene_alerta(self):
        return self.stock_actual <= self.stock_minimo