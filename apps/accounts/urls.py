from django.urls import path
from . import views

urlpatterns = [
    path('login/',                views.vista_login,               name='login'),
    path('logout/',               views.vista_logout,              name='logout'),
    path('registro/',             views.vista_registro,            name='registro'),
    path('operador/dashboard/',   views.vista_dashboard_operador,  name='dashboard_operador'),
    path('consultor/dashboard/',  views.vista_dashboard_consultor, name='dashboard_consultor'),
    path('2fa/setup/',    views.vista_2fa_setup,   name='2fa_setup'),
    path('2fa/verify/',   views.vista_2fa_verify,  name='2fa_verify'),
    path('2fa/disable/',  views.vista_2fa_disable, name='2fa_disable'),
    path('operador/mis-movimientos/', views.vista_mis_movimientos, name='mis_movimientos'),
    path('consultor/reportes/',       views.vista_reportes_consultor, name='reportes_consultor'),
    path('usuarios/',                 views.vista_gestion_usuarios,   name='gestion_usuarios'),
    path('usuarios/<uuid:pk>/rol/',   views.cambiar_rol_usuario,      name='cambiar_rol_usuario'),
]