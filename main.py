from fastapi import FastAPI

from routers import auth, users

app = FastAPI()

app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
