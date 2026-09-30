import os
import secrets

from flask import Flask, redirect, request, url_for
from flask_login import LoginManager, current_user

from .models import Usuario, db
from .utils import csrf_token, formata_data, formata_moeda, url_segura, verificar_csrf

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar o sistema."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def carregar_usuario(user_id):
    return db.session.get(Usuario, int(user_id))


def _secret_key(instance_path):
    """Usa SECRET_KEY do ambiente ou gera uma e guarda na pasta instance."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    caminho = os.path.join(instance_path, "secret_key")
    if not os.path.exists(caminho):
        with open(caminho, "w") as f:
            f.write(secrets.token_hex(32))
    with open(caminho) as f:
        return f.read().strip()


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.update(
        SECRET_KEY=_secret_key(app.instance_path),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", "sqlite:///" + os.path.join(app.instance_path, "construtora.db")
        ),
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", os.path.join(app.instance_path, "uploads")),
        MAX_CONTENT_LENGTH=25 * 1024 * 1024,  # 25 MB por envio
    )
    if config:
        app.config.update(config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from .routes import bp_auth, bp_main
    from .routes_cadastros import bp_cad

    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_main)
    app.register_blueprint(bp_cad)

    app.jinja_env.filters["moeda"] = formata_moeda
    app.jinja_env.filters["data"] = formata_data
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["url_segura"] = url_segura

    @app.before_request
    def _antes():
        verificar_csrf()
        # Enquanto não existir nenhum usuário, obriga a criar o administrador.
        if request.endpoint not in ("auth.setup", "static") and Usuario.query.count() == 0:
            return redirect(url_for("auth.setup"))

    @app.context_processor
    def _ctx():
        from .models import Empresa

        empresa = Empresa.get() if current_user.is_authenticated else None
        return {"empresa_atual": empresa}

    with app.app_context():
        db.create_all()

    return app
