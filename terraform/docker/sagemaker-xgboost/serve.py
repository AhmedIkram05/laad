#!/usr/bin/env python3
"""
SageMaker XGBoost serving container with gunicorn.

Serves the xgboost-model from /opt/ml/model/ and responds to
/ping (health) and /invocations (predict) endpoints.

Input:  text/csv (single row per line) or application/json
Output: application/jsonlines
"""

import json
import os
from io import StringIO

import flask
import pandas as pd
import xgboost as xgb

MODEL_PATH = os.environ.get("SAGEMAKER_MODEL_PATH", "/opt/ml/model/xgboost-model")
model = None


def load_model():
    global model
    if not os.path.exists(MODEL_PATH):
        print(f"[ERROR] Model not found at {MODEL_PATH}", flush=True)
        return None
    model = xgb.Booster()
    model.load_model(MODEL_PATH)
    print(f"[INFO] Model loaded from {MODEL_PATH}", flush=True)
    print(f"[INFO] Model features: {model.num_features()}", flush=True)
    return model


# Load model at import time (before gunicorn forks workers)
print("[INFO] Loading model...", flush=True)
load_model()
print("[INFO] Model loading complete", flush=True)


app = flask.Flask(__name__)


@app.route("/ping", methods=["GET"])
def ping():
    healthy = model is not None
    status = 200 if healthy else 503
    return flask.Response(
        response=json.dumps({"status": "ok" if healthy else "model_not_loaded"}),
        status=status,
        mimetype="application/json",
    )


@app.route("/invocations", methods=["POST"])
def invocations():
    if model is None:
        return flask.Response(
            response=json.dumps({"error": "model not loaded"}),
            status=503,
            mimetype="application/json",
        )

    content_type = flask.request.content_type or ""

    try:
        if "text/csv" in content_type:
            data = flask.request.data.decode("utf-8")
            df = pd.read_csv(StringIO(data), header=None)
            dmatrix = xgb.DMatrix(df)
            predictions = model.predict(dmatrix)
        elif "json" in content_type:
            data = flask.request.get_json()
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict) and "instances" in data:
                df = pd.DataFrame(data["instances"])
            else:
                df = pd.DataFrame([data])
            dmatrix = xgb.DMatrix(df)
            predictions = model.predict(dmatrix)
        else:
            return flask.Response(
                response=json.dumps(
                    {
                        "error": f"unsupported content type: {content_type}. Use text/csv or application/json"
                    }
                ),
                status=400,
                mimetype="application/json",
            )

        # Format predictions
        if len(predictions.shape) == 1:
            pred_list = predictions.tolist()
        else:
            pred_list = predictions.tolist()

        result = json.dumps({"predictions": pred_list})
        return flask.Response(response=result, status=200, mimetype="application/json")

    except Exception as e:
        return flask.Response(
            response=json.dumps({"error": str(e)}),
            status=400,
            mimetype="application/json",
        )


if __name__ == "__main__":
    # If run directly (development), use Flask dev server
    port = int(os.environ.get("SAGEMAKER_SERVER_PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
