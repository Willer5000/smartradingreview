# Auditoría de autenticación del repositorio

Repositorio auditado por GitHub: `Willer5000/smartradingreview`.
La autenticación fue introducida históricamente en el commit `178f05cd9a4bd2cac5781e93a115519eb95f4734` (`autenticacion commit 15`).

## Componentes

### 1. Flask Session — `app.py`
- `SMARTRADING_SESSION_SECRET` firma la sesión Flask.
- Cookies configuradas con `HttpOnly`, `Secure`, `SameSite=Lax` y sesión no permanente.
- La cookie guarda identidad de sesión; no guarda la contraseña.
- Flask firma la cookie con el `secret_key`; por defecto no es un token JWT de login ni un token Bearer del navegador.

### 2. Usuarios y credenciales — `app.py`
`_auth_users()` obtiene contraseñas exclusivamente de variables de entorno:
- `SMARTRADING_PASSWORD_WILLER`
- `SMARTRADING_PASSWORD_DANILO`
- `SMARTRADING_PASSWORD_DAMIR`

`/api/auth/login` recibe `user/password`, compara con `hmac.compare_digest`, limpia la sesión anterior y escribe `session['authenticated_user']` si coincide.

`/api/auth/me` resuelve el usuario desde la sesión del servidor/cookie firmada.

`/api/auth/logout` limpia la sesión.

`_require_auth()` es el guard que usan endpoints privados para devolver 401 si no hay sesión válida.

### 3. Frontend
`static/script.js` usa `credentials: 'same-origin'` para que el navegador envíe la cookie de sesión a `/api/auth/me`, `/api/auth/login` y `/api/auth/logout`.

El frontend no conserva la contraseña ni un Bearer token en localStorage. La identidad efectiva la decide Flask.

### 4. Supabase — `supabase_client.py`
La conexión es server-side. Prioridad de credenciales:
1. `CENTRAL_SUPABASE_SERVICE_KEY`
2. `SUPABASE_SERVICE_ROLE_KEY`
3. `SUPABASE_KEY` como compatibilidad

La URL prioriza `CENTRAL_SUPABASE_URL` y luego `SUPABASE_URL`.
Las service/secret keys no se envían al navegador por este flujo.

### 5. Tareas programadas / mantenimiento
Algunos endpoints administrativos usan `X-Auth-Key` y `SCHEDULED_AUTH_KEY`, separado de la sesión Flask.

## Flujo de request normal
1. El usuario introduce usuario/contraseña en la UI.
2. Browser → `POST /api/auth/login` JSON + `credentials:same-origin`.
3. Flask lee credencial esperada desde variables de entorno.
4. `hmac.compare_digest` valida.
5. Flask emite cookie de sesión firmada.
6. En requests siguientes, browser envía cookie automáticamente.
7. `_authenticated_user()` / `_require_auth()` validan la identidad.
8. Los endpoints server-side usan Supabase/Telegram con secretos del entorno; esos secretos no viajan al browser.
9. Logout borra la sesión.

## Manejo de tokens/credenciales
- Contraseñas: variables de entorno Render; no deben existir en GitHub.
- Session secret: variable `SMARTRADING_SESSION_SECRET`.
- Supabase secret/service role: sólo backend.
- Telegram token/chat: variables de entorno backend.
- Scheduled key: header `X-Auth-Key` comparado con `SCHEDULED_AUTH_KEY`.

## Hallazgo de seguridad importante tras hacer público el repositorio
El código actual conserva un fallback conocido para tareas programadas:
`crypto_trader_analyst_2025`.

Como el repositorio ahora es público, ese fallback ya no debe considerarse secreto. Recomendación inmediata de configuración, sin cambiar este commit de trading:
- verificar en Render que `SCHEDULED_AUTH_KEY` esté definido con un valor aleatorio largo y distinto al fallback;
- rotarlo si alguna vez se usó el valor por defecto.

Una mejora futura de seguridad debería eliminar el fallback y fallar cerrado si falta la variable. No se incluyó aquí para no romper jobs programados sin confirmar primero la configuración de Render.

## Limitación actual de las contraseñas
Las contraseñas de usuarios se comparan como secretos de entorno en texto, aunque usando comparación constante. Para una futura capa comercial conviene migrar a hashes de contraseña (Argon2/bcrypt/Werkzeug) y almacenamiento de usuarios, pero no es necesario para reparar el motor de trading y no se modificó en 17.5.1.
