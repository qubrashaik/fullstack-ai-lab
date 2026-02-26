from flask import Flask, request, jsonify, render_template
from flask_cors import CORS



from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt
)
from pymongo import MongoClient
import bcrypt
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ---------------- JWT Configuration ----------------

app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY")

app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)

jwt = JWTManager(app)

# ---------------- MongoDB Connection ----------------
client = MongoClient(os.getenv("MONGO_URI"))
db = client["fullstack_ai_lab"]
users_collection = db["users"]
revoked_tokens_collection = db["revoked_tokens"]

# ---------------- Routes ----------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/signup", methods=["POST"])
def signup():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400

        if users_collection.find_one({"email": email}):
            return jsonify({"error": "Email already registered"}), 400

        hashed_password = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt()
        )

        users_collection.insert_one({
            "email": email,
            "password": hashed_password,
            "created_at": datetime.utcnow()
        })

        return jsonify({"message": "User registered successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        user = users_collection.find_one({"email": email})

        if not user or not bcrypt.checkpw(
            password.encode("utf-8"),
            user["password"]
        ):
            return jsonify({"error": "Invalid credentials"}), 401

        access_token = create_access_token(identity=email)
        refresh_token = create_refresh_token(identity=email)

        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": email
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    current_user = get_jwt_identity()
    new_access_token = create_access_token(identity=current_user)
    return jsonify({"access_token": new_access_token}), 200


@app.route("/api/protected", methods=["GET"])
@jwt_required()
def protected():
    current_user = get_jwt_identity()
    return jsonify({
        "message": "Access granted to protected resource",
        "user": current_user,
        "timestamp": datetime.utcnow().isoformat()
    }), 200


@app.route("/api/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    revoked_tokens_collection.insert_one({"jti": jti})
    return jsonify({"message": "Successfully logged out"}), 200


# ---------------- Token Blocklist ----------------
@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_header, jwt_payload):
    jti = jwt_payload["jti"]
    return revoked_tokens_collection.find_one({"jti": jti}) is not None


# ---------------- JWT Error Handlers ----------------
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({"error": "Token has expired"}), 401


@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({"error": "Invalid token"}), 401


@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({"error": "Authorization header required"}), 401


# ---------------- Run App ----------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)