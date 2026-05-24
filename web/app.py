"""Flask application factory."""

import logging
from flask import Flask
from core.database import init_db


def create_app(config: dict) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = config["web"]["secret_key"]
    app.config["VOLLEY_CONFIG"] = config

    init_db()

    from web.routes.dashboard import bp as dash_bp
    from web.routes.campaigns import bp as camp_bp
    from web.routes.leads import bp as leads_bp
    from web.routes.sequences import bp as seq_bp
    from web.routes.analytics import bp as analytics_bp
    from web.routes.api import bp as api_bp

    app.register_blueprint(dash_bp)
    app.register_blueprint(camp_bp)
    app.register_blueprint(leads_bp)
    app.register_blueprint(seq_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(api_bp)

    logging.getLogger(__name__).info("Flask app created")
    return app
