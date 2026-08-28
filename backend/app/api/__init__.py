from flask import Blueprint

from .chat import chat_bp
from .feedback import admin_feedback_bp, feedback_bp
from .health import health_bp
from .index import admin_index_bp
from .policies import admin_policies_bp
from .reader import reader_bp
from .security import security_bp


api_v1 = Blueprint("api_v1", __name__)
api_v1.register_blueprint(chat_bp)
api_v1.register_blueprint(feedback_bp)
api_v1.register_blueprint(health_bp)
api_v1.register_blueprint(security_bp, url_prefix="/admin/auth")
api_v1.register_blueprint(admin_policies_bp, url_prefix="/admin")
api_v1.register_blueprint(admin_index_bp, url_prefix="/admin")
api_v1.register_blueprint(admin_feedback_bp, url_prefix="/admin")
api_v1.register_blueprint(reader_bp)
