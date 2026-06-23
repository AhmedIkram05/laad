"""
SageMaker Model Upload Script

Downloads the champion XGBoost model from MLflow S3 artifacts, converts it to
SageMaker-compatible format (model.tar.gz with xgboost-model), and uploads it.

Usage (run inside backend container):
    python -m backend.src.scripts.upload_sagemaker_model

Or via Docker:
    docker exec laad-backend-1 python -m backend.src.scripts.upload_sagemaker_model
"""

import json
import logging
import os
import tarfile
import tempfile
from pathlib import Path

import boto3
import xgboost as xgb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Configuration ---
BUCKET = "laad-mlflow-artifacts"
SAGEMAKER_MODELS_PREFIX = "sagemaker-models"
CHAMPION_MODEL_PATH = "2/models/m-0a23b657155c4c1c861a821e8cfba6f1/artifacts/model.ubj"
MODEL_VERSION = os.environ.get("SAGEMAKER_MODEL_VERSION", "1")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "eu-west-2")

# Remote paths
DEST_KEY = f"{SAGEMAKER_MODELS_PREFIX}/{MODEL_VERSION}/model.tar.gz"
SOURCE_BUCKET = BUCKET
SOURCE_KEY = CHAMPION_MODEL_PATH


def download_s3_file(s3_client, bucket: str, key: str, local_path: str) -> None:
    """Download a file from S3 to a local path."""
    logger.info("Downloading s3://%s/%s ...", bucket, key)
    s3_client.download_file(bucket, key, local_path)
    logger.info("Downloaded to %s (%d bytes)", local_path, Path(local_path).stat().st_size)


def upload_s3_file(s3_client, bucket: str, key: str, local_path: str) -> None:
    """Upload a local file to S3."""
    logger.info("Uploading %s to s3://%s/%s ...", local_path, bucket, key)
    s3_client.upload_file(local_path, bucket, key)
    logger.info("Upload complete")


def convert_model_to_sagemaker_format(input_path: str, output_dir: str) -> str:
    """
    Load an XGBoost sklearn model from UBJ format and save as SageMaker-compatible
    xgboost-model file. Returns path to model.tar.gz.
    """
    logger.info("Loading XGBoost model from %s ...", input_path)

    # Load the model — XGBoost 3.x supports UBJ format
    model = xgb.XGBClassifier()
    model.load_model(input_path)

    # Extract the internal booster
    booster = model.get_booster()

    # Save as JSON format (XGBoost 2.0+ defaults to UBJSON; SageMaker XGBoost 1.5 cannot read UBJSON)
    # Using .json extension forces JSON format which is compatible with XGBoost 1.x
    xgb_model_json = os.path.join(output_dir, "xgboost-model.json")
    booster.save_model(xgb_model_json)
    # SageMaker expects the file named "xgboost-model", but load_model() auto-detects JSON by content
    xgb_model_path = os.path.join(output_dir, "xgboost-model")
    os.rename(xgb_model_json, xgb_model_path)
    logger.info("Saved booster as JSON: %s (%d bytes)", xgb_model_path, Path(xgb_model_path).stat().st_size)

    # Create model.tar.gz with the xgboost-model file
    tar_path = os.path.join(output_dir, "model.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(xgb_model_path, arcname="xgboost-model")

    logger.info("Created model.tar.gz (%d bytes)", Path(tar_path).stat().st_size)
    return tar_path


def main():
    logger.info("=" * 60)
    logger.info("SageMaker Model Upload Script")
    logger.info("Source: s3://%s/%s", SOURCE_BUCKET, SOURCE_KEY)
    logger.info("Dest:   s3://%s/%s", BUCKET, DEST_KEY)
    logger.info("=" * 60)

    s3 = boto3.client("s3", region_name=AWS_REGION)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Download champion model from S3
        model_ubj = os.path.join(tmpdir, "model.ubj")
        download_s3_file(s3, SOURCE_BUCKET, SOURCE_KEY, model_ubj)

        # Step 2: Convert to SageMaker format
        tar_path = convert_model_to_sagemaker_format(model_ubj, tmpdir)

        # Step 3: Upload model.tar.gz to S3
        upload_s3_file(s3, BUCKET, DEST_KEY, tar_path)

        # Step 4: Print result for terraform
        model_data_url = f"s3://{BUCKET}/{DEST_KEY}"
        print(f"\n{'=' * 60}")
        print(f"✅ Model uploaded to: {model_data_url}")
        print(f"Use this terraform command:")
        print(f"  terraform apply -var='sagemaker_enabled=true' -var='sagemaker_model_data_url={model_data_url}'")
        print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    exit(main())
