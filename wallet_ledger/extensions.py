"""Extensions partagées, instanciées une seule fois et branchées par la factory.

Les garder ici (et non dans la factory) évite les imports circulaires entre les
modèles, les services et l'application.
"""

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
