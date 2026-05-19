from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from apps.accounts.models import CustomUser
from .decorators import login_required_custom, operador_required, consultor_required, admin_required
from django.db import models

def vista_login(request):
    """
    Autentica al usuario con username y password.

    Flujo con 2FA activo:
      1. Valida credenciales con authenticate().
      2. Si el usuario tiene TOTPDevice confirmado, almacena su PK en sesión
         y redirige a /2fa/verify/ SIN llamar login() todavía.
      3. En /2fa/verify/ se valida el token y solo entonces se llama login().
      Este orden garantiza que la sesión nunca queda abierta antes de
      completar el segundo factor.

    Flujo sin 2FA:
      Llama login() directamente y redirige según el rol.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)

        if user is not None:
            from django_otp.plugins.otp_totp.models import TOTPDevice
            tiene_2fa = TOTPDevice.objects.filter(
                user=user, confirmed=True).exists()

            if tiene_2fa:
                # Guarda el PK en sesión temporal — NO llama login() aún.
                # La sesión queda sin usuario autenticado hasta pasar el 2FA.
                request.session['pre_2fa_user_pk'] = str(user.pk)
                request.session['pre_2fa_backend'] = \
                    'django.contrib.auth.backends.ModelBackend'
                return redirect('2fa_verify')

            # Sin 2FA — autenticación completa directa
            login(request, user)
            return _redirigir_por_rol(user)

        messages.error(request, 'Usuario o contraseña incorrectos')

    return render(request, 'auth/login.html')


def vista_logout(request):
    """
    Cierra la sesión activa y redirige al login.
    """
    logout(request)
    return redirect('login')


def vista_registro(request):
    """
    Crea una nueva cuenta de usuario con rol CONSULTOR (solo lectura).
    Los roles operador y admin solo pueden ser asignados por un administrador.

    Validaciones:
      - username y password1 no pueden estar vacíos.
      - password1 debe coincidir con password2.
      - El username no debe existir previamente en la base de datos.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username  = request.POST.get('username', '').strip()
        password1 = request.POST.get('password1', '').strip()
        password2 = request.POST.get('password2', '').strip()

        if not username or not password1:
            messages.error(request, 'Usuario y contraseña son obligatorios')
            return redirect('registro')

        if password1 != password2:
            messages.error(request, 'Las contraseñas no coinciden')
            return redirect('registro')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, f'El usuario {username} ya existe')
            return redirect('registro')

        # El autoregistro público asigna siempre rol CONSULTOR (solo lectura).
        # Para otorgar rol operador, usar la gestión de usuarios (admin).
        CustomUser.objects.create_user(
            username=username,
            password=password1,
            rol=CustomUser.CONSULTOR,
        )
        messages.success(request,
            'Cuenta creada. Ingresa con tus credenciales.')
        return redirect('login')

    return render(request, 'auth/registro.html')


@operador_required
def vista_dashboard_operador(request):
    """
    Panel principal para usuarios con rol operador.

    Muestra:
      - Inventario activo completo con su categoría.
      - Conteo de productos con stock en cero (alertas críticas).
      - Resumen de movimientos propios del día: entradas, salidas, ajustes.
      - Historial personal de los últimos 20 movimientos registrados.

    Requiere rol operador o superior (decorator: operador_required).
    """
    from apps.inventory.models import Producto
    from apps.movements.models import Movimiento
    from django.utils import timezone

    hoy = timezone.localdate()

    productos = Producto.objects.select_related('categoria').filter(is_active=True)
    alertas   = productos.filter(stock_actual__lte=0).count()

    # Resumen del día — filtra solo los movimientos del usuario en sesión
    movs_hoy     = Movimiento.objects.filter(
        usuario=request.user,
        created_at__date=hoy,
    )
    entradas_hoy = movs_hoy.filter(tipo='entrada').count()
    salidas_hoy  = movs_hoy.filter(tipo='salida').count()
    ajustes_hoy  = movs_hoy.filter(tipo='ajuste').count()

    # Historial propio — últimos 20 movimientos, ordenados por fecha descendente
    mis_movimientos = Movimiento.objects.filter(
        usuario=request.user,
    ).select_related('producto').order_by('-created_at')[:20]

    return render(request, 'dashboard/operador.html', {
        'productos':        productos,
        'productos_alerta': alertas,
        'entradas_hoy':     entradas_hoy,
        'salidas_hoy':      salidas_hoy,
        'ajustes_hoy':      ajustes_hoy,
        'mis_movimientos':  mis_movimientos,
    })


