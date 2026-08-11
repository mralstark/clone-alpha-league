from app.main import create_app

# Create a single FastAPI instance for ASGI servers and deployment.
# Keep creation here to avoid import-time side-effects in package imports.
app = create_app()
