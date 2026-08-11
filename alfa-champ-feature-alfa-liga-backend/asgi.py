from app.main import create_app

# Create a single FastAPI instance for ASGI servers and deployment.
# Avoid name collisions with the package named `app` by exposing both
# `application` (canonical ASGI) and `app` for tools that expect it.
application = create_app()
# export legacy name too
app = application
