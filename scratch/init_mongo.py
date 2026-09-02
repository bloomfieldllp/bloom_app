import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
config.settings.IS_LOCAL_OPERATOR = False

from database import init_db
init_db()
print("Mongo init complete")
