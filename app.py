import os
from google.adk.cli.fast_api import get_fast_api_app

# Initialize the FastAPI application using ADK's helper
# This ensures it's compatible with the Dockerfile's gunicorn command
# We point to the root directory where 'adk_app' package resides.
app = get_fast_api_app(agents_dir=".", web=True)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)