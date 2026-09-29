"""Print the OpenAPI document; the frontend types are generated from it (make codegen)."""

import json

from app.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2, sort_keys=True))
