from app.main import app
from app.job_api import register_job_routes

register_job_routes(app)
