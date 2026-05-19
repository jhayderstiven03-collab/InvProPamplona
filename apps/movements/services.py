from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.inventory.models import Producto
from apps.movements.models import Movimiento


def registrar_movimiento(tipo, producto_id, cantidad, usuario, nota=''):
    """
    Registra un movimiento de inventario y actualiza el stock.
    Lanza ValidationError si la operacion no es valida.

    El select_for_update() se ejecuta dentro del bloque atomic para
    garantizar que el lock de fila y la escritura ocurran en la misma
    transaccion, evitando condiciones de carrera en concurrencia alta.
    """
    if cantidad <= 0:
        raise ValidationError('La cantidad debe ser mayor a cero.')

    cantidad = Decimal(str(cantidad))

    with transaction.atomic():
        try:
            producto = Producto.objects.select_for_update().get(
                id=producto_id, is_active=True
            )
        except Producto.DoesNotExist:
            raise ValidationError('Producto no encontrado o inactivo.')

        if tipo == Movimiento.ENTRADA:
            producto.stock_actual += cantidad

        elif tipo == Movimiento.SALIDA:
            if producto.stock_actual < cantidad:
                raise ValidationError(
                    f'Stock insuficiente — Disponible: {producto.stock_actual}, Solicitado: {cantidad}'
                )
            producto.stock_actual -= cantidad

        elif tipo == Movimiento.AJUSTE:
            producto.stock_actual = cantidad

        else:
            raise ValidationError(f'Tipo de movimiento invalido: {tipo}')

        producto.save(update_fields=['stock_actual', 'updated_at'])

        movimiento = Movimiento.objects.create(
            tipo=tipo,
            producto=producto,
            cantidad=cantidad,
            nota=nota,
            usuario=usuario,
        )

    return movimiento


def obtener_resumen_movimientos(dias=7):
    """
    Retorna entradas y salidas de los ultimos N dias.
    Usado por el endpoint del dashboard.
    """
    from django.utils import timezone
    from django.db.models import Sum
    from datetime import timedelta

    hoy = timezone.localdate()
    desde = hoy - timedelta(days=dias - 1)

    resultado = []
    for i in range(dias):
        fecha = desde + timedelta(days=i)
        movs = Movimiento.objects.filter(created_at__date=fecha)

        entradas = movs.filter(
            tipo=Movimiento.ENTRADA
        ).aggregate(total=Sum('cantidad'))['total'] or 0

        salidas = movs.filter(
            tipo=Movimiento.SALIDA
        ).aggregate(total=Sum('cantidad'))['total'] or 0

        resultado.append({
            'fecha': fecha.strftime('%d/%m'),
            'entradas': float(entradas),
            'salidas': float(salidas),
        })

    return resultado