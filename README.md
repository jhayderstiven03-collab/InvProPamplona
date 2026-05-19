# InvPro · Sistema de Inventario
## Universidad de Pamplona
> Sistema de gestion de inventario desarrollado con
> Django + FastAPI + PostgreSQL + Tailwind CSS.
## Stack tecnologico
| Capa        | Tecnologia                     |
|-------------|--------------------------------|
| Frontend    | Tailwind CSS + HTML + JS       |
| Backend API | FastAPI + Swagger UI           |
| Framework   | Django + SimpleJWT             |
| Base datos  | PostgreSQL (Render managed)    |
| Despliegue  | Render                         |
| IDE         | Cursor                         

## Instalacion local
### Requisitos previos- Python 3.11+- Node.js 18+- PostgreSQL 15+
### Pasos
```bash
git clone https://github.com/[usuario]/invpro-unipamplona.git
cd invpro-unipamplona
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Editar con tus credenciales
python manage.py migrate
python manage.py tailwind install
uvicorn config.asgi:application --reload --port 8000
```
### Variables de entorno (.env)
```
SECRET_KEY=tu-clave-secreta
DEBUG=True
DB_NAME=invpro_db
DB_USER=postgres
DB_PASSWORD=tu-password
DB_HOST=localhost
DB_PORT=5432

## Estructura del proyecto
```
invpro-unipamplona/
 config/          # Settings Django
 apps/
 accounts/   # Auth + roles
 inventory/  # Productos + categorias
 movements/  # Entradas y salidas
 api/             # Endpoints FastAPI
 templates/       # HTML Tailwind
 static/          # CSS compilado + JS
 requirements.txt
```
## Equipo de desarrollo
| Persona | Rol                        |
|---------|----------------------------|
| A       | Backend Lead + DevOps      |
| B       | Auth + Seguridad           |
| C       | Modelos + CRUD Backend     |
| D       | Frontend + Vistas          |
| E       | Docs + Integracion + Dash  |
