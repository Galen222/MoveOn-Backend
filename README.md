MoveON - Aplicación deportiva para guardar rutas de movimiento andando o corriendo.

Python desarrollado en Visual Studio Code (FastAPI) y Base de Datos PostgreSQL

🚀 Guía para Colaboradores

1. Clonar el repositorio
   Abre una terminal en tu carpeta de proyectos y ejecuta: git clone https://github.com/Galen222/MoveOn-Backend.git y después cd MoveOn-Backend

2. Backend (Visual Studio Code)

   2.1 Abre Visual Studio Code. Selecciona Archivo > Abrir Carpeta... y elige la carpeta MoveOn-Backend.

   2.2 Crear Entorno Virtual: Abre la terminal de VS Code y ejecuta: python -m venv venv

   2.3 Activar Entorno:

      Windows: .\venv\Scripts\activate

      Mac/Linux: source venv/bin/activate

      Instalar Dependencias: pip install -r requirements_limpio.txt

      Configurar Intérprete: Pulsa Ctrl + Shift + P, escribe "Python: Select Interpreter" y elige el que indica ('venv': venv).

3. Flujo de trabajo (Git). Para evitar conflictos, sigue siempre este orden:

PULL: Antes de empezar, descarga los cambios de tus compañeros.

COMMIT: Cuando termines un cambio, guarda tus avances con un mensaje descriptivo.

PUSH: Envía tus cambios a GitHub.

4. Ejecución del Servidor Backend

Para probar la API localmente, con el entorno venv activo, ejecuta: uvicorn main:app --reload