@consultor_required
def vista_dashboard_consultor(request):
    from apps.inventory.models import Producto
    productos = Producto.objects.select_related(
        'categoria').filter(is_active=True)
    alertas = productos.filter(stock_actual__lte=0).count()
    return render(request, 'dashboard/consultor.html', {
        'productos':        productos,
        'productos_alerta': alertas,
    })

@operador_required
def vista_mis_movimientos(request):
    from apps.movements.models import Movimiento
    from django.utils import timezone

    hoy = timezone.localdate()

    entradas_hoy = Movimiento.objects.filter(
        usuario=request.user, created_at__date=hoy, tipo='entrada').count()
    salidas_hoy  = Movimiento.objects.filter(
        usuario=request.user, created_at__date=hoy, tipo='salida').count()
    ajustes_hoy  = Movimiento.objects.filter(
        usuario=request.user, created_at__date=hoy, tipo='ajuste').count()

    mis_movimientos = Movimiento.objects.filter(
        usuario=request.user
    ).select_related('producto').order_by('-created_at')[:50]

    return render(request, 'dashboard/mis_movimientos.html', {
        'entradas_hoy':    entradas_hoy,
        'salidas_hoy':     salidas_hoy,
        'ajustes_hoy':     ajustes_hoy,
        'mis_movimientos': mis_movimientos,
    })


@consultor_required
def vista_reportes_consultor(request):
    from apps.inventory.models import Producto, Categoria
    from apps.movements.models import Movimiento
    from django.db.models import Sum, F

    productos_alerta_list = Producto.objects.filter(
        is_active=True,
        stock_actual__lte=F('stock_minimo')
    ).select_related('categoria').order_by('stock_actual')

    movimientos = Movimiento.objects.select_related(
        'producto', 'usuario').order_by('-created_at')[:50]

    categorias = Categoria.objects.filter(is_active=True)
    stock_cats = []
    for cat in categorias:
        total = Producto.objects.filter(
            categoria=cat, is_active=True
        ).aggregate(total=Sum('stock_actual'))['total'] or 0
        stock_cats.append({'nombre': cat.nombre, 'total': float(total)})

    return render(request, 'dashboard/reportes_consultor.html', {
        'prods_alerta_list': productos_alerta_list,
        'movimientos':       movimientos,
        'stock_cats':        stock_cats,
    })

@login_required_custom
def vista_2fa_setup(request):
    """
    Genera un dispositivo TOTP no confirmado para el usuario autenticado,
    produce el QR de configuración y lo entrega al template como base64 PNG.

    Elimina cualquier dispositivo previo no confirmado antes de crear uno nuevo
    para evitar dispositivos huérfanos en la base de datos.
    """
    from django_otp.plugins.otp_totp.models import TOTPDevice
    import qrcode
    import io
    import base64

    # Elimina dispositivos previos no confirmados del mismo usuario
    TOTPDevice.objects.filter(user=request.user, confirmed=False).delete()

    device, _ = TOTPDevice.objects.get_or_create(
        user=request.user,
        confirmed=False,
        defaults={'name': 'InvPro Unipamplona'},
    )

    # Genera el QR como PNG en memoria y lo codifica en base64
    uri = device.config_url
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    return render(request, 'auth/2fa_setup.html', {
        'qr_b64': qr_b64,
        'secret': device.bin_key.hex(),
        'device': device,
    })


def vista_2fa_verify(request):
    """
    Verifica el token TOTP en dos escenarios:

    A) Confirmación inicial (setup):
       El usuario ya está autenticado (login_required_custom) y confirma
       su nuevo dispositivo por primera vez.

    B) Verificación en login:
       El usuario NO está autenticado aún. Su PK está en
       request.session['pre_2fa_user_pk']. Si el token es válido,
       se llama login() y se limpia la sesión temporal.
    """
    from django_otp.plugins.otp_totp.models import TOTPDevice
    import django_otp

    if request.method == 'POST':
        token = request.POST.get('token', '').strip().replace(' ', '')

        # ── Escenario A: confirmación de setup (usuario ya autenticado) ──────
        if request.user.is_authenticated:
            device = TOTPDevice.objects.filter(
                user=request.user, confirmed=False).first()

            if device:
                if device.verify_token(token):
                    device.confirmed = True
                    device.save()
                    django_otp.login(request, device)
                    messages.success(request,
                        '2FA activado correctamente en tu cuenta')
                    return redirect('dashboard')
                else:
                    messages.error(request,
                        'Código incorrecto. Intenta de nuevo')
                    return redirect('2fa_setup')

            # Usuario autenticado sin device pendiente: verifica login normal
            device = TOTPDevice.objects.filter(
                user=request.user, confirmed=True).first()
            if device and device.verify_token(token):
                django_otp.login(request, device)
                return _redirigir_por_rol(request.user)

            messages.error(request, 'Código incorrecto')
            return render(request, 'auth/2fa_verify.html')

        # ── Escenario B: segundo factor en flujo de login ────────────────────
        user_pk = request.session.get('pre_2fa_user_pk')
        if not user_pk:
            # Sesión temporal expirada o acceso directo a la URL
            messages.error(request,
                'Sesión expirada. Inicia sesión nuevamente.')
            return redirect('login')

        try:
            user = CustomUser.objects.get(pk=user_pk)
        except CustomUser.DoesNotExist:
            messages.error(request, 'Usuario no encontrado')
            return redirect('login')

        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()

        if device and device.verify_token(token):
            # Token válido — ahora sí se establece la sesión completa
            backend = request.session.get(
                'pre_2fa_backend',
                'django.contrib.auth.backends.ModelBackend',
            )
            user.backend = backend
            login(request, user)
            django_otp.login(request, device)
            # Limpia datos temporales de sesión
            request.session.pop('pre_2fa_user_pk', None)
            request.session.pop('pre_2fa_backend', None)
            return _redirigir_por_rol(user)

        messages.error(request, 'Código incorrecto. Intenta de nuevo')

    return render(request, 'auth/2fa_verify.html')


def _redirigir_por_rol(user):
    """
    Helper interno — centraliza la redirección por rol.
    Evita duplicar la misma lógica en vista_login y vista_2fa_verify.
    """
    if user.es_admin():
        return redirect('dashboard')
    elif user.es_operador():
        return redirect('dashboard_operador')
    else:
        return redirect('dashboard_consultor')


ROLES_ASIGNABLES_POR_ADMIN = frozenset({
    CustomUser.OPERADOR,
    CustomUser.CONSULTOR,
})


@admin_required
def vista_gestion_usuarios(request):
    """
    Lista usuarios operador y consultor para que el admin pueda cambiar su rol.
    Los administradores no aparecen ni pueden ser modificados desde aquí.
    """
    usuarios = CustomUser.objects.exclude(
        rol=CustomUser.ADMIN,
    ).filter(is_superuser=False).order_by('username')
    return render(request, 'accounts/usuarios.html', {
        'usuarios': usuarios,
    })


@admin_required
def cambiar_rol_usuario(request, pk):
    """
    Cambia el rol de un usuario entre operador y consultor.
    Solo acepta POST. Rechaza administradores y roles no permitidos.
    """
    if request.method != 'POST':
        return redirect('gestion_usuarios')

    nuevo_rol = request.POST.get('rol', '').strip()
    if nuevo_rol not in ROLES_ASIGNABLES_POR_ADMIN:
        messages.error(request, 'Rol no válido. Solo se permite Operador o Consultor.')
        return redirect('gestion_usuarios')

    try:
        usuario = CustomUser.objects.get(pk=pk)
    except CustomUser.DoesNotExist:
        messages.error(request, 'Usuario no encontrado')
        return redirect('gestion_usuarios')

    if usuario.es_admin() or usuario.is_superuser:
        messages.error(request, 'No se puede modificar el rol de un administrador')
        return redirect('gestion_usuarios')

    if usuario.rol == nuevo_rol:
        messages.info(request, f'{usuario.username} ya tiene el rol {usuario.get_rol_display()}')
        return redirect('gestion_usuarios')

    rol_anterior = usuario.get_rol_display()
    usuario.rol = nuevo_rol
    usuario.save(update_fields=['rol'])
    messages.success(
        request,
        f'Rol de {usuario.username} actualizado: {rol_anterior} → {usuario.get_rol_display()}',
    )
    return redirect('gestion_usuarios')


@login_required_custom
def vista_2fa_disable(request):
    """
    Elimina todos los dispositivos TOTP del usuario autenticado.
    Solo acepta POST para evitar desactivación accidental por GET.
    """
    from django_otp.plugins.otp_totp.models import TOTPDevice
    if request.method == 'POST':
        TOTPDevice.objects.filter(user=request.user).delete()
        messages.success(request, '2FA desactivado')
    return redirect('dashboard')