import os
import django
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from asgiref.sync import sync_to_async as _original_sync_to_async
from django.db import close_old_connections
from functools import wraps

def sync_to_async(func, *args, **kwargs):
    @wraps(func)
    def wrapper(*func_args, **func_kwargs):
        close_old_connections()
        try:
            return func(*func_args, **func_kwargs)
        finally:
            close_old_connections()
    return _original_sync_to_async(wrapper, *args, **kwargs)


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

app = FastAPI(
    title="InvPro API",
    description="API REST del Sistema de Inventario - Universidad de Pamplona",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

from fastapi.responses import JSONResponse
from django.utils.timezone import localtime
import traceback

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": traceback.format_exc()}
    )

# ── SCHEMAS ───────────────────────────────────────────────────────
class ProductoResponse(BaseModel):
    id:              str
    nombre:          str
    sku:             str
    descripcion:     str
    categoria_id:    str
    categoria_nombre:str
    stock_actual:    float
    stock_minimo:    float
    precio_unitario: float
    tiene_alerta:    bool
    is_active:       bool

class ProductoCreate(BaseModel):
    nombre:          str
    sku:             str
    descripcion:     Optional[str] = ''
    categoria_id:    str
    stock_actual:    float = 0
    stock_minimo:    float = 0
    precio_unitario: float = 0

class ProductoUpdate(BaseModel):
    nombre:          Optional[str] = None
    descripcion:     Optional[str] = None
    categoria_id:    Optional[str] = None
    stock_minimo:    Optional[float] = None
    precio_unitario: Optional[float] = None

# ── HEALTH ────────────────────────────────────────────────────────
@app.get("/v1/health")
async def health_check():
    return {"status": "ok", "sistema": "InvPro-Jhayder-Confirmado", "version": "1.0.0"}

# ── AUTH ──────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class RegistroRequest(BaseModel):
    username: str
    password: str
    nombre_completo: str = ""
    correo: str = ""
    telefono: str = ""
    direccion: str = ""

@app.post("/v1/auth/login/")
async def login(data: LoginRequest):
    return await sync_to_async(_login)(data)

def _login(data):
    from django.contrib.auth import authenticate
    user = authenticate(username=data.username, password=data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")
    return {
        "access": f"mock_access_token_{user.id}",
        "refresh": f"mock_refresh_token_{user.id}",
        "requires_2fa": False
    }

@app.post("/v1/auth/registro/", status_code=201)
async def registro(data: RegistroRequest):
    return await sync_to_async(_registro)(data)

def _registro(data):
    from apps.accounts.models import CustomUser
    if CustomUser.objects.filter(username=data.username).exists():
        raise HTTPException(status_code=400, detail="El usuario ya existe")
    
    user = CustomUser.objects.create_user(
        username=data.username,
        password=data.password,
        nombre_completo=data.nombre_completo,
        correo=data.correo,
        telefono=data.telefono,
        direccion=data.direccion
    )
    _registrar_auditoria(user, 'registro_usuario', f"Se registró nuevo usuario '{user.username}'")
    return {"status": "success", "id": str(user.id)}

@app.get("/v1/auth/perfil/")
async def perfil(
    username: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    return await sync_to_async(_perfil)(username, authorization)

def _perfil(username, authorization):
    from apps.accounts.models import CustomUser
    from django_otp.plugins.otp_totp.models import TOTPDevice
    from django.utils import timezone
    try:
        u = None
        
        # 1. Intentar buscar por token de autorización (Authorization: Bearer mock_access_token_{user_id})
        if authorization and "mock_access_token_" in authorization:
            try:
                user_id = authorization.split("mock_access_token_")[-1].strip()
                u = CustomUser.objects.filter(id=user_id).first()
            except Exception:
                pass
                
        # 2. Si no hay token o no se encontró, intentar por query parameter username
        if not u and username:
            u = CustomUser.objects.filter(username=username).first()
            
        # 3. Fallback: Devolver el primero en la base de datos (generalmente admin/superusuario)
        if not u:
            u = CustomUser.objects.first()
            
        if not u:
            raise HTTPException(status_code=404, detail="No hay usuarios en la base de datos")
            
        tiene_2fa = TOTPDevice.objects.filter(user=u, confirmed=True).exists()

        operaciones_hoy = 0
        total_este_mes = 0
        if u.rol == 'admin':
            from apps.audit.models import HistorialOperacion
            hoy = timezone.localdate()
            este_mes_inicio = hoy.replace(day=1)
            operaciones_hoy = HistorialOperacion.objects.filter(created_at__date=hoy).count()
            total_este_mes = HistorialOperacion.objects.filter(created_at__date__gte=este_mes_inicio).count()

        return {
            "id": str(u.id),
            "username": u.username,
            "nombre_completo": u.nombre_completo or u.username,
            "correo": u.correo,
            "telefono": u.telefono,
            "direccion": u.direccion,
            "rol": u.rol,
            "tiene_2fa": tiene_2fa,
            "operaciones_hoy": operaciones_hoy,
            "total_este_mes": total_este_mes
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── GESTIÓN DE USUARIOS (solo admin) ─────────────────────────────
class CambiarRolRequest(BaseModel):
    rol: str

def _get_user_from_auth_header(authorization):
    from apps.accounts.models import CustomUser
    if not authorization or "mock_access_token_" not in authorization:
        return None
    try:
        user_id = authorization.split("mock_access_token_")[-1].strip()
        return CustomUser.objects.filter(id=user_id).first()
    except Exception:
        return None

def _require_admin_user(authorization):
    user = _get_user_from_auth_header(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="No autenticado")
    if not user.es_admin():
        raise HTTPException(status_code=403, detail="Solo administradores pueden gestionar usuarios")
    return user

@app.get("/v1/usuarios/")
async def listar_usuarios(authorization: Optional[str] = Header(None)):
    return await sync_to_async(_listar_usuarios)(authorization)

def _listar_usuarios(authorization):
    _require_admin_user(authorization)
    from apps.accounts.models import CustomUser
    usuarios = CustomUser.objects.exclude(
        rol=CustomUser.ADMIN,
    ).filter(is_superuser=False).order_by('username')
    return [
        {
            "id": str(u.id),
            "username": u.username,
            "nombre_completo": u.nombre_completo or "",
            "correo": u.correo or u.email or "",
            "rol": u.rol,
            "rol_label": u.get_rol_display(),
        }
        for u in usuarios
    ]

@app.patch("/v1/usuarios/{user_id}/rol/")
async def cambiar_rol_usuario_api(
    user_id: str,
    data: CambiarRolRequest,
    authorization: Optional[str] = Header(None),
):
    return await sync_to_async(_cambiar_rol_usuario_api)(user_id, data, authorization)

def _cambiar_rol_usuario_api(user_id, data, authorization):
    from apps.accounts.models import CustomUser
    admin = _require_admin_user(authorization)
    if data.rol not in (CustomUser.OPERADOR, CustomUser.CONSULTOR):
        raise HTTPException(status_code=400, detail="Rol no válido. Use operador o consultor")
    try:
        usuario = CustomUser.objects.get(pk=user_id)
    except CustomUser.DoesNotExist:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if usuario.es_admin() or usuario.is_superuser:
        raise HTTPException(status_code=403, detail="No se puede modificar el rol de un administrador")
    if usuario.rol == data.rol:
        return {
            "status": "ok",
            "message": f"{usuario.username} ya tiene el rol {usuario.get_rol_display()}",
            "rol": usuario.rol,
            "rol_label": usuario.get_rol_display(),
        }
    rol_anterior = usuario.get_rol_display()
    usuario.rol = data.rol
    usuario.save(update_fields=['rol'])
    _registrar_auditoria(
        admin,
        'cambio_rol',
        f"Rol de {usuario.username}: {rol_anterior} → {usuario.get_rol_display()}",
    )
    return {
        "status": "ok",
        "message": f"Rol actualizado a {usuario.get_rol_display()}",
        "rol": usuario.rol,
        "rol_label": usuario.get_rol_display(),
    }

# ── 2FA ENDPOINTS ──────────────────────────────────────────────────
class Verify2FARequest(BaseModel):
    token: str

@app.post("/v1/auth/2fa/setup/")
async def setup_2fa(authorization: Optional[str] = Header(None)):
    return await sync_to_async(_setup_2fa)(authorization)

def _setup_2fa(authorization):
    from apps.accounts.models import CustomUser
    from django_otp.plugins.otp_totp.models import TOTPDevice

    user = None
    if authorization and "mock_access_token_" in authorization:
        try:
            user_id = authorization.split("mock_access_token_")[-1].strip()
            user = CustomUser.objects.filter(id=user_id).first()
        except Exception:
            pass

    if not user:
        user = CustomUser.objects.first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # Elimina dispositivos previos no confirmados del mismo usuario
    TOTPDevice.objects.filter(user=user, confirmed=False).delete()

    device, _ = TOTPDevice.objects.get_or_create(
        user=user,
        confirmed=False,
        defaults={'name': 'InvPro Unipamplona'},
    )

    return {
        "config_url": device.config_url,
        "secret": device.bin_key.hex()
    }

@app.post("/v1/auth/2fa/verify/")
async def verify_2fa(data: Verify2FARequest, authorization: Optional[str] = Header(None)):
    return await sync_to_async(_verify_2fa)(data.token, authorization)

def _verify_2fa(token, authorization):
    from apps.accounts.models import CustomUser
    from django_otp.plugins.otp_totp.models import TOTPDevice

    user = None
    if authorization and "mock_access_token_" in authorization:
        try:
            user_id = authorization.split("mock_access_token_")[-1].strip()
            user = CustomUser.objects.filter(id=user_id).first()
        except Exception:
            pass

    if not user:
        user = CustomUser.objects.first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    # 1. Intentar con dispositivo no confirmado (durante el setup)
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if device:
        if device.verify_token(token):
            device.confirmed = True
            device.save()
            _registrar_auditoria(user, 'activar_2fa', "Activó autenticación en dos pasos (2FA)")
            return {"status": "success", "detail": "2FA activado correctamente"}
        else:
            raise HTTPException(status_code=400, detail="Código incorrecto")

    # 2. Si no hay no confirmado, intentar con dispositivo ya confirmado
    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if device:
        if device.verify_token(token):
            return {"status": "success", "detail": "Código verificado correctamente"}
        else:
            raise HTTPException(status_code=400, detail="Código incorrecto")

    raise HTTPException(status_code=400, detail="Dispositivo 2FA no configurado")

@app.post("/v1/auth/2fa/disable/")
async def disable_2fa(authorization: Optional[str] = Header(None)):
    return await sync_to_async(_disable_2fa)(authorization)

def _disable_2fa(authorization):
    from apps.accounts.models import CustomUser
    from django_otp.plugins.otp_totp.models import TOTPDevice

    user = None
    if authorization and "mock_access_token_" in authorization:
        try:
            user_id = authorization.split("mock_access_token_")[-1].strip()
            user = CustomUser.objects.filter(id=user_id).first()
        except Exception:
            pass

    if not user:
        user = CustomUser.objects.first()

    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    TOTPDevice.objects.filter(user=user).delete()
    _registrar_auditoria(user, 'desactivar_2fa', "Desactivó autenticación en dos pasos (2FA)")
    return {"status": "success", "detail": "2FA desactivado correctamente"}

# ── DASHBOARD ─────────────────────────────────────────────────────
@app.get("/v1/dashboard/")
async def dashboard(authorization: Optional[str] = Header(None)):
    return await sync_to_async(_get_dashboard_data)(authorization)

def _get_dashboard_data(authorization):
    from django.utils import timezone
    from apps.inventory.models import Producto
    from apps.movements.models import Movimiento
    from apps.accounts.models import CustomUser
    from apps.movements.services import obtener_resumen_movimientos

    # 1. Identificar al usuario solicitante
    user = None
    if authorization and "mock_access_token_" in authorization:
        try:
            user_id = authorization.split("mock_access_token_")[-1].strip()
            user = CustomUser.objects.filter(id=user_id).first()
        except Exception:
            pass

    hoy = timezone.localdate()

    if user and user.rol == 'operador':
        # Si es un operador, devolvemos sus datos específicos
        entradas_hoy    = Movimiento.objects.filter(
            usuario=user, tipo=Movimiento.ENTRADA, created_at__date=hoy).count()
        salidas_hoy     = Movimiento.objects.filter(
            usuario=user, tipo=Movimiento.SALIDA, created_at__date=hoy).count()
        ajustes_hoy     = Movimiento.objects.filter(
            usuario=user, tipo=Movimiento.AJUSTE, created_at__date=hoy).count()

        ultimos = []
        for mov in Movimiento.objects.filter(usuario=user).select_related(
                'producto').order_by('-created_at')[:30]:  # Limit 30 for complete history
            ultimos.append({
                "tipo":     mov.tipo,
                "producto": mov.producto.sku,
                "producto_nombre": mov.producto.nombre,
                "cantidad": float(mov.cantidad),
                "fecha":    localtime(mov.created_at).strftime('%d/%m %H:%M'),
                "usuario":  mov.usuario.username,
            })

        return {
            "total_productos":     0,
            "entradas_hoy":        entradas_hoy,
            "salidas_hoy":         salidas_hoy,
            "alertas_activas":     ajustes_hoy, # Mapeamos Ajustes Hoy en alertas_activas
            "movimientos_7_dias":  [],
            "ultimos_movimientos": ultimos,
        }

    # Si es Administrador o Consultor, mantenemos el comportamiento original global
    from django.db.models import F
    total_productos  = Producto.objects.filter(is_active=True).count()
    entradas_hoy     = Movimiento.objects.filter(
        tipo=Movimiento.ENTRADA, created_at__date=hoy).count()
    salidas_hoy      = Movimiento.objects.filter(
        tipo=Movimiento.SALIDA, created_at__date=hoy).count()
    alertas_activas  = Producto.objects.filter(
        is_active=True,
        stock_actual__lte=F('stock_minimo')).count()

    ultimos = []
    for mov in Movimiento.objects.select_related(
            'producto', 'usuario').order_by('-created_at')[:10]:
        ultimos.append({
            "tipo":     mov.tipo,
            "producto": mov.producto.sku,
            "producto_nombre": mov.producto.nombre,
            "cantidad": float(mov.cantidad),
            "fecha":    localtime(mov.created_at).strftime('%d/%m %H:%M'),
            "usuario":  mov.usuario.username,
        })

    return {
        "total_productos":     total_productos,
        "entradas_hoy":        entradas_hoy,
        "salidas_hoy":         salidas_hoy,
        "alertas_activas":     alertas_activas,
        "movimientos_7_dias":  obtener_resumen_movimientos(dias=7),
        "ultimos_movimientos": ultimos,
    }

# ── PRODUCTOS — LISTAR ────────────────────────────────────────────
@app.get("/v1/productos/")
async def listar_productos(
    categoria: Optional[str] = None,
    alerta:    Optional[bool] = None,
    buscar:    Optional[str]  = None,
):
    return await sync_to_async(_listar_productos)(categoria, alerta, buscar)

def _listar_productos(categoria, alerta, buscar):
    from apps.inventory.models import Producto
    qs = Producto.objects.select_related('categoria').filter(is_active=True)

    if categoria:
        qs = qs.filter(categoria__nombre__icontains=categoria)
    if alerta is True:
        from django.db.models import F
        qs = qs.filter(stock_actual__lte=F('stock_minimo'))
    if buscar:
        qs = qs.filter(nombre__icontains=buscar) | \
             qs.filter(sku__icontains=buscar)

    return [_producto_to_dict(p) for p in qs]

# ── PRODUCTOS — ALERTAS ───────────────────────────────────────────
@app.get("/v1/productos/alertas/")
async def productos_en_alerta():
    return await sync_to_async(_productos_en_alerta)()

def _productos_en_alerta():
    from apps.inventory.models import Producto
    from django.db.models import F
    qs = Producto.objects.select_related('categoria').filter(
        is_active=True, stock_actual__lte=F('stock_minimo'))
    return [_producto_to_dict(p) for p in qs]

# ── PRODUCTOS — DETALLE ───────────────────────────────────────────
@app.get("/v1/productos/{producto_id}")
async def detalle_producto(producto_id: str):
    return await sync_to_async(_detalle_producto)(producto_id)

def _detalle_producto(producto_id):
    from apps.inventory.models import Producto
    try:
        p = Producto.objects.select_related('categoria').get(
            id=producto_id, is_active=True)
        return _producto_to_dict(p)
    except Producto.DoesNotExist:
        raise HTTPException(status_code=404, detail='Producto no encontrado')

# ── PRODUCTOS — CREAR ─────────────────────────────────────────────
@app.post("/v1/productos/", status_code=201)
async def crear_producto(
    data: ProductoCreate,
    username: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    return await sync_to_async(_crear_producto)(data, username, authorization)

def _crear_producto(data, username, authorization):
    from apps.inventory.models import Producto, Categoria
    from django.core.exceptions import ValidationError

    try:
        cat = Categoria.objects.get(id=data.categoria_id, is_active=True)
    except Categoria.DoesNotExist:
        raise HTTPException(status_code=404, detail='Categoria no encontrada')

    if Producto.objects.filter(sku=data.sku).exists():
        raise HTTPException(status_code=400,
            detail=f'Ya existe un producto con SKU {data.sku}')

    p = Producto.objects.create(
        nombre=data.nombre,
        sku=data.sku,
        descripcion=data.descripcion or '',
        categoria=cat,
        stock_actual=data.stock_actual,
        stock_minimo=data.stock_minimo,
        precio_unitario=data.precio_unitario,
    )
    
    usuario = _get_user_from_auth(username, authorization)
    _registrar_auditoria(usuario, 'crear_producto', f"Creó producto '{p.nombre}' (SKU: {p.sku})")
    
    return _producto_to_dict(p)

# ── PRODUCTOS — ACTUALIZAR ────────────────────────────────────────
@app.patch("/v1/productos/{producto_id}")
async def actualizar_producto(
    producto_id: str,
    data: ProductoUpdate,
    username: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    return await sync_to_async(_actualizar_producto)(producto_id, data, username, authorization)

def _actualizar_producto(producto_id, data, username, authorization):
    from apps.inventory.models import Producto, Categoria

    try:
        p = Producto.objects.select_related('categoria').get(
            id=producto_id, is_active=True)
    except Producto.DoesNotExist:
        raise HTTPException(status_code=404, detail='Producto no encontrado')

    if data.nombre          is not None: p.nombre          = data.nombre
    if data.descripcion     is not None: p.descripcion     = data.descripcion
    if data.stock_minimo    is not None: p.stock_minimo    = data.stock_minimo
    if data.precio_unitario is not None: p.precio_unitario = data.precio_unitario

    if data.categoria_id is not None:
        try:
            p.categoria = Categoria.objects.get(
                id=data.categoria_id, is_active=True)
        except Categoria.DoesNotExist:
            raise HTTPException(status_code=404,
                detail='Categoria no encontrada')

    p.save()
    
    usuario = _get_user_from_auth(username, authorization)
    _registrar_auditoria(usuario, 'editar_producto', f"Editó producto '{p.nombre}'")
    
    return _producto_to_dict(p)

# ── PRODUCTOS — ELIMINAR (soft delete) ────────────────────────────
@app.delete("/v1/productos/{producto_id}", status_code=204)
async def eliminar_producto(
    producto_id: str,
    username: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    await sync_to_async(_eliminar_producto)(producto_id, username, authorization)

def _eliminar_producto(producto_id, username, authorization):
    from apps.inventory.models import Producto
    try:
        p = Producto.objects.get(id=producto_id, is_active=True)
        p.is_active = False
        p.save(update_fields=['is_active'])
        
        usuario = _get_user_from_auth(username, authorization)
        _registrar_auditoria(usuario, 'eliminar_producto', f"Eliminó producto '{p.nombre}'")
    except Producto.DoesNotExist:
        raise HTTPException(status_code=404, detail='Producto no encontrado')

# ── MOVIMIENTOS — REGISTRAR ───────────────────────────────────────
class MovimientoCreate(BaseModel):
    tipo:        str
    producto_id: str
    cantidad:    float
    nota:        Optional[str] = ''

class MovimientoResponse(BaseModel):
    id:         str
    tipo:       str
    producto:   str
    cantidad:   float
    nota:       str
    usuario:    str
    created_at: str

@app.post("/v1/movimientos/", status_code=201)
async def registrar_movimiento(
    data: MovimientoCreate,
    username: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    return await sync_to_async(_registrar_movimiento)(data, username, authorization)

def _registrar_movimiento(data, username, authorization):
    from apps.movements.services import registrar_movimiento
    from apps.accounts.models import CustomUser
    from django.core.exceptions import ValidationError

    tipos_validos = ['entrada', 'salida', 'ajuste']
    if data.tipo not in tipos_validos:
        raise HTTPException(
            status_code=400,
            detail=f'Tipo invalido. Use: {tipos_validos}')

    # 1. Identificar al usuario que realiza el movimiento
    usuario = None
    if authorization and "mock_access_token_" in authorization:
        try:
            user_id = authorization.split("mock_access_token_")[-1].strip()
            usuario = CustomUser.objects.filter(id=user_id).first()
        except Exception:
            pass

    # 2. Si no hay token, intentar por query parameter username
    if not usuario and username:
        try:
            usuario = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            pass

    # 3. Fallback a admin si no se encuentra
    if not usuario:
        usuario = CustomUser.objects.filter(username="admin").first()
    if not usuario:
        usuario = CustomUser.objects.first()

    if not usuario:
        raise HTTPException(
            status_code=404,
            detail='No se pudo determinar un usuario para registrar el movimiento')

    try:
        mov = registrar_movimiento(
            tipo=data.tipo,
            producto_id=data.producto_id,
            cantidad=data.cantidad,
            usuario=usuario,
            nota=data.nota or '',
        )
        _registrar_auditoria(
            usuario,
            'registrar_movimiento',
            f"Registró movimiento de {data.tipo} de {data.cantidad} unidades para '{mov.producto.nombre}'",
            metadata={"producto_id": str(mov.producto.id), "cantidad": data.cantidad, "tipo": data.tipo}
        )
        return {
            "id":         str(mov.id),
            "tipo":       mov.tipo,
            "producto":   mov.producto.sku,
            "cantidad":   float(mov.cantidad),
            "nota":       mov.nota,
            "usuario":    mov.usuario.username,
            "created_at": localtime(mov.created_at).strftime('%d/%m/%Y %H:%M'),
        }
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ── MOVIMIENTOS — LISTAR ──────────────────────────────────────────
@app.get("/v1/movimientos/")
async def listar_movimientos(
    tipo:   Optional[str] = None,
    limite: int = 20,
):
    return await sync_to_async(_listar_movimientos)(tipo, limite)

def _listar_movimientos(tipo, limite):
    from apps.movements.models import Movimiento
    qs = Movimiento.objects.select_related('producto', 'usuario')

    if tipo:
        qs = qs.filter(tipo=tipo)

    qs = qs.order_by('-created_at')[:limite]

    return [{
        "id":         str(m.id),
        "tipo":       m.tipo,
        "producto":   m.producto.sku,
        "producto_nombre": m.producto.nombre,
        "cantidad":   float(m.cantidad),
        "nota":       m.nota,
        "usuario":    m.usuario.username,
        "created_at": localtime(m.created_at).strftime('%d/%m/%Y %H:%M'),
    } for m in qs]

# ── CATEGORIAS — LISTAR ───────────────────────────────────────────
@app.get("/v1/categorias/")
async def listar_categorias():
    return await sync_to_async(_listar_categorias)()

def _listar_categorias():
    from apps.inventory.models import Categoria
    qs = Categoria.objects.filter(is_active=True).order_by('nombre')
    return [{
        "id":          str(c.id),
        "nombre":      c.nombre,
        "prefix":      getattr(c, 'prefix', ''),
        "descripcion": c.descripcion,
        "productos":   c.productos.filter(is_active=True).count(),
    } for c in qs.prefetch_related('productos')]

# ── CATEGORIAS — NEXT SKU ─────────────────────────────────────────
@app.get("/v1/categorias/{categoria_id}/next-sku")
async def next_sku(categoria_id: str):
    return await sync_to_async(_next_sku)(categoria_id)

def _next_sku(categoria_id):
    from apps.inventory.models import Categoria, Producto
    try:
        cat = Categoria.objects.get(id=categoria_id, is_active=True)
    except Categoria.DoesNotExist:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    
    count = Producto.objects.filter(categoria=cat).count()
    siguiente_num = count + 1
    return {"sku": f"{cat.prefix}-{siguiente_num:04d}"}

# ── CATEGORIAS — CREAR ────────────────────────────────────────────
class CategoriaCreate(BaseModel):
    nombre:      str
    descripcion: Optional[str] = ''

class CategoriaUpdate(BaseModel):
    nombre:      Optional[str] = None
    descripcion: Optional[str] = None

@app.post("/v1/categorias/", status_code=201)
async def crear_categoria_api(
    data: CategoriaCreate,
    username: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    return await sync_to_async(_crear_categoria_api)(data, username, authorization)

def _crear_categoria_api(data, username, authorization):
    from apps.inventory.models import Categoria

    if Categoria.objects.filter(nombre=data.nombre).exists():
        raise HTTPException(
            status_code=400,
            detail=f'Ya existe la categoria {data.nombre}')

    cat = Categoria.objects.create(
        nombre=data.nombre,
        descripcion=data.descripcion or '',
    )
    
    usuario = _get_user_from_auth(username, authorization)
    _registrar_auditoria(usuario, 'crear_categoria', f"Creó categoría '{cat.nombre}'")
    
    return {
        "id":          str(cat.id),
        "nombre":      cat.nombre,
        "descripcion": cat.descripcion,
        "productos":   0,
    }

@app.patch("/v1/categorias/{categoria_id}")
async def editar_categoria_api(
    categoria_id: str,
    data: CategoriaUpdate,
    username: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    return await sync_to_async(_editar_categoria_api)(categoria_id, data, username, authorization)

def _editar_categoria_api(categoria_id, data, username, authorization):
    from apps.inventory.models import Categoria

    try:
        cat = Categoria.objects.get(id=categoria_id, is_active=True)
    except Categoria.DoesNotExist:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    if data.nombre is not None:
        cat.nombre = data.nombre
    if data.descripcion is not None:
        cat.descripcion = data.descripcion
    cat.save()

    usuario = _get_user_from_auth(username, authorization)
    _registrar_auditoria(usuario, 'editar_categoria', f"Editó categoría '{cat.nombre}'")

    return {
        "id":          str(cat.id),
        "nombre":      cat.nombre,
        "descripcion": cat.descripcion,
        "productos":   cat.productos.filter(is_active=True).count(),
    }

@app.delete("/v1/categorias/{categoria_id}", status_code=204)
async def eliminar_categoria_api(
    categoria_id: str,
    username: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    await sync_to_async(_eliminar_categoria_api)(categoria_id, username, authorization)

def _eliminar_categoria_api(categoria_id, username, authorization):
    from apps.inventory.models import Categoria

    try:
        cat = Categoria.objects.get(id=categoria_id, is_active=True)
        cat.is_active = False
        cat.save()
        
        usuario = _get_user_from_auth(username, authorization)
        _registrar_auditoria(usuario, 'eliminar_categoria', f"Eliminó categoría '{cat.nombre}'")
    except Categoria.DoesNotExist:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

# ── HISTORIAL DE OPERACIONES ──────────────────────────────────────
@app.get("/v1/historial/")
async def listar_historial(
    tipo: Optional[str] = None,
    limite: int = 50,
):
    return await sync_to_async(_listar_historial)(tipo, limite)

def _listar_historial(tipo, limite):
    from apps.audit.models import HistorialOperacion
    qs = HistorialOperacion.objects.select_related('autor')

    if tipo:
        qs = qs.filter(tipo=tipo)

    qs = qs.order_by('-created_at')[:limite]

    return [{
        "id":           str(h.id),
        "autor_id":     str(h.autor.id),
        "autor_nombre": h.autor.nombre_completo or h.autor.username,
        "tipo":         h.tipo,
        "tipo_label":   h.get_tipo_display(),
        "detalle":      h.detalle,
        "metadata":     h.metadata,
        "created_at":   localtime(h.created_at).strftime('%d/%m/%Y %H:%M'),
    } for h in qs]

# ── HELPER ────────────────────────────────────────────────────────
def _producto_to_dict(p):
    return {
        "id":               str(p.id),
        "nombre":           p.nombre,
        "sku":              p.sku,
        "descripcion":      p.descripcion,
        "categoria_id":     str(p.categoria.id),
        "categoria_nombre": p.categoria.nombre,
        "stock_actual":     float(p.stock_actual),
        "stock_minimo":     float(p.stock_minimo),
        "precio_unitario":  float(p.precio_unitario),
        "tiene_alerta":     p.tiene_alerta,
        "is_active":        p.is_active,
    }

def _get_user_from_auth(username, authorization):
    from apps.accounts.models import CustomUser
    usuario = None
    if authorization and "mock_access_token_" in authorization:
        try:
            user_id = authorization.split("mock_access_token_")[-1].strip()
            usuario = CustomUser.objects.filter(id=user_id).first()
        except Exception:
            pass

    if not usuario and username:
        try:
            usuario = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            pass

    if not usuario:
        usuario = CustomUser.objects.filter(username="admin").first()
    if not usuario:
        usuario = CustomUser.objects.first()
    return usuario

def _registrar_auditoria(autor, tipo, detalle="", metadata=None):
    from apps.audit.models import HistorialOperacion
    from apps.accounts.models import CustomUser
    try:
        if not autor:
            autor = CustomUser.objects.filter(username="admin").first() or CustomUser.objects.first()
        if autor:
            HistorialOperacion.objects.create(
                autor=autor,
                tipo=tipo,
                detalle=detalle,
                metadata=metadata or {}
            )
    except Exception as e:
        print(f"Error registrando auditoria: {e}")