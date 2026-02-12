from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "Tenderlitika V2 is alive"}