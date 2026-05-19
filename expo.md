# Documentación Técnica: Autenticación, Registro y 2FA

Este documento detalla la implementación del sistema de gestión de usuarios y seguridad para la plataforma **InvPro Unipamplona**, enfocándose en el flujo de autenticación de dos factores (2FA).

## 1. Stack Tecnológico

La seguridad del sistema se apoya en las siguientes tecnologías:

*   **Django Auth System**: Núcleo para la gestión de sesiones y hashing de contraseñas (PBKDF2).
*   **Custom User Model**: Implementación de `AbstractUser` utilizando `UUID` como llave primaria para dificultar ataques de enumeración.
*   **django-otp**: Framework para manejar contraseñas de un solo uso (One-Time Passwords).
*   **TOTP (Time-based OTP)**: Algoritmo estándar (RFC 6238) para generar códigos basados en tiempo.
*   **python-qrcode**: Generación dinámica de códigos QR en formato Base64 para sincronización con aplicaciones móviles.

---

## 2. Modelo de Usuarios y Roles

El sistema utiliza un modelo personalizado llamado `CustomUser` ubicado en `apps.accounts.models`.

| Rol | Descripción | Permisos |
| :--- | :--- | :--- |
| **Administrador** | Gestión total | Acceso al panel de administración y control total de inventario. |
| **Operador** | Gestión operativa | Registro de entradas, salidas y ajustes de stock. |
| **Consultor** | Solo lectura | Visualización de reportes y estado de inventario. |

> **Nota:** Por seguridad, todo registro nuevo vía formulario público se asigna automáticamente como **Consultor**.

---

## 3. Flujo de Autenticación (Login)

Se implementó un flujo de **dos pasos** para garantizar que la sesión no se inicie hasta que se valide el segundo factor.

### Diagrama de Flujo Lógico
1.  **POST /login/**: El usuario envía credenciales.
2.  **Validación 1**: `authenticate(username, password)`.
3.  **Chequeo de 2FA**:
    *   **Si NO tiene 2FA**: Se llama a `login(request, user)` -> Redirección al Dashboard.
    *   **Si TIENE 2FA**:
        *   Se guarda el ID del usuario en `request.session['pre_2fa_user_pk']`.
        *   Se guarda el backend en `request.session['pre_2fa_backend']`.
        *   **No se inicia sesión** (el usuario sigue siendo `AnonymousUser` para el servidor).
        *   Redirección a `/2fa/verify/`.

---

## 4. Implementación de Doble Factor (2FA)

### A. Configuración Inicial (Setup)
Para activar el 2FA, el usuario debe estar autenticado. El proceso en `vista_2fa_setup` consiste en:
1.  Eliminar cualquier dispositivo TOTP previo no confirmado para evitar basura en la DB.
2.  Crear un nuevo `TOTPDevice` con estado `confirmed=False`.
3.  Generar una `config_url` que contiene el secreto compartido.
4.  Convertir la URL en un **Código QR** usando la librería `qrcode` y enviarlo al template como una cadena **Base64**.

### B. Verificación y Confirmación
En la vista `vista_2fa_verify`, el sistema valida el token de 6 dígitos:
*   **Durante el Setup**: Si el código es válido, el dispositivo se marca como `confirmed=True`.
*   **Durante el Login**: 
    1. Se recupera el usuario desde el PK temporal de la sesión.
    2. Se verifica el token contra el dispositivo confirmado.
    3. Si es exitoso, se ejecutan `login()` y `django_otp.login()` simultáneamente para elevar el nivel de seguridad de la sesión.

---

## 5. Medidas de Seguridad Adicionales

*   **Sesiones Temporales**: Los datos de "pre-autenticación" expiran si el usuario no completa el segundo factor en un tiempo determinado.
*   **Decoradores de Acceso**: Se crearon decoradores personalizados (`@operador_required`, `@consultor_required`) que verifican tanto la autenticación como el nivel de 2FA de la sesión.
*   **Protección contra Fuerza Bruta**: Al no iniciar la sesión en el primer paso del 2FA, se evita que un atacante con la contraseña correcta pueda acceder a información sensible o realizar acciones parciales.
*   **Cierre de Sesión Seguro**: La función `vista_logout` invalida tanto la sesión de Django como el estado de autenticación del dispositivo OTP.

---

## 6. Rutas Principales (Endpoints)

*   `accounts/login/`: Autenticación primaria.
*   `accounts/registro/`: Creación de cuentas (Rol Consultor).
*   `accounts/2fa/setup/`: Generación de QR y clave secreta.
*   `accounts/2fa/verify/`: Punto de validación de tokens.
*   `accounts/2fa/disable/`: Eliminación de dispositivos de seguridad (Solo mediante POST).
