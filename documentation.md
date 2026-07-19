
# DOCUMENTACIÓN COMPLETA DEL PROYECTO

## INES — Sistema Inteligente de Monitoreo de Infraestructura

---

## TABLA DE CONTENIDOS

1. [RESUMEN DEL PROYECTO](#1-resumen-del-proyecto)
2. [ARQUITECTURA GENERAL](#2-arquitectura-general)
3. [ESTRUCTURA DEL PROYECTO](#3-estructura-del-proyecto)
4. [CONFIGURACIÓN DEL PROYECTO (config/)](#4-configuración-del-proyecto-config)
5. [APLICACIONES DJANGO](#5-aplicaciones-django)
   - [5.1 apps/core](#51-appscore)
   - [5.2 apps/users](#52-appsusers)
   - [5.3 apps/buildings](#53-appsbuildings)
   - [5.4 apps/sensors](#54-appssensors)
   - [5.5 apps/authentication](#55-appsauthentication)
   - [5.6 apps/dashboard](#56-appsdashboard)
   - [5.7 apps/history](#57-appshistory)
   - [5.8 apps/thresholds](#58-appsthresholds)
   - [5.9 apps/limits](#59-appslimits)
   - [5.10 apps/settings](#510-appssettings)
6. [MODELO DE BASE DE DATOS](#6-modelo-de-base-de-datos)
7. [SISTEMA DE AUTENTICACIÓN](#7-sistema-de-autenticación)
8. [MOTOR DE SIMULACIÓN DE SENSORES](#8-motor-de-simulación-de-sensores)
9. [SISTEMA DE CLASIFICACIÓN DE RIESGO](#9-sistema-de-clasificación-de-riesgo)
10. [SISTEMA DE ALERTAS Y CORREO](#10-sistema-de-alertas-y-correo)
11. [SISTEMA DE REPORTES PDF](#11-sistema-de-reportes-pdf)
12. [FRONTEND Y UI](#12-frontend-y-ui)
13. [STREAMING SSE EN TIEMPO REAL](#13-streaming-sse-en-tiempo-real)
14. [SCRIPT DE POBLACIÓN DE BD](#14-script-de-población-de-bd)
15. [RUTAS COMPLETAS (URLS)](#15-rutas-completas-urls)
16. [DIAGRAMA DE FLUJO DE DATOS](#16-diagrama-de-flujo-de-datos)
17. [CONSIDERACIONES DE SEGURIDAD](#17-consideraciones-de-seguridad)

---

## 1. RESUMEN DEL PROYECTO

**INES** (Sistema Inteligente de Monitoreo) es una aplicación web desarrollada en **Django** que permite monitorear en tiempo real la infraestructura crítica de edificios: **bombas de agua** y **elevadores**. 

El sistema **simula** sensores IoT con física realista, clasifica el riesgo de cada variable (Normal/Alto/Crítico), inyecta fallas programáticas, envía alertas por correo electrónico con formato HTML profesional, y genera reportes PDF detallados. Todo mediante una interfaz web moderna con streaming en tiempo real vía **Server-Sent Events (SSE)**.

### Propósito
Servir como herramienta de monitoreo inteligente para administradores de edificios, permitiendo:
- Visualización en tiempo real del estado de bombas y elevadores
- Detección temprana de anomalías mediante clasificación de riesgo
- Simulación de 15 tipos de fallas con física realista
- Protección automática de equipos ante fallas críticas
- Generación de reportes PDF descargables
- Notificaciones por correo electrónico con diseño profesional
- Historial completo de eventos con filtros y búsqueda

### Stack Tecnológico
| Componente | Tecnología |
|------------|------------|
| Backend | Python 3.12+ / Django 5.x |
| Base de datos | PostgreSQL |
| Tiempo real | Eventlet (greenlets) + SSE |
| PDF | fpdf2 |
| Correo | smtplib + MIME |
| Frontend | HTML5, CSS3 (Vanilla), JavaScript (Vanilla) |
| Librerías JS | Font Awesome 6, ApexCharts, Chart.js |
| Autenticación | Sesiones con decoradores personalizados |
| Concurrencia | Eventlet monkey-patching |

---

## 2. ARQUITECTURA GENERAL

```
                    ┌─────────────────────────────────┐
                    │        Navegador Web            │
                    │   (HTML/CSS/JS Vanilla)         │
                    └──────────┬──────────────────────┘
                               │
              ┌────────────────┼────────────────────┐
              │                │                    │
         HTTP REST        SSE Stream          HTTP REST
       (AJAX fetches)   (text/event-stream)   (form submits)
              │                │                    │
              ▼                ▼                    ▼
    ┌─────────────────────────────────────────────────────┐
    │                 Django Server (Eventlet WSGI)       │
    │                                                     │
    │  ┌───────────┐ ┌──────────┐ ┌──────────────────┐   │
    │  │ Views     │ │ SSO      │ │Simulation Engine │   │
    │  │ (JSON/    │ │ Streamer │ │(greenlet loop)   │   │
    │  │  HTML)    │ │          │ │                   │   │
    │  └─────┬─────┘ └────┬─────┘ └────────┬──────────┘   │
    │        │             │                │              │
    │        ▼             ▼                ▼              │
    │  ┌──────────────────────────────────────────────┐   │
    │  │          Capa de Servicios                   │   │
    │  │  (Risk Service, PDF, SMTP, Payload, etc.)   │   │
    │  └──────────────────┬───────────────────────────┘   │
    │                     │                                │
    │                     ▼                                │
    │  ┌──────────────────────────────────────────────┐   │
    │  │              Django ORM + Models             │   │
    │  └──────────────────┬───────────────────────────┘   │
    └─────────────────────┼───────────────────────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │  PostgreSQL   │
                  │  (monitoreo_db) │
                  └───────────────┘
```

### Flujo de Inicio (server.py)
1. Se carga `.env` mediante `load_dotenv()`
2. Se aplica `eventlet.monkey_patch()` para hacer todas las operaciones asíncronas
3. Se parchea psycopg2 para ser compatible con greenlets
4. Se configura Django
5. Se crean los `BuildingSimulator` para cada equipo de monitoreo en BD
6. Se verifica conexión SMTP
7. Se inicia el watchdog del motor de simulación en un greenlet
8. Se inicia el servidor WSGI con `eventlet.wsgi.server()`

---

## 3. ESTRUCTURA DEL PROYECTO

```
TesisFinal/
├── .env                          # Variables de entorno (secretos)
├── .env.example                  # Ejemplo de variables de entorno
├── .gitignore                    # Archivos ignorados por git
├── manage.py                     # Entry point de Django (runserver)
├── requirements.txt              # Dependencias Python
├── server.py                     # Servidor de producción (eventlet WSGI)
├── documentation.md              # Este documento
│
├── config/                       # Configuración general de Django
│   ├── __init__.py
│   ├── asgi.py                   # ASGI entry point
│   ├── settings.py               # Configuración global
│   ├── urls.py                   # Enrutamiento raíz
│   └── wsgi.py                   # WSGI entry point
│
├── apps/                         # Aplicaciones Django
│   ├── __init__.py
│   │
│   ├── core/                     # Utilidades compartidas
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── auth_decorators.py    # Decoradores de autenticación
│   │   ├── constants.py          # Constantes globales
│   │   ├── dotenv.py             # Cargador de .env
│   │   ├── middleware.py         # AuthMiddleware
│   │   ├── smtp_service.py       # Servicio SMTP genérico
│   │   ├── utils.py              # Utilidades varias
│   │   ├── tests.py              # Tests unitarios
│   │   ├── services/             # Subservicios
│   │   │   ├── __init__.py
│   │   │   ├── http_request.py   # Helper de request
│   │   │   ├── http_response.py  # Helper de response JSON
│   │   │   ├── pdf_rendering.py  # Renderizado PDF
│   │   │   ├── pdf_shared.py     # Funciones PDF compartidas
│   │   │   └── risk_service.py   # Clasificador de riesgo
│   │   ├── templatetags/
│   │   │   ├── __init__.py
│   │   │   └── date_extras.py    # Template tags (naturaltime_es)
│   │   └── templates/core/       # Templates base
│   │       ├── layouts/
│   │       │   ├── base_sidebar.html
│   │       │   ├── base_public.html
│   │       │   ├── _list_base.html
│   │       │   └── _config_base.html
│   │       └── components/
│   │           ├── button.html
│   │           ├── empty_state.html
│   │           ├── history_item.html
│   │           ├── navbar.html
│   │           ├── pagination.html
│   │           ├── sidebar.html
│   │           └── toast_messages.html
│   │
│   ├── users/                    # Gestión de personas y usuarios
│   │   ├── __init__.py
│   │   ├── admin.py              # Registro admin
│   │   ├── apps.py
│   │   ├── emails.py             # Envío de correos (test, masivo)
│   │   ├── models.py             # Persona, Usuario
│   │   ├── reports.py            # PDF de usuarios
│   │   ├── services.py           # Lógica de negocio de usuarios
│   │   ├── urls.py               # Rutas de usuarios
│   │   ├── validators.py         # Validación de formularios
│   │   ├── views.py              # CRUD de usuarios
│   │   ├── templates/users/      # Templates de usuarios
│   │   └── migrations/
│   │
│   ├── buildings/                # Gestión de edificios
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py             # Building, MonitoringEquipment, UserBuilding
│   │   ├── pdf_builder.py        # PDF de reporte de edificio
│   │   ├── services.py           # Lógica de equipos
│   │   ├── shared.py             # Funciones compartidas
│   │   ├── urls.py
│   │   ├── validators.py         # Validación de edificios
│   │   ├── views.py              # CRUD de edificios
│   │   ├── templates/buildings/
│   │   └── migrations/
│   │
│   ├── sensors/                  # Simulación y sensores
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── engine.py             # Motor principal de simulación
│   │   ├── models.py             # SensorReading
│   │   ├── payload.py            # Constructor de payload live
│   │   ├── sensor_config.py      # Configuración central de sensores
│   │   ├── urls.py
│   │   ├── views.py              # API de resumen diario
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   └── payload_service.py # Lógica de payload
│   │   ├── simulation/           # Subsistema de simulación
│   │   │   ├── __init__.py
│   │   │   ├── constants.py      # Constantes físicas
│   │   │   ├── controls.py       # Control de simulación
│   │   │   ├── exceptions.py     # Excepciones de simulación
│   │   │   ├── fault_recovery.py # Recuperación de fallas
│   │   │   ├── globals.py        # Estado global (simulators dict)
│   │   │   ├── models.py         # BuildingSimulator
│   │   │   ├── simulation_engine.py # Dispatcher de simulación
│   │   │   ├── utils.py          # Clamp
│   │   │   └── physics/          # Física de equipos
│   │   │       ├── __init__.py
│   │   │       ├── pump.py       # Física de bomba
│   │   │       └── elevator.py   # Física de elevador
│   │   └── migrations/
│   │
│   ├── authentication/           # Login y registro
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── urls.py
│   │   ├── views.py              # Login, logout, complete_registration
│   │   └── templates/authentication/
│   │
│   ├── dashboard/                # Dashboard principal
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── shared.py             # build_monitoring_config
│   │   ├── urls.py               # Rutas del monitor y API
│   │   ├── views.py              # monitoring_view
│   │   ├── simulation/           # API de simulación
│   │   │   ├── __init__.py
│   │   │   ├── api.py            # API status
│   │   │   ├── controls.py       # Controles de simulación
│   │   │   ├── shared.py         # get_simulator
│   │   │   └── streaming.py      # SSE stream
│   │   └── templates/dashboard/
│   │
│   ├── history/                  # Historial y alertas
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── context_processors.py # Contador no leídos
│   │   ├── models.py             # History, UserDismissedHistory
│   │   ├── shared.py             # Parseo y filtrado de historial
│   │   ├── urls.py
│   │   ├── views.py              # CRUD de historial + PDF
│   │   ├── alerts/
│   │   │   ├── __init__.py
│   │   │   └── engine.py         # Motor de alertas compuestas
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── email_config.py   # EmailConfig, EmailAttachment
│   │   │   ├── email_recipients.py # Destinatarios
│   │   │   ├── email_sender.py   # Envío de correos
│   │   │   ├── email_templates.py # Plantillas HTML de correo
│   │   │   └── history_persistence.py # Persistencia de historial
│   │   ├── templates/history/
│   │   └── migrations/
│   │
│   ├── thresholds/               # Configuración de umbrales
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py             # ThresholdConfig
│   │   ├── services.py           # CRUD de umbrales
│   │   ├── urls.py
│   │   ├── views.py              # API de umbrales
│   │   ├── templates/thresholds/
│   │   └── migrations/
│   │
│   ├── limits/                   # Límites físicos de sensores
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py             # SensorLimitConfig
│   │   ├── services.py           # CRUD de límites
│   │   ├── urls.py
│   │   ├── views.py              # API de límites
│   │   ├── templates/limits/
│   │   └── migrations/
│   │
│   └── settings/                 # Configuración de perfil
│       ├── __init__.py
│       ├── apps.py
│       ├── urls.py
│       ├── views.py              # Cambio email, username, password
│       └── templates/settings/
│
├── static/                       # Archivos estáticos
│   ├── css/
│   │   └── styles.css            # ~2800 líneas de diseño CSS
│   └── js/
│       ├── shared.js             # Utilidades JS compartidas
│       ├── forms.js              # Validación de formularios
│       ├── monitoring.js         # Lógica del dashboard
│       ├── script.js             # Inicializador de páginas
│       ├── thresholds.js         # UI de umbrales
│       └── limits.js             # UI de límites
│
├── scripts/
│   └── populate_db.py            # Población de BD de prueba
│
└── venv/                         # Entorno virtual
```

---

## 4. CONFIGURACIÓN DEL PROYECTO (config/)

### 4.1 config/settings.py

**UBICACIÓN**: `config/settings.py` (130 líneas)

Configuración principal de Django. Puntos clave:

```python
# Variables de entorno obligatorias
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")  # Si falta: raise RuntimeError

# Debug (por defecto: false)
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() in ("true", "1", "yes")

# Hosts permitidos (separados por coma)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
```

**APPS INSTALADAS** (orden de carga):
1. Django por defecto (admin, auth, contenttypes, sessions, messages, staticfiles)
2. `apps.core` - Utilidades compartidas
3. `apps.users` - Gestión de usuarios
4. `apps.buildings` - Gestión de edificios
5. `apps.sensors` - Sensores y simulación
6. `apps.authentication` - Login/registro
7. `apps.dashboard` - Dashboard principal
8. `apps.history` - Historial y alertas
9. `apps.limits` - Límites de sensores
10. `apps.thresholds` - Umbrales de riesgo
11. `apps.settings` - Configuración de perfil

**MIDDLEWARE** (orden de ejecución):
1. SecurityMiddleware - Headers de seguridad
2. SessionMiddleware - Sesiones
3. CommonMiddleware - URLs canónicas
4. CsrfViewMiddleware - Protección CSRF
5. AuthenticationMiddleware - Auth de Django
6. MessageMiddleware - Mensajes flash
7. XFrameOptionsMiddleware - Clickjacking
8. **`AuthMiddleware`** (personalizado) - Verifica sesión en cada request

**CONTEXT PROCESSORS**:
- `apps.history.context_processors.unread_history_count` - Contador de alertas no leídas disponible en todos los templates como `{{ unread_history_count }}`

**BASE DE DATOS**:
```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "monitoreo_db"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}
```

**SESIÓN**:
- Duración: 28800 segundos (8 horas)
- Expira al cerrar navegador
- Cookie HTTPOnly
- SameSite: Lax
- `SESSION_SAVE_EVERY_REQUEST = True` - Renueva expiración en cada request

**SEGURIDAD** (en producción):
- Cookies seguras (HTTPS)
- SSL Redirect
- HSTS por 1 año
- Content-Type nosniff
- XSS filter
- Referrer policy: same-origin
- X-Frame-Options: DENY
- CSRF Cookie HTTPOnly

**OTROS**:
- `TIME_ZONE = "America/Caracas"`
- `TOKEN_MAX_AGE = 86400` (24h para tokens de registro)
- `STATICFILES_DIRS` = carpeta `static/` raíz
- Cache de memoria local (`LocMemCache`)

### 4.2 config/urls.py

**UBICACIÓN**: `config/urls.py` (15 líneas)

Enrutamiento raíz. Incluye todas las apps por path vacío `""`:

```python
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.dashboard.urls")),
    path("", include("apps.authentication.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.buildings.urls")),
    path("", include("apps.history.urls")),
    path("", include("apps.limits.urls")),
    path("", include("apps.thresholds.urls")),
    path("", include("apps.settings.urls")),
    path("", include("apps.sensors.urls")),
]
```

### 4.3 manage.py y server.py

**manage.py**: Entry point para `python manage.py runserver`. 
- Carga `.env`
- Aplica `eventlet.monkey_patch()` y parchea psycopg2
- Si se ejecuta `runserver` con `--noreload` o `RUN_MAIN=true`:
  - Inicializa Django
  - Crea BuildingSimulators para cada equipo en BD
  - Inicia el watchdog del motor de simulación en un greenlet

**server.py**: Entry point para producción.
- Carga `.env` ANTES de Django setup
- Aplica monkey_patch, parchea psycopg2
- Inicializa Django, crea simuladores
- Verifica conexión SMTP con login de prueba
- Inicia watchdog de simulación
- Inicia servidor WSGI con `eventlet.wsgi.server()` en `0.0.0.0:8000`

### 4.4 .env (Variables de Entorno)

```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...@gmail.com
SMTP_PASSWORD=... (app password)
DJANGO_SECRET_KEY=...
DJANGO_DEBUG=true
DB_NAME=monitoreo_db
DB_USER=postgres
DB_PASSWORD=...
DB_HOST=127.0.0.1
DB_PORT=5432
```

---

## 5. APLICACIONES DJANGO

---

## 5.1 apps/core

**Propósito**: Proporciona servicios transversales a todas las demás apps.

### Archivos:

#### `auth_decorators.py`
```python
ADMIN_ROLES = ("SA",)  # Solo "SA" es admin

is_admin_role(rol)          # Verifica si un rol es admin
login_required(view_func)   # Redirige a login si no hay usuario_id en sesión
admin_required(view_func)   # Redirige a monitor si no es admin (rol != "SA")
```

#### `middleware.py` (AuthMiddleware)
Middleware que se ejecuta en CADA request:

1. **Rutas públicas** (sin autenticación): `/login/`, `/static/`, `/admin/`, `/complete-registration/`
2. Si no está autenticado y no es ruta pública → redirige a login
3. Si está autenticado y va a login → redirige a monitor
4. Si está autenticado y va a ruta de admin → verifica que sea rol "SA"
5. Verifica que el usuario exista en BD (si no, limpia sesión)
6. Agrega headers de caché: `no-cache, no-store, must-revalidate, private`

Las rutas de administración se cachean cada 5s (debug) o 300s (producción):
- `user_list`, `user_create`, `building_list`, `register_building`
- `sensor_limits`, `user_edit`, `user_delete`, `edit_building`, `delete_building`

#### `dotenv.py`
Cargador de `.env` casero (sin librerías externas):
- Lee archivo línea por línea
- Ignora comentarios (`#`) y líneas sin `=`
- Usa `os.environ.setdefault()` para no sobreescribir variables existentes

#### `smtp_service.py`
Servicio SMTP genérico con 3 funciones:

1. **`get_smtp_creds()`**: Obtiene credenciales SMTP desde parámetros o variables de entorno
2. **`smtp_send()`**: Conecta vía SMTP con STARTTLS, envía mensaje a cada destinatario
3. **`build_mime_message()`**: Construye mensaje MIME multiparte con:
   - Versión HTML
   - Versión texto plano (fallback)
   - PDF adjunto opcional

#### `utils.py`
```python
verify_password(raw_password, user)  # Usa check_password de django hashers
```

#### `constants.py`
```python
MIN_PASSWORD_LENGTH = 8
MAX_USERNAME_LENGTH = 20
MIN_USERNAME_LENGTH = 4
```

#### services/risk_service.py
**Clasificador de riesgo** (función pura, sin BD):
```python
classify_risk(variable, value, thresholds=None) -> (risk_level, css_color)
```
Soporta 3 modos de dirección:
- **"higher"**: Mayor es peor. Normal ≤ high, Alto ≤ critic, Crítico > critic
- **"lower"**: Menor es peor. Normal ≥ high, Alto ≥ critic, Crítico < critic
- **"range"**: Valor debe estar en rango. Crítico si fuera de [high, critic], Normal si dentro del 60% central, Alto si en las bandas del 20%

#### services/http_request.py
```python
get_building_id_param(request, *param_names)  # Extrae building_id de GET params
```

#### services/http_response.py
```python
json_error(msg, status=400)  # {"status": "error", "message": msg}
json_ok(extra=None)          # {"status": "ok", ...extra}
```

#### services/pdf_shared.py
Funciones base para PDF:
- `_resolve_font()`: Busca DejaVuSans.ttf o Arial.ttf en rutas de Windows/Linux/macOS
- `_pdf_font()`: Agrega fuente y establece estilo/tamaño
- `safe_text()`: Si no hay fuente Unicode, reemplaza acentos por ASCII
- `draw_row()`: Dibuja fila de tabla con:
  - Cálculo automático de altura según contenido
  - Zebra striping (filas pares)
  - Colores de fondo y texto por celda
  - Salto de página automático si no cabe

#### services/pdf_rendering.py
Funciones de renderizado PDF de alto nivel:
- `render_logo()`: Logo INES con barra azul
- `render_pdf_header()`: Encabezado con logo, título, metadatos
- `render_section_divider()`: Divisor de sección
- `render_summary_box()`: Caja de resumen con múltiples items
- `render_severity_legend()`: Leyenda de colores de severidad
- `render_stats_summary()`: Resumen de estadísticas
- `render_table_header()`: Encabezado de tabla
- `render_event_rows()`: Filas de eventos con colores por riesgo
- `make_pdf_response()`: Convierte PDF a HttpResponse
- `_create_report_pdf()`: Crea instancia de FPDF con header/footer personalizados

#### templatetags/date_extras.py
```python
naturaltime_es(value)  # "Ahora", "Hace 5 min", "Hace 3 h", "Hace 2 d", o "01/01/2024"
```

---

## 5.2 apps/users

**Propósito**: Gestión completa de personas y usuarios del sistema.

### Modelos

#### Persona (`persona`)

| Campo | Tipo | BD | Detalles |
|-------|------|-----|----------|
| id_persona | AutoField (PK) | `id_persona` | |
| ci | CharField(16) | `ci` | Único, formato: V-12345678 |
| first_name | CharField(40) | `primer_nombre` | |
| middle_name | CharField(40) | `segundo_nombre` | Blank, default "" |
| first_last_name | CharField(40) | `primer_apellido` | |
| second_last_name | CharField(40) | `segundo_apellido` | Blank, default "" |
| email | EmailField(75) | `email` | Único |

Métodos: `get_full_name()` → "Juan Carlos Perez Gomez"

#### Usuario (`usuario`)

| Campo | Tipo | BD | Detalles |
|-------|------|-----|----------|
| id_usuario | AutoField (PK) | `id_usuario` | |
| username | CharField(100) | `username` | Único |
| password | CharField(255) | `password` | Hash Django |
| id_persona | OneToOneField→Persona | `id_persona` | CASCADE |
| rol | CharField(2) | `rol` | "US"=Usuario, "SA"=Super Admin |
| registered | BooleanField | `registrado` | Default False |

### Validators (`validators.py`)

Expresiones regulares de validación:

| Función | Regex | Uso |
|---------|-------|-----|
| `REGEX_ONLY_LETTERS` | `^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s]+$` | Nombres y apellidos |
| `_REGEX_EMAIL` | `^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)+$` | Correos |
| `_REGEX_VENEZUELAN_CI` | `^[VEve]\-?\d{6,14}$` | Cédula venezolana |
| `_REGEX_BUILDING_RIF` | `^[Jj]\-?\d{7,9}\-?\d$` | RIF jurídico |
| `REGEX_ADDRESS` | `^[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s\,\.\#\-\/\(\)]+$` | Direcciones |
| `REGEX_USERNAME` | `^[a-zA-ZáéíóúÁÉÍÓÚñÑ0-9]+$` | Username |
| `REGEX_PASSWORD` | `(?=.*[a-zA-Z])(?=.*\d)` | Contraseña (debe tener letras y números) |

Funciones:
- `normalize_ci()`: "V12345678" → "V-12345678"
- `normalize_rif()`: "J123456780" → "J-12345678-0"
- `validate_user_form()`: Valida todos los campos, retorna dict de errores

### Views

| Vista | Ruta | Método | Auth | Descripción |
|-------|------|--------|------|-------------|
| `user_list_view` | `/users/` | GET | admin | Lista paginada con filtros |
| `user_create_view` | `/users/create/` | GET/POST | admin | Crear usuario + enviar activación |
| `user_update_view` | `/users/<id>/edit/` | GET/POST | admin | Editar usuario |
| `user_delete_view` | `/users/<id>/delete/` | GET | admin | Eliminar usuario y persona |
| `check_cedula_uniqueness_view` | `/api/check-cedula/` | GET | Público | Verificar unicidad de cédula |
| `user_link_building_view` | `/api/users/<id>/link-building/` | POST | admin | Vincular edificio a usuario |
| `user_unlink_building_view` | `/api/users/<id>/unlink-building/` | POST | admin | Desvincular edificio |

### Services (`services.py`)

- `build_user_data()`: Construye dict con datos completos del usuario (incluyendo edificios)
- `generate_random_password()`: 10 caracteres alfanuméricos con `secrets`
- `build_random_username()`: Genera username tipo "JPerez" + contador si existe
- `send_activation_email()`: Envía correo con token firmado
- `_filter_users_query()`: Filtra usuarios por query, edificio, estado (con exclude de admins)
- `create_user_with_retry()`: Crea usuario con reintentos si username duplicado

### Emails (`emails.py`)

Envío de reportes por correo:
- `send_test_email()`: Envía reporte a un correo específico
- `send_all_subscribers()`: Envía reporte a todos los usuarios de un edificio
- Manejo de errores SMTP con mensajes en español (límite diario Gmail, auth, conexión)

### Reports (`reports.py`)

- `user_pdf_view()`: Genera PDF con lista de usuarios agrupados por edificio
  - Resumen con totales, registrados, pendientes
  - Tabla por edificio
  - Colores por estado

---

## 5.3 apps/buildings

**Propósito**: Gestión de edificios y equipos de monitoreo.

### Modelos

#### Building (`edificio`)

| Campo | Tipo | BD | Detalles |
|-------|------|-----|----------|
| id | AutoField (PK) | `id_edificio` | |
| name | CharField(40) | `nb_edificio` | |
| rif | CharField(16) | `rif` | Único, formato J-XXXXXXXX-X |
| address | CharField(100) | `direccion` | |
| floors | PositiveIntegerField | `cantidad_pisos` | 1-150 |

#### MonitoringEquipment (`equipo_monitoreo`)

| Campo | Tipo | BD | Detalles |
|-------|------|-----|----------|
| id | AutoField (PK) | `id_equipo_monitoreo` | |
| name | CharField(255) | `nb_equipo` | |
| building | ForeignKey→Building | `id_edificio` | CASCADE, related="equipment" |
| equipment_type | CharField(20) | `tipo` | "bomba" o "elevador" |
| status | CharField(20) | `status` | "operativo", "falla", "mantenimiento" |

**Restricción**: UniqueConstraint(building, equipment_type) - un edificio no puede tener dos bombas ni dos elevadores

#### UserBuilding (`usuario_edificio`)

| Campo | Tipo | BD |
|-------|------|-----|
| id | AutoField (PK) | `id_asignacion` |
| user | ForeignKey→Usuario | `id_usuario` |
| building | ForeignKey→Building | `id_edificio` |

**Restricción**: UniqueConstraint(user, building)

### Views

| Vista | Ruta | Método | Auth | Descripción |
|-------|------|--------|------|-------------|
| `building_list_view` | `/buildings/` | GET | admin | Lista paginada con filtros |
| `register_building_view` | `/buildings/create/` | GET/POST | admin | Crear edificio + equipos |
| `edit_building_view` | `/buildings/<id>/edit/` | GET/POST | admin | Editar edificio |
| `delete_building_view` | `/buildings/<id>/delete/` | POST | admin | Eliminar (CASCADE) |
| `check_rif_uniqueness_view` | `/api/check-rif/` | GET | Público | Verificar RIF único |
| `building_report_pdf_view` | `/buildings/<id>/report/pdf/` | GET | auth | PDF del edificio |

### Services (`services.py`)

```python
@dataclass
class EquipmentConfig:
    has_elevator: bool = False

sync_equipment_for_building(building, config)  # Crea/elimina equipos según config
```

### Shared (`shared.py`)
- `extract_building_data(request)`: Extrae datos del formulario
- `extract_equipment_config(request)`: Extrae si tiene elevador

### PDF Builder (`pdf_builder.py`)

**Función principal**: `generate_building_report_bytes(edificio_id)`

Genera un PDF completo con:

1. **Header**: Logo INES, nombre del edificio, RIF, dirección, fecha
2. **Resumen ejecutivo**: Conteo de sensores por severidad (Normal/Alto/Crítico)
3. **Equipos registrados**: Tabla con nombre, tipo, estado (con colores)
4. **Leyenda de severidades**: Colores y descripciones
5. **Sensores en estado crítico/alto**: Tabla prioritaria
6. **Lecturas actuales**: Tablas separadas por Bomba y Elevador
7. **Estadísticas**: Promedio, mínimo, máximo de la última hora
8. **Historial**: Conteo por severidad en el período
9. **Umbrales configurados**: Tabla de límites de riesgo
10. **Límites físicos**: Configuración de límites máximos

---

## 5.4 apps/sensors

**Propósito**: Corazón del sistema. Define la configuración de sensores, el motor de simulación, y el modelo de lecturas.

### sensor_config.py

Archivo de configuración central (348 líneas). Define:

**Variables de sensores** (16 variables):

| Variable | Nombre | Unidad | Tipo |
|----------|--------|--------|------|
| pump_flow_rate | Caudal | l/s | Bomba |
| pump_pressure | Presión | bar | Bomba |
| pump_temperature | Temperatura | °C | Bomba |
| pump_vibration | Vibración | mm/s | Bomba |
| pump_tank_level | Nivel de tanque | % | Bomba |
| pump_voltage | Voltaje | V | Bomba |
| pump_current | Corriente | A | Bomba |
| pump_water_quality | Calidad de agua | ppm | Bomba |
| elev_position | Posición | piso | Elevador |
| elev_speed | Velocidad | m/s | Elevador |
| elev_load | Carga | kg | Elevador |
| elev_door_status | Estado de puerta | - | Elevador (enum) |
| elev_temperature | Temperatura | °C | Elevador |
| elev_current | Corriente | A | Elevador |
| elev_vibration | Vibración | mm/s | Elevador |
| elev_voltage | Voltaje | V | Elevador |

**Niveles de riesgo**:
```python
RISK_NORMAL = "Normal"     # Verde
RISK_ALTO = "Alto"         # Naranja
RISK_CRITICO = "Crítico"   # Rojo
RISK_RESUELTA = "Resuelta" # Verde (para historial)
```

**Umbrales por defecto** (`DEFAULT_THRESHOLDS`):

| Variable | Dirección | Normal | Alto | Crítico |
|----------|-----------|--------|------|---------|
| pump_flow_rate | higher | ≤18.0 | ≤22.0 | >22.0 l/s |
| pump_pressure | range | 1.1-6.5 | 0.5-1.1 / 6.5-8.0 | <0.5 o >8.0 bar |
| pump_temperature | higher | ≤60.0 | ≤85.0 | >85.0 °C |
| pump_vibration | higher | ≤4.5 | ≤7.1 | >7.1 mm/s |
| pump_tank_level | range | 27-78 | 10-27 / 78-95 | <10 o >95 % |
| pump_voltage | range | 206.8-233.2 | 198-206.8 / 233.2-242 | <198 o >242 V |
| pump_current | higher | ≤16.0 | ≤22.0 | >22.0 A |
| pump_water_quality | higher | ≤300 | ≤500 | >500 ppm |
| elev_speed | higher | ≤1.2 | ≤1.6 | >1.6 m/s |
| elev_load | higher | ≤600 | ≤800 | >800 kg |
| elev_temperature | higher | ≤60.0 | ≤80.0 | >80.0 °C |
| elev_current | higher | ≤25.0 | ≤35.0 | >35.0 A |
| elev_vibration | higher | ≤3.0 | ≤5.0 | >5.0 mm/s |
| elev_voltage | range | 357.2-402.8 | 342-357.2 / 402.8-418 | <342 o >418 V |

**Tipos de falla** (15 en total):

Bomba (8):
| Clave | Nombre | Variables afectadas |
|-------|--------|-------------------|
| dry_run | Sequía | flow_rate, pressure, temperature, vibration, tank_level, current |
| blocked_discharge | Descarga bloqueada | flow_rate, pressure, vibration, temperature, current |
| pipe_burst | Ruptura de tubería | flow_rate, pressure, vibration, temperature, current, tank_level |
| cavitation | Cavitación | flow_rate, vibration, pressure, temperature |
| overheat | Sobrecalentamiento | temperature, vibration |
| power_surge | Sobrecarga eléctrica | flow_rate, pressure, voltage, current, temperature, vibration |
| power_outage | Corte eléctrico | voltage, current, flow_rate, pressure, vibration, temperature |
| bearing_failure | Falla de rodamientos | vibration, temperature, current, water_quality |

Elevador (7):
| Clave | Nombre | Variables afectadas |
|-------|--------|-------------------|
| motor_stuck | Motor atascado | temperature, speed, current, door_status, voltage, vibration |
| door_blocked | Puerta bloqueada | door_status, speed |
| overspeed | Exceso de velocidad | speed, current, door_status, vibration |
| overload | Sobrecarga | load, door_status, speed, current, vibration |
| pos_sensor_fail | Fallo sensor posición | position, speed, door_status |
| commercial_power_outage | Corte energía comercial | voltage, current, speed, door_status, temperature |
| traction_loss | Pérdida de tracción | position, speed, current, vibration, temperature |

**Rangos físicos** (`SENSOR_RANGES`):
- Límites realistas para cada variable
- Ej: pump_pressure (0.0, 10.0) bar, elev_speed (0.0, 3.0) m/s

**Rangos absolutos** (`SENSOR_ABSOLUTE_RANGES`):
- Techos máximos configurables (más amplios)
- Para validación de límites

**Constantes de simulación**:
```python
SIM_TICK_INTERVAL = 1          # 1 segundo entre ticks
MAX_PDF_EVENTS = 200           # Máx eventos en PDF
PAGE_SIZE = 15                 # Paginación
SMTP_TIMEOUT = 15              # Timeout SMTP
DAILY_PERSIST_INTERVAL = 30    # Persistir cada 30 ticks
DAILY_RETENTION_DAYS = 8       # Retención de lecturas
PAYLOAD_HISTORY_SLICE = 200    # History en payload
```

### models.py

#### SensorReading (`lectura_sensor`)

| Campo | Tipo | BD |
|-------|------|-----|
| building | ForeignKey→Building | `id_edificio` |
| variable | CharField(50) | `variable` |
| value | FloatField | `valor` |
| risk | CharField(20) | `riesgo` |
| timestamp | DateTimeField | `fecha` (db_index) |

Índice compuesto: (building, variable, timestamp)

### views.py

#### daily_summary(request, building_id)
API GET que retorna resumen diario de lecturas:
- Parámetro `?days=7` (1-30)
- Retorna JSON con labels (días) y datos agrupados por pump/elevator
- Cada variable tiene avg, min, max por día

### simulation/constants.py

Constantes físicas detalladas:

**Bomba**:
- `PUMP_P0 = 7.0` (presión base), `PUMP_K = 0.012` (constante de pérdida)
- `T_AMBIENT = 22.0` (temperatura ambiente)

**Elevador**:
- `CRUISING_SPEED = 1.0 m/s`
- `ACCELERATION = 0.8 m/s²`
- `FLOOR_HEIGHT = 3.5 m`
- `PASSENGER_WAIT_TICKS = 8`
- `G = 9.81 m/s²` (gravedad)
- `JERK = 0.5 m/s³` (límite de sacudida para curva S)
- `CABIN_EMPTY_MASS = 800 kg`
- `RATED_LOAD = 500 kg`
- `COUNTERWEIGHT_MASS = 1025 kg` (M_cw = M_empty + 0.45 * M_rated)
- `MOTOR_EFFICIENCY = 0.85`
- `DOOR_OPEN_TIME = 2.0 s`
- `DOOR_CLOSE_TIME = 2.0 s`
- `OVERLOAD_EXTRA_KG = 900 kg`
- `POWER_OUTAGE_BRAKE_TIME = 0.1 s`
- `POWER_OUTAGE_BATTERY_WAIT = 3.0 s`
- `BATTERY_RESCUE_SPEED = 0.3 m/s`
- `OVERSPEED_GOVERNOR_TRIGGER = 1.25 × CRUISING_SPEED`
- `PROTECTION_GRACE_TICKS = 5`

**Valores iniciales seguros** (`DEFAULT_SENSOR_DATA`):
- Bomba apagada: presión=1.0 bar, temp=25°C, vib=0 mm/s, volt=220V, current=0A
- Elevador detenido: speed=0 m/s, load=0 kg, temp=25°C, door=closed, pos=piso 0

### simulation/models.py

#### AlertDispatcher
Dispatcher de eventos con cola (deque maxlen=500) y subscribers:
- `append()`: Agrega evento y notifica a subscribers
- `clear()`: Limpia eventos y subscribers

#### BuildingSimulator
Clase principal del simulador. Atributos:

| Atributo | Tipo | Descripción |
|----------|------|-------------|
| edificio_id | int | ID del edificio |
| nombre | str | Nombre del edificio |
| equipment_types | set | {"bomba"}, {"elevador"}, o ambos |
| floors | int | Cantidad de pisos |
| sensor_data | dict | Valores actuales de sensores |
| has_pump / has_elevator | bool | Equipos disponibles |
| pump_on / elevator_on | bool | Encendido/apagado |
| active_alerts | dict | Alertas activas |
| history | list | Historial en memoria |
| pending_alerts | AlertDispatcher | Alertas pendientes de enviar |
| sim_paused | bool | Simulación pausada |
| sim_started | bool | Simulación iniciada |
| sim_speed | float | Velocidad de simulación (0.1-10) |
| sim_faults | dict | Fallas activas {device: fault_type} |
| auto_faults_enabled | bool | Inyección automática de fallas |
| protection_on | bool | Protección automática activada |

**Atributos de transición de fallas**:
- `fault_transition_pump/elev`: "stable" | "injecting" | "recovering"
- `_fault_targets_pump/elev`: Targets de ramping

**Atributos de física de elevador**:
- `_elev_motor_torque_factor`: Factor de torque (0.0 = motor atascado)
- `_elev_door_obstructed`: Puerta bloqueada físicamente
- `_elev_speed_governor_failed`: Gobernador de velocidad fallido
- `_elev_overload_extra_kg`: Carga extra por falla de sobrecarga
- `_elev_pos_sensor_stuck`: Sensor de posición congelado
- `_elev_power_available`: Disponibilidad de energía
- `_elev_brake_failed`: Freno mecánico fallido

### simulation/globals.py
```python
simulators: dict[int, BuildingSimulator] = {}
```
Diccionario global de simuladores (clave = edificio_id). Es el estado compartido entre todos los greenlets.

### simulation/simulation_engine.py
```python
update_sensor_data(active_sim: BuildingSimulator)
```
Dispatcher: si tiene bomba, llama a `_update_pump()`; si tiene elevador, llama a `_update_elevator()`

### simulation/controls.py

Control programático de la simulación:

- `inject_fault(edificio_id, device, fault_type)`: Inyecta falla con transición progresiva
- `clear_fault(edificio_id, device)`: Limpia falla(s), marca historial como resuelto, aplica recuperación
- `reset_simulator(edificio_id)`: Reinicia todo el simulador a estado seguro (pausado)

### simulation/exceptions.py
- `SimulatorError`: Base
- `SimulatorNotFoundError` (404)
- `InvalidDeviceError` (400)
- `DeviceNotInBuildingError` (400)
- `InvalidFaultTypeError` (400)
- `DeviceOffError` (409)

### physics/pump.py

**Modelo físico de bomba** (457 líneas):

**Operación normal** (`_run_pump_normal`):
1. Voltaje → converge a 220V con ruido
2. Si voltaje < 50V → todos los outputs caen a cero
3. Si nivel de tanque < 10% → modo cavitación (caudal baja, vibración sube)
4. Modo normal:
   - Caudal: random walk con límite en 85% del umbral alto
   - Presión: P = P0 - K * Q² (curva característica de bomba)
   - Temperatura: modelo térmico de primer orden
   - Vibración: función de caudal y temperatura
   - Corriente: modelo eléctrico (P_eléctrica = P_mecánica / eficiencia)

**Fallas de bomba** (cada una define valores target para ramping):

| Falla | Efecto |
|-------|--------|
| dry_run | Caudal=0, presión=0, temperatura>crítico, vibración>crítico, current=0, tank=0 |
| blocked_discharge | Caudal=0, presión>crítico, temperatura>crítico, vibración>crítico, current>crítico |
| pipe_burst | Caudal>crítico, presión=0, vibración>crítico, temperature>crítico |
| cavitation | Caudal errático, vibración>crítico, presión 0-0.5 |
| overheat | Temperatura>crítico, vibración>crítico, current>crítico, caudal=0 |
| power_surge | Voltaje>crítico, current>crítico, temperatura>crítico, vibración>crítico |
| power_outage | Todos los valores a cero / temperatura ambiente |
| bearing_failure | Vibración>crítico, temperatura>crítico, calidad de agua>crítico |

**Tasas de ramping** (unidades por tick):
- flow_rate: 3.0, pressure: 1.5, temperature: 8.0, vibration: 2.0
- current: 4.0, voltage: 30.0, tank_level: 5.0, water_quality: 30.0

### physics/elevator.py

**Modelo físico de elevador** (909 líneas):

**Máquina de estados finitos (FSM)**:

```
IDLE → DOOR_OPENING → DOORS_OPEN → DOOR_CLOSING → ACCELERATING → MOVING → DECELERATING → DOOR_OPENING → ...
```

**Estados**:

1. **IDLE**: Elevador detenido, puerta cerrada. Espera 2-5 segundos, elige piso aleatorio
2. **DOOR_OPENING**: Puerta abriéndose (2 segundos)
3. **DOORS_OPEN**: Puerta abierta, espera pasajeros (8 ticks)
   - Si carga > umbral crítico → no cierra puerta (sobrecarga)
   - Cambia carga aleatoriamente ±150 kg
4. **DOOR_CLOSING**: Puerta cerrándose (2 segundos)
   - Si sobrecarga o puerta obstruida → vuelve a DOORS_OPEN
   - Si no está en piso destino → ACCELERATING
5. **ACCELERATING**: Curva S de aceleración (jerk-limited)
   - Si motor_torque_factor ≤ 0 → MOVING con speed=0
6. **MOVING**: Crucero a velocidad constante
   - Cálculo de distancia de frenado: d = v²/(2a) + 0.5
   - Si gobernador falló → overspeed (acelera sin control)
   - Si brake failed → no frena
7. **DECELERATING**: Curva S de desaceleración
   - Cuando speed ≤ 0.05 → DOOR_OPENING

**Modelos físicos**:
- **Posición**: Integración de velocidad con dt
- **Carga**: Random walk con efecto de falla overload
- **Temperatura del motor**: Modelo térmico con carga, velocidad, y estado
- **Corriente del motor**: Modelo basado en:
  - Fuerza de gravedad por desbalance (cabina vs contrapeso)
  - Fuerza inercial durante aceleración
  - Potencia mecánica = Fuerza × velocidad
  - Potencia eléctrica = P_mecánica / eficiencia
  - Corriente = corriente base + corriente por potencia
  - Factor inrush durante arranque (1.5× primer medio segundo)
- **Vibración**: Función de velocidad y estado
- **Voltaje**: 380V nominal, cae durante aceleración (-12V)

**Fallas de elevador**:

| Falla | Parámetros | Efecto |
|-------|------------|--------|
| motor_stuck | torque_factor=0 | No acelera, rotor bloqueado |
| door_blocked | door_obstructed=True | Puerta no cierra |
| overspeed | governor_failed=True, brake_failed=True | Velocidad sin control |
| overload | overload_extra_kg=900 | Carga excede límite |
| pos_sensor_fail | pos_sensor_stuck=True | Posición congelada, emergencia ≤1 tick |
| commercial_power_outage | power_available=False | Freno emergencia → espera → rescate batería |
| traction_loss | traction_loss=True | Posición no avanza (10%), vibración alta |

**Power Outage FSM**:
```
PERÍODO < 0.1s:  Freno emergencia (speed→0)
0.1s < t < 3.0s: Espera (IDLE)
t > 3.0s:        Rescate por batería (0.3 m/s al piso más cercano)
                  → puerta se abre → completado
```

### engine.py

**Motor principal de simulación** (332 líneas):

```python
generate_data_and_emit()  # Loop infinito en greenlet
```

Por cada tick (SIM_TICK_INTERVAL = 1s):

```python
for sim in simulators.values():
    _run_sim_tick(sim)  # Por cada simulador
```

**`_run_sim_tick(sim)`**:
1. Si pausado → return
2. `update_sensor_data(sim)` → física (pump/elevator)
3. `_process_sensor_alerts(sim, alert_vars)`:
   - Obtiene umbrales de BD
   - Clasifica riesgo de cada variable
   - Si hay fallas activas → `_send_compound_alerts_for_faults()`
4. `_check_auto_faults(sim)`: Cada ~5 ticks, inyecta falla aleatoria si está habilitado
5. `_check_auto_protection(sim)`: Si protección activa y falla estable por 5 ticks → apaga equipo
6. `_build_history_records(sim)`: Persiste lecturas cada 30 ticks, limpia registros >8 días

**Backoff exponencial**:
- Si un simulador lanza excepción → backoff: 2^fallos (máx 30 ticks)

### payload_service.py

Construye el payload JSON para el frontend:

```python
build_live_payload(ctx: PayloadContext) -> dict
```

Payload incluye:
- `current`: Valores actuales de sensores (solo variables relevantes)
- `risk`: Nivel de riesgo por variable con badge CSS
- `history`: Últimos 200 registros
- `thresholds`: Umbrales configurados
- `alert_log`: Alertas de BD (cacheadas 3s)
- `stats`: Estadísticas (avg, min, max, std) por variable
- Estado de equipos (pump_on, elevator_on, sim faults, etc.)

Sincroniza estado de equipos con BD cada 5s (`_maybe_sync_equipment_status`):
- Si hay falla activa → status = "falla"
- Si no → status = "operativo"

---

## 5.5 apps/authentication

**Propósito**: Login, logout y completación de registro.

### views.py (212 líneas)

#### login_view
- **GET**: Muestra formulario de login
- **POST**: Valida credenciales
- **Rate limiting**: 5 intentos/minuto por IP (cache de memoria)
- Verifica contraseña con `check_password()` de Django
- Establece sesión con: usuario_id, usuario_rol, usuario_es_admin, usuario_nombre_completo

#### logout_view
- Hace `request.session.flush()`
- Redirige a login

#### complete_registration_view
- **GET**: Muestra formulario con token
- **POST**: Valida username (letras y números, 4-20 chars) y password (mín 8 chars, letras+números)
- Verifica token firmado con `TOKEN_MAX_AGE` (24h)
- Guarda username y password hasheada
- Marca usuario como registered=True

### Funciones auxiliares:
- `_setup_session()`: Configura sesión post-login
- `_resolve_registration_token()`: Verifica token firmado de Django
- `_validate_login_fields()`: Validación básica
- `_validate_registration_form()`: Validación completa de registro

---

## 5.6 apps/dashboard

**Propósito**: Dashboard principal con monitoreo en tiempo real.

### views.py
```python
monitoring_view(request)
```
- Carga edificios según rol (admin→todos, user→asignados)
- Determina building_id desde parámetro GET
- Renderiza `monitoring_dashboard.html` con:
  - Lista de edificios
  - Config JSON para JS
  - Opciones de falla para inyección

### shared.py
- `build_monitoring_config()`: Construye config JSON con nombres, unidades, rangos, umbrales
- `get_user_building_ids()`: IDs de edificios asignados a un usuario

### simulation/streaming.py
**SSE Stream** (ver sección 13)

### simulation/api.py
```python
api_status(request)  # GET /api/status/?edificio_id=X
```
Retorna payload completo vía `build_live_payload_for_sim()`

### simulation/controls.py
Endpoints de control (todos POST, requieren admin):

| Endpoint | Función | Descripción |
|----------|---------|-------------|
| `/api/sim/<id>/status/` | sim_status | Estado del simulador |
| `/api/sim/<id>/pause/` | sim_pause | Pausar/reanudar |
| `/api/sim/<id>/reset/` | sim_reset | Reiniciar a estado seguro |
| `/api/sim/<id>/inject-fault/` | sim_inject_fault | Inyectar falla |
| `/api/sim/<id>/clear-fault/` | sim_clear_fault | Limpiar falla |
| `/api/sim/<id>/set-speed/` | sim_set_speed | Velocidad (0.1-10) |
| `/api/sim/<id>/toggle-pump/` | sim_toggle_pump | Encender/apagar bomba |
| `/api/sim/<id>/toggle-elevator/` | sim_toggle_elevator | Encender/apagar elevador |
| `/api/sim/<id>/toggle-protection/` | sim_toggle_protection | Protección automática |
| `/api/sim/<id>/toggle-auto-faults/` | sim_toggle_auto_faults | Fallas automáticas |

### simulation/shared.py
- `get_simulator(building_id)`: Obtiene o crea simulador dinámicamente
- `_sync_equipment_from_db()`: Sincroniza equipos cada 60s
- `get_first_simulator()`: Primer simulador disponible
- `parse_json_body()`: Parseo seguro de JSON

---

## 5.7 apps/history

**Propósito**: Historial de eventos, alertas compuestas, notificaciones por correo.

### Modelos

#### History (`historial`)

| Campo | Tipo | BD |
|-------|------|-----|
| id | AutoField (PK) | `id_historial` |
| user | ForeignKey→Usuario (nullable) | `id_usuario` |
| monitoring_equipment | ForeignKey→MonitoringEquipment (nullable) | `id_equipo_monitoreo` |
| date | DateTimeField | `fecha` (db_index) |
| message | JSONField | `mensaje` |
| resolved | BooleanField | `resuelto` |
| fault_type | CharField(50) nullable | `tipo_falla` |
| affected_variables | JSONField (list) | `variables_afectadas` |

#### UserDismissedHistory (`historial_descartado`)

| Campo | Tipo | BD |
|-------|------|-----|
| user | ForeignKey→Usuario | `id_usuario` |
| history_record | ForeignKey→History | `id_historial` |
| dismissed_at | DateTimeField (auto_now_add) | `descartado_en` |

Restricción: UniqueConstraint(user, history_record)

### context_processors.py

```python
unread_history_count(request)  # → {"unread_history_count": N}
```
Disponible en TODOS los templates. Cacheado 2s.

### views.py (423 líneas)

| Vista | Ruta | Descripción |
|-------|------|-------------|
| `history_view` | `/history/` | Lista paginada con filtros |
| `view_unread_count` | `/history/api/count/` | Contador JSON |
| `sse_unread_count_stream` | (stream propio) | SSE de conteo |
| `clear_history_view` | `/history/clear/` | Descartar registros |
| `resolve_alert_view` | `/history/<id>/resolve/` | Resolver alerta |
| `history_pdf_view` | `/history/pdf/` | Exportar PDF |

**history_view** soporta filtros:
- `?edificio=X` - Por edificio
- `?severidad=Alto` - Por severidad
- `?variable=...` - Por variable
- `?periodo=reciente|antiguo|custom` - Por período
- `?fecha_desde=&fecha_hasta=` - Rango personalizado

### shared.py (213 líneas)

- `_build_history_query()`: Query base con permisos por rol, excluye descartados
- `parse_history()`: Convierte records a formato con parsed_data
- `parse_history_record_for_display()`: Parsea mensaje JSON individual
- `filter_date_range()`: Filtro por fechas
- `extract_variables()`: Variables únicas en resultados
- `extract_severities()`: Severidades únicas presentes

### alerts/engine.py

**Motor de alertas compuestas**:

```python
send_compound_alert(fault_type, affected_vars, risk_level, sim)
```

Flujo:
1. Traduce valores a español (VALUE_DISPLAY_ES)
2. Obtiene nombre de falla (FAULT_NAMES_ES)
3. Obtiene texto de alerta (FAULT_ALERT_MESSAGES)
4. Envía correo HTML con `_send_compound_email()` (asíncrono, eventlet.spawn)
5. Agrega payload a `sim.pending_alerts` (para SSE)
6. Persiste en BD con `save_compound_history_record()`

### services/email_templates.py

Generación de HTML para correos:

- **`_build_email_shell(inner_html)`**: Estructura base del correo:
  - Header con logo INES y barra azul
  - Contenido central
  - Footer automático

- **`build_activation_email_html(link)`**: Correo de activación de cuenta
  - Botón "Activar cuenta" con diseño border-box
  - Información de seguridad (24h validez)

- **`build_compound_alert_email_html(fault_name, risk_level, affected_vars, action)`**: 
  - Banner con color según severidad
  - Tabla de variables afectadas
  - Caja de acción correctiva

- **`build_report_email_html(edificio, contexto)`**: Correo de reporte
  - Notificación de PDF adjunto

**Diseño del correo**:
- Fuente: DM Sans (Google Fonts)
- Colores: acento azul (#2563eb), fondo gris (#f5f5f5)
- Estilo: border-box con sombra, bordes gruesos negros
- Totalmente responsivo (tablas anidadas)

### services/email_recipients.py

```python
get_building_emails(edificio_id)  # → List[str]
```
Obtiene correos de usuarios registrados (excluye admins) asignados a un edificio.

### services/email_sender.py

- `send_email_raw()`: Envío directo con HTML opcional y PDF adjunto
- `_send_email_smtp()`: Envío con construcción de HTML automática
- `send_email_alert()`: Envío con configuración completa

### services/email_config.py
- `EmailAttachment`: Wrapper para PDF
- `EmailConfig`: Configuración completa de envío

### services/history_persistence.py

```python
get_alert_log(edificio_id, limit)  # Últimas N alertas de BD
save_compound_history_record(fault_type, affected_vars, risk_level, action, edificio_id)
```

- `_find_equipment_by_fault()`: Encuentra equipo de monitoreo según tipo de falla

---

## 5.8 apps/thresholds

**Propósito**: Configuración de umbrales de riesgo por edificio.

### Modelo ThresholdConfig (`umbral_config`)

| Campo | Tipo | BD |
|-------|------|-----|
| building | ForeignKey→Building | `id_edificio` |
| variable | CharField(50) | `variable` |
| direction | CharField(10) | `direction` (higher/lower/range) |
| high | FloatField | `high` |
| critic | FloatField | `critic` |
| crit_low | FloatField nullable | `crit_low` |
| crit_high | FloatField nullable | `crit_high` |
| created_at | DateTimeField (auto_now_add) | |
| updated_at | DateTimeField (auto_now) | |

Unique: (building, variable)

### services.py

```python
get_thresholds(building_id)  # DEFAULT_THRESHOLDS + overrides de BD
update_threshold(variable, config, building_id)
bulk_update(thresholds_dict, building_id)
```

### views.py

- `render_admin_thresholds()`: Página de administración de umbrales
- `view_get_thresholds()`: API GET → JSON con umbrales
- `view_update_thresholds()`: API POST → actualiza umbrales

**Validación** de umbrales:
- Dirección válida: higher, lower, range
- Valores numéricos (no NaN/Inf)
- Máx 10 dígitos enteros, 4 decimales
- Para "range": high < critic
- Para "higher": high < critic
- Para "lower": high > critic
- Dentro de límites físicos del sensor

---

## 5.9 apps/limits

**Propósito**: Configuración de límites físicos máximos de sensores.

### Modelo SensorLimitConfig (`limite_sensor_config`)

| Campo | Tipo | BD |
|-------|------|-----|
| building | ForeignKey→Building | `id_edificio` |
| variable | CharField(50) | `variable` |
| max_value | FloatField | `max_value` |
| created_at | DateTimeField (auto_now_add) | |
| updated_at | DateTimeField (auto_now) | |

Unique: (building, variable)

### services.py

```python
get_sensor_limits(building_id)  # SENSOR_RANGES + overrides de BD
_update_sensor_limit(variable, max_value, building_id)
bulk_update_limits(limits_dict, building_id)
```

Al actualizar límite, llama a `simulator.refresh_limits()` para actualizar en memoria.

### views.py

- `render_admin_limits()`: Página de administración de límites
- `view_get_sensor_limits()`: API GET → límites
- `view_update_sensor_limits()`: API POST → actualiza límites

**Validación**:
- Máx 10 dígitos enteros, 4 decimales
- No exceder límite absoluto (SENSOR_ABSOLUTE_RANGES)
- Debe ser mayor que mínimo por defecto
- No puede ser inferior al umbral crítico/alto correspondiente

---

## 5.10 apps/settings

**Propósito**: Configuración de perfil de usuario.

### views.py (210 líneas)

#### configuration_view
- **GET**: Muestra formulario con datos actuales
- **POST**: Maneja dos acciones:

1. **update_profile**: Cambiar email y/o username
   - Requiere contraseña actual
   - Valida email único, username único
   
2. **change_password**: Cambiar contraseña
   - Requiere contraseña actual
   - Nueva contraseña: 8-128 chars, letras y números
   - Confirmación debe coincidir

---

## 6. MODELO DE BASE DE DATOS

### Diagrama de Tablas

```
┌──────────────────┐     ┌─────────────────────┐
│     persona      │     │      usuario        │
├──────────────────┤     ├─────────────────────┤
│ id_persona (PK)  │◄────│ id_persona (FK)     │
│ ci (UQ)          │     │ id_usuario (PK)     │
│ primer_nombre    │     │ username (UQ)       │
│ segundo_nombre   │     │ password            │
│ primer_apellido  │     │ rol (US/SA)         │
│ segundo_apellido │     │ registrado          │
│ email (UQ)       │     └─────────┬───────────┘
└──────────────────┘               │
                                   │
┌──────────────────────┐    ┌──────┴──────────┐
│  usuario_edificio    │    │  historial       │
├──────────────────────┤    ├──────────────────┤
│ id_asignacion (PK)   │    │ id_historial (PK)│
│ id_usuario (FK) ◄────┘    │ id_usuario (FK)◄┘
│ id_edificio (FK) ──┐      │ id_equipo (FK)  │
│ UQ(usuario,edificio)│     │ fecha (idx)      │
└─────────────────────┘     │ mensaje (JSON)   │
                            │ resuelto         │
┌──────────────────────┐    │ tipo_falla       │
│      edificio        │    │ variables_afect. │
├──────────────────────┤    └──────────────────┘
│ id_edificio (PK)     │
│ nb_edificio          │    ┌────────────────────────┐
│ rif (UQ)             │    │ historial_descartado    │
│ direccion            │    ├────────────────────────┤
│ cantidad_pisos       │    │ id_usuario (FK)        │
└──────────┬───────────┘    │ id_historial (FK)      │
           │                │ descartado_en          │
           │                │ UQ(usuario,histor)     │
┌──────────┴───────────┐    └────────────────────────┘
│  equipo_monitoreo    │
├──────────────────────┤    ┌────────────────────────┐
│ id_equipo (PK)       │    │   umbral_config        │
│ id_edificio (FK)     │    ├────────────────────────┤
│ nb_equipo            │    │ id_edificio (FK)       │
│ tipo (bomba/elevad.) │    │ variable               │
│ status               │    │ direction              │
│ UQ(edif, tipo)       │    │ high                   │
└──────────────────────┘    │ critic                 │
                            │ UQ(edificio,variable)  │
┌────────────────────────┐  └────────────────────────┘
│   limite_sensor_config │
├────────────────────────┤  ┌────────────────────────┐
│ id_edificio (FK)       │  │   lectura_sensor       │
│ variable               │  ├────────────────────────┤
│ max_value              │  │ id_edificio (FK)       │
│ UQ(edificio,variable)  │  │ variable               │
└────────────────────────┘  │ valor                  │
                            │ riesgo                 │
                            │ fecha (idx)            │
                            │ INDEX(build,var,date)  │
                            └────────────────────────┘
```

### Resumen de Tablas

| Tabla | PK | FKs | Únicos |
|-------|----|------|--------|
| persona | id_persona | - | ci, email |
| usuario | id_usuario | id_persona | username |
| edificio | id_edificio | - | rif |
| equipo_monitoreo | id_equipo | id_edificio | (edificio, tipo) |
| usuario_edificio | id_asignacion | id_usuario, id_edificio | (usuario, edificio) |
| historial | id_historial | id_usuario, id_equipo | - |
| historial_descartado | - | id_usuario, id_historial | (usuario, historial) |
| umbral_config | - | id_edificio | (edificio, variable) |
| limite_sensor_config | - | id_edificio | (edificio, variable) |
| lectura_sensor | - | id_edificio | - |

---

## 7. SISTEMA DE AUTENTICACIÓN

**Tipo**: Autenticación por sesión (NO JWT, NO Django Auth nativo)

### Flujo de login:
1. Usuario envía POST a `/login/` con username y password
2. Se verifica rate limit (5 intentos/min por IP)
3. Se busca usuario por username
4. Se verifica password con `check_password()` (Django hashers)
5. Si ok: se establecen variables de sesión:
   - `usuario_id`, `usuario_rol`, `usuario_es_admin`, `usuario_nombre_completo`
6. Si fail: incrementa contador de intentos (expira en 60s)

### Decoradores:
- **`@login_required`**: Verifica `usuario_id` en sesión
- **`@admin_required`**: Verifica rol "SA"

### Middleware (AuthMiddleware):
Se ejecuta en cada request:
1. Define rutas públicas
2. Si no autenticado y no pública → redirect a login
3. Si autenticado y va a login → redirect a monitor
4. Verifica que el usuario exista en BD
5. Si va a ruta admin → verifica rol SA
6. Agrega headers anti-caché

### Registro:
1. Admin crea usuario con datos personales
2. Sistema genera username aleatorio y contraseña temporal
3. Se envía correo con token firmado (válido 24h)
4. Usuario completa registro: establece username y password
5. Usuario queda como `registered=True`

---

## 8. MOTOR DE SIMULACIÓN DE SENSORES

### Arquitectura

```
server.py / manage.py
    │
    ▼
eventlet.spawn(_engine_watchdog)
    │
    ▼
generate_data_and_emit()  ← Loop infinito
    │
    └── por cada tick (1s):
        └── por cada BuildingSimulator:
            ├── update_sensor_data() → physics/pump.py o physics/elevator.py
            ├── _process_sensor_alerts()
            ├── _check_auto_faults()
            ├── _check_auto_protection()
            └── _build_history_records()
```

### Características clave:
1. **In-memory**: Los valores de sensores viven en RAM (dict `simulators`)
2. **Física realista**: Modelos termodinámicos, eléctricos y mecánicos
3. **Transiciones progresivas**: Las fallas rampean gradualmente (no cambian instantáneamente)
4. **Fallas compuestas**: Una falla afecta múltiples variables simultáneamente
5. **Auto-recuperación**: Al limpiar falla, valores vuelven gradualmente a la normalidad
6. **Concurrencia**: Todo corre en greenlets de eventlet (cooperativo)
7. **Watchdog**: Si el loop de simulación falla, se reinicia automáticamente

### Velocidad de simulación:
- `sim_speed`: factor multiplicador (0.1x a 10x)
- Afecta la magnitud de los cambios por tick
- Controlable desde UI (admin)

---

## 9. SISTEMA DE CLASIFICACIÓN DE RIESGO

### Función: `classify_risk(variable, value, thresholds)`

**Modo "higher"** (mayor es peor):
```
Normal:  value ≤ high
Alto:    high < value ≤ critic
Crítico: value > critic
```

**Modo "lower"** (menor es peor):
```
Normal:  value ≥ high
Alto:    critic ≤ value < high
Crítico: value < critic
```

**Modo "range"** (rango seguro):
```
margin = (critic - high) * 0.20
Normal:  high + margin ≤ value ≤ critic - margin    (banda central 60%)
Alto:    fuera de banda central pero dentro de [high, critic]  (bandas 20% cada una)
Crítico: value < high o value > critic
```

**Sensores de enumeración** (elev_door_status): Siempre retornan Normal.

**Sin umbrales**: Retorna Normal.

---

## 10. SISTEMA DE ALERTAS Y CORREO

### Flujo de alerta compuesta:

```
Falla inyectada (simulador)
    │
    ▼
Variables rampean a valores anómalos
    │
    ▼
engine.py: _process_sensor_alerts()
    │
    ├── Clasifica riesgo de cada variable
    │
    ▼
_send_compound_alerts_for_faults()
    │
    ├── Espera transición "stable" (rampa completada)
    ├── Debounce: 3 ticks antes de enviar
    │
    ▼
send_compound_alert()  ← alerts/engine.py
    │
    ├── Traduce valores a español
    ├── Envía correo HTML (eventlet.spawn asíncrono)
    ├── Agrega payload a pending_alerts (para SSE)
    └── Persiste en BD (history)
```

### Protección automática:

Si `protection_on = True` y hay falla estable por 5 ticks:
1. Se registra evento de protección en historial
2. Se apaga el equipo (pump_on = False o elevator_on = False)
3. Se limpia la falla
4. Se muestra alerta "Resuelta" en la UI

### Tipos de correo:
1. **Alerta compuesta**: Cuando se detecta falla con múltiples sensores afectados
2. **Activación de cuenta**: Token firmado para completar registro
3. **Reporte de monitoreo**: PDF adjunto con estado actual

### Formato HTML de correos:
- Diseño profesional con DM Sans
- Banner coloreado según severidad
- Tabla de variables afectadas
- Caja de acción correctiva
- Totalmente responsivo (tablas anidadas)

---

## 11. SISTEMA DE REPORTES PDF

### Biblioteca: fpdf2

### Funcionalidades:
1. **Reporte de edificio**: Estado completo con resumen, equipos, lecturas, estadísticas
2. **Reporte de usuarios**: Lista de usuarios agrupados por edificio
3. **Reporte de historial**: Eventos filtrados con agrupación por edificio

### Características del PDF:
- Logo INES con barra de acento azul
- Header/footer automáticos con número de página
- Tablas con zebra striping
- Colores por nivel de riesgo
- Saltos de página automáticos
- Fuente DejaVu Sans (con fallback a Arial/Helvetica)
- Soporte de acentos (conversión a ASCII si no hay fuente Unicode)

---

## 12. FRONTEND Y UI

### HTML Templates

**Base templates**:
- `base_sidebar.html`: Layout principal con sidebar, topbar móvil, contenido
- `base_public.html`: Layout público (login)
- `_list_base.html`: Base para listas (usuarios, edificios)
- `_config_base.html`: Base para configuraciones (umbrales, límites)

**Componentes**:
- `sidebar.html`: Sidebar de navegación
- `navbar.html`: Barra de navegación pública
- `button.html`: Componente botón
- `history_item.html`: Item de historial
- `pagination.html`: Paginación
- `toast_messages.html`: Notificaciones toast
- `empty_state.html`: Estado vacío

**Templates por app**: Cada app tiene sus propios templates en `templates/<app>/`

### CSS (`styles.css`)

~2800 líneas de CSS vanilla con:
- Sistema de diseño basado en propiedades CSS (colores, espaciado, tipografía)
- Layout responsive (mobile-first)
- Grid de tarjetas de sensores
- Sidebar colapsable en móvil
- Paneles de filtro (slide-in)
- Notificaciones toast
- Estados de carga, offline y vacío
- Tablas con diseño limpio
- Formularios con feedback visual
- Tema oscuro para tablas
- Animaciones y transiciones

### JavaScript

**shared.js**: Librería de utilidades compartidas:
- `CustomSelect`: Select personalizado con diseño propio
- Selector de edificios
- Renderizado de tarjetas de sensores
- Cliente SSE con auto-reconexión (exponential backoff)
- Helpers para Chart.js
- Paneles de filtro y modal
- `showConfirm()`: Modal de confirmación reutilizable
- `showToast()`: Notificaciones toast
- `csrfFetch()`: Fetch con token CSRF automático
- `hideAllStates()`: Ocultar estados de UI

**forms.js**: Validación de formularios:
- Validación en tiempo real mientras el usuario escribe
- Validación al enviar
- Feedback visual con clases CSS

**monitoring.js**: Dashboard en tiempo real:
- Actualización de gráficos ApexCharts
- Manejo de eventos SSE
- Actualización de tarjetas de sensores
- Estados de UI

**script.js**: Inicializador:
- `App*Init()` y `App*SetupEvents()` por página
- Dispatcher que llama a la función correcta según la página

**thresholds.js**: UI de configuración de umbrales
**limits.js**: UI de configuración de límites

---

## 13. STREAMING SSE EN TIEMPO REAL

### Tecnología: Server-Sent Events (SSE)

### Endpoint: `GET /sse/<building_id>/`

### Flujo:

```
Cliente abre conexión SSE
    │
    ▼
django.http.StreamingHttpResponse (text/event-stream)
    │
    ▼
event_stream()  ← Greenlet
    │
    ├── Cada SIM_TICK_INTERVAL (1s):
    │   ├── build_live_payload_for_sim(sim) → payload JSON
    │   └── yield "data: {payload}\n\n"
    │
    ├── Inmediatamente:
    │   ├── Lee pending_alerts del AlertDispatcher
    │   └── yield "event: history-event\ndata: {alert}\n\n"
    │
    └── Cuando cambia el conteo:
        └── yield "event: count-update\ndata: {'count': N}\n\n"
```

### Reconexión:
- El cliente SSE en JS reconecta automáticamente
- Implementa exponential backoff en caso de fallos

### Canales de comunicación:
1. **`data:`**: Payload de telemetría (cada tick)
2. **`event: history-event`**: Alertas nuevas (inmediato)
3. **`event: count-update`**: Actualización de conteo no leído

---

## 14. SCRIPT DE POBLACIÓN DE BD

### `scripts/populate_db.py`

Ejecuta: `python scripts/populate_db.py`

### Qué hace:
1. **TRUNCATE** de todas las tablas con RESTART IDENTITY CASCADE
2. Crea 20 personas con datos venezolanos realistas
3. Crea 1 admin (V-99999999, admin@sistema.com, username: "admin", pass: "password123")
4. Crea 20 usuarios (user0-user19, pass: "password123")
5. Crea 20 edificios con nombres y direcciones realistas (5-30 pisos)
6. Asigna 1-3 edificios por usuario aleatoriamente
7. Vincula admin a todos los edificios
8. Crea bomba de agua para cada edificio
9. 60% de edificios tienen elevador
10. Siembra umbrales por defecto para cada edificio
11. Siembra límites de sensores para cada edificio
12. Genera 7 días de lecturas históricas (6 lecturas/día)

---

## 15. RUTAS COMPLETAS (URLS)

### apps/authentication
| Ruta | Vista | Nombre |
|------|-------|--------|
| `/login/` | login_view | login |
| `/logout/` | logout_view | logout |
| `/complete-registration/` | complete_registration_view | complete_registration |

### apps/dashboard
| Ruta | Vista | Nombre |
|------|-------|--------|
| `/` | RedirectView | home |
| `/monitor/` | monitoring_view | monitor |
| `/sse/` | sse_stream | sse_stream_global |
| `/sse/<int:building_id>/` | sse_stream | sse_stream |
| `/api/status/` | api_status | api_status |
| `/api/sim/<int:building_id>/status/` | sim_status | api_sim_status |
| `/api/sim/<int:building_id>/pause/` | sim_pause | api_sim_pause |
| `/api/sim/<int:building_id>/reset/` | sim_reset | api_sim_reset |
| `/api/sim/<int:building_id>/inject-fault/` | sim_inject_fault | api_sim_inject_fault |
| `/api/sim/<int:building_id>/clear-fault/` | sim_clear_fault | api_sim_clear_fault |
| `/api/sim/<int:building_id>/set-speed/` | sim_set_speed | api_sim_set_speed |
| `/api/sim/<int:building_id>/toggle-pump/` | sim_toggle_pump | api_sim_toggle_pump |
| `/api/sim/<int:building_id>/toggle-elevator/` | sim_toggle_elevator | api_sim_toggle_elevator |
| `/api/sim/<int:building_id>/toggle-protection/` | sim_toggle_protection | api_sim_toggle_protection |
| `/api/sim/<int:building_id>/toggle-auto-faults/` | sim_toggle_auto_faults | api_sim_toggle_auto_faults |

### apps/users
| Ruta | Vista | Nombre |
|------|-------|--------|
| `/users/` | user_list_view | user_list |
| `/users/create/` | user_create_view | user_create |
| `/users/<int:user_id>/edit/` | user_update_view | user_edit |
| `/users/<int:user_id>/delete/` | user_delete_view | user_delete |
| `/api/check-cedula/` | check_cedula_uniqueness_view | check_cedula |
| `/api/send-test-email/` | send_test_email | send_test_email |
| `/api/send-all-subscribers/` | send_all_subscribers | send_all_subscribers |
| `/usuarios/pdf/` | user_pdf_view | user_pdf |
| `/api/users/<int:user_id>/link-building/` | user_link_building_view | user_link_building |
| `/api/users/<int:user_id>/unlink-building/` | user_unlink_building_view | user_unlink_building |

### apps/buildings
| Ruta | Vista | Nombre |
|------|-------|--------|
| `/buildings/create/` | register_building_view | register_building |
| `/buildings/` | building_list_view | building_list |
| `/buildings/<int:building_id>/edit/` | edit_building_view | edit_building |
| `/buildings/<int:building_id>/delete/` | delete_building_view | delete_building |
| `/api/check-rif/` | check_rif_uniqueness_view | check_rif |
| `/buildings/<int:edificio_id>/report/pdf/` | building_report_pdf_view | building_report_pdf |

### apps/history
| Ruta | Vista | Nombre |
|------|-------|--------|
| `/history/` | history_view | history |
| `/history/clear/` | clear_history_view | clear_history |
| `/history/api/count/` | view_unread_count | api_unread_count |
| `/history/<int:record_id>/resolve/` | resolve_alert_view | resolve_alert |
| `/history/pdf/` | history_pdf_view | history_pdf |

### apps/thresholds
| Ruta | Vista | Nombre |
|------|-------|--------|
| `/thresholds/` | render_admin_thresholds | thresholds |
| `/api/thresholds/` | view_get_thresholds | api_thresholds |
| `/api/thresholds/update/` | view_update_thresholds | api_thresholds_update |

### apps/limits
| Ruta | Vista | Nombre |
|------|-------|--------|
| `/limits/` | render_admin_limits | sensor_limits |
| `/api/sensor-limits/` | view_get_sensor_limits | api_sensor_limits |
| `/api/sensor-limits/update/` | view_update_sensor_limits | api_sensor_limits_update |

### apps/settings
| Ruta | Vista | Nombre |
|------|-------|--------|
| `/settings/` | configuration_view | configuration |

### apps/sensors
| Ruta | Vista | Nombre |
|------|-------|--------|
| `/api/sensors/daily/<int:building_id>/` | daily_summary | daily_summary |

---

## 16. DIAGRAMA DE FLUJO DE DATOS

```
USUARIO (Admin)                          USUARIO (Regular)
    │                                          │
    ├── CRUD Edificios                        │
    ├── CRUD Usuarios                         │
    ├── Configurar Umbrales                   │
    ├── Configurar Límites                    │
    ├── Inyectar Fallas                       │
    ├── Controlar Simulación                  │
    └── Ver Dashboard ───────────┬────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  Dashboard SSE  │
                        │  (Tiempo Real)  │
                        └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
            ┌──────────┐ ┌──────────┐ ┌──────────┐
            │  Últimas │ │ Historial│ │Alertas   │
            │ Lecturas │ │ Eventos  │ │ Compuestas│
            └──────────┘ └──────────┘ └──────────┘

                    SIMULACIÓN (Greenlet Loop)
                    ┌────────────────────────────────┐
                    │  Cada tick (1s):                │
                    │  1. Física Bomba/Elevador       │
                    │  2. Clasificar Riesgo           │
                    │  3. Detectar Fallas             │
                    │  4. Enviar Alertas (email)      │
                    │  5. Persistir en BD             │
                    └────────────────────────────────┘
```

---

## 17. CONSIDERACIONES DE SEGURIDAD

### Implementadas:
1. **Contraseñas hasheadas** con Django `make_password()` (PBKDF2)
2. **CSRF Protection** con tokens en formularios y headers en fetch
3. **Sesiones HTTPOnly** con SameSite Lax
4. **Rate limiting** en login (5 intentos/min por IP)
5. **Middleware de autenticación** que verifica sesión en cada request
6. **Decoradores** `@login_required` y `@admin_required`
7. **Tokens firmados** para registro (Django signing, 24h expiración)
8. **Headers de seguridad**: X-Frame-Options, Content-Type nosniff, XSS filter
9. **Cookies seguras** en producción (HTTPS-only)
10. **Validación de formularios** tanto client-side como server-side
11. **Expiración de sesión** al cerrar navegador
12. **Headers anti-caché** en páginas autenticadas

### Recomendadas para producción:
1. Usar HTTPS con certificado válido
2. Configurar `DJANGO_DEBUG=false`
3. Usar `DJANGO_ALLOWED_HOSTS` restrictivo
4. No commitear `.env` con credenciales reales
5. Usar app password de Gmail (no contraseña real)
6. Considerar migrar a autenticación JWT para APIs
7. Agregar logging de seguridad (intentos fallidos)
8. Considerar PostgreSQL connection pooling (PGBouncer)

---

*Documentación generada para defensa de tesis. INES - Sistema Inteligente de Monitoreo.*
*Última actualización: Julio 2026*
