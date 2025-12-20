from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Hola, el backend de MoveOn está vivo"}