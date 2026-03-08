MoveON - Aplicación deportiva para guardar rutas de movimiento andando o corriendo.

Backend desarrollado en Python con FastAPI y Base de Datos PostgreSQL.


🚀 Guía para Colaboradores

1. Clonar el repositorio. Abre una terminal en tu carpeta de proyectos y ejecuta: git clone https://github.com/Galen222/MoveOn-Backend.git y después cd MoveOn-Backend

2. Backend (Visual Studio Code):

   2.1 Abre Visual Studio Code. Selecciona Archivo > Abrir Carpeta... y elige la carpeta MoveOn-Backend

   2.2 Crear Entorno Virtual: Abre la terminal de VS Code y ejecuta: python -m venv venv

   2.3 Activar Entorno:

      Windows: .\venv\Scripts\activate

      Mac/Linux: source venv/bin/activate

      Instalar Dependencias: pip install -r requirements_limpio.txt

      Configurar Intérprete: Pulsa Ctrl + Shift + P, escribe "Python: Select Interpreter" y elige el que indica ('venv': venv)

3. Base de datos:

   3.1 Crea una base de datos nueva en PostgreSQL usando pdAdmin 4 llamada moveon_db, dejala vacia

   3.2 Ejecuta desde consola alembic upgrade head

   3.3 Si quieres usuarios fake para pruebas:

      3.3.1 Ejecuta python scripts/seed_fake_users.py y creara 20 usuarios con nombre usuarioX con email usuarioX@prueba.com (donde X es un numero del 1 al 20) y su contraseña es Prueba123

      3.3.2 Ejecuta python scripts/seed_fake_activities.py para crear actividades para los usuarios creados

      3.3.3 Ejecuta python scripts/cleanup_fake_data.py para borrar los 20 usuarios y sus actividades respetando los usuarios que tu hayas creado

5. Flujo de trabajo (Git). Para evitar conflictos, sigue siempre este orden:

   PULL: Antes de empezar, descarga los cambios de tus compañeros

   COMMIT: Cuando termines un cambio, guarda tus avances con un mensaje descriptivo

   PUSH: Envía tus cambios a GitHub

6. Ejecución del Servidor Backend. Para probar la API localmente, con el entorno venv activo, ejecuta: uvicorn main:app --reload

7. IMPORTANTE: Debes tener un .env actualizado
