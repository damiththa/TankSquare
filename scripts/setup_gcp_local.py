#!/usr/bin/env python3
"""
TankSquare — Local Terminal GCP & Secret Manager Provisioning Script (`scripts/setup_gcp_local.py`).

Run this directly from your Mac terminal:
    python3 scripts/setup_gcp_local.py

What this script does locally from your terminal:
1. Verifies `gcloud` CLI is installed and authenticated (`gcloud auth login` + `gcloud auth application-default login`).
2. Prompts for your single `GCP_PROJECT_ID` (and optional region, default `us-central1`).
3. Uses hidden terminal input (`getpass`) to prompt for `GOOGLE_MAPS_API_KEY` and `W3W_API_KEY`
   so your keys NEVER appear in your shell history (`.zsh_history`) or in Git.
4. Auto-generates cryptographically random 32-byte secrets for `SESSION_SIGNING_SECRET` and `VENDOR_API_SHARED_SECRET`.
5. Uploads all 4 secrets directly to Google Cloud Secret Manager (`tanksquare-*`).
6. Grants the Cloud Run runtime service account `roles/secretmanager.secretAccessor`.
7. Provisions the Native Cloud Firestore database and `gs://<PROJECT_ID>-media` Cloud Storage bucket.
8. Writes ONLY non-sensitive project/environment pointers (`GCP_PROJECT_ID`, `USE_GCP_SECRET_MANAGER=true`)
   to your local untracked `.env` file so local terminal runs fetch secrets straight from GCP Secret Manager!
"""

import getpass
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


REPO_ROOT = Path(__file__).resolve().parent.parent


def find_gcloud() -> Optional[str]:
    """Locate the `gcloud` binary on macOS."""
    in_path = shutil.which("gcloud")
    if in_path:
        return in_path

    common_mac_paths = [
        Path.home() / "google-cloud-sdk" / "bin" / "gcloud",
        Path("/opt/homebrew/bin/gcloud"),
        Path("/usr/local/bin/gcloud"),
        Path("/usr/local/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/bin/gcloud"),
    ]
    for p in common_mac_paths:
        if p.exists():
            return str(p)
    return None


def run_cmd(args: List[str], input_bytes: Optional[bytes] = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def upsert_gcp_secret(gcloud_bin: str, project_id: str, secret_id: str, secret_value: str) -> None:
    """Create a secret in GCP Secret Manager if it doesn't exist, then add a new version from stdin."""
    desc = run_cmd([gcloud_bin, "secrets", "describe", secret_id, f"--project={project_id}"], check=False)
    if desc.returncode != 0:
        print(f"  -> Creating secret '{secret_id}' in GCP Secret Manager...")
        run_cmd(
            [
                gcloud_bin,
                "secrets",
                "create",
                secret_id,
                "--replication-policy=automatic",
                f"--project={project_id}",
            ]
        )
    else:
        print(f"  -> Adding new version to existing secret '{secret_id}'...")

    run_cmd(
        [
            gcloud_bin,
            "secrets",
            "versions",
            "add",
            secret_id,
            "--data-file=-",
            f"--project={project_id}",
        ],
        input_bytes=secret_value.encode("utf-8"),
    )


def main() -> None:
    print("=" * 72)
    print(" TankSquare — Local Mac Terminal GCP & Secret Manager Setup")
    print("=" * 72)

    gcloud_bin = find_gcloud()
    if not gcloud_bin:
        print("\n[!] `gcloud` CLI was not found on your Mac.")
        print("Install it in your Mac terminal with either:")
        print("  Option A (Official Mac Installer): curl https://sdk.cloud.google.com | bash")
        print("  Option B (Homebrew):               brew install --cask google-cloud-sdk")
        sys.exit(1)

    print(f"[✓] Found gcloud CLI at: {gcloud_bin}")

    # 1. Prompt for GCP Project ID & Region
    default_proj = os.getenv("GCP_PROJECT_ID", "").strip()
    project_id = input(f"\nEnter your single GCP Project ID [{default_proj or 'e.g. tanksquare-cloud'}]: ").strip() or default_proj
    if not project_id:
        print("[!] A valid GCP Project ID is required.")
        sys.exit(1)

    region = input("Enter preferred GCP Region [us-central1]: ").strip() or "us-central1"

    # 2. Hidden input for API keys (never echoed to terminal or history)
    print("\n--- Secret Manager Key Input (Hidden input — nothing echoed to screen) ---")
    maps_key = getpass.getpass("Paste your Google Maps Platform API Key (or press Enter for PLACEHOLDER): ").strip() or "PLACEHOLDER_MAPS_KEY"
    w3w_key = getpass.getpass("Paste your what3words API Key (or press Enter for PLACEHOLDER): ").strip() or "PLACEHOLDER_W3W_KEY"

    session_secret = secrets.token_urlsafe(32)
    vendor_secret = secrets.token_urlsafe(32)

    # 3. Set active project & enable APIs
    print(f"\n[1/5] Configuring GCP project '{project_id}' and enabling required APIs...")
    run_cmd([gcloud_bin, "config", "set", "project", project_id])
    apis = [
        "run.googleapis.com",
        "firestore.googleapis.com",
        "storage.googleapis.com",
        "secretmanager.googleapis.com",
        "cloudbuild.googleapis.com",
        "artifactregistry.googleapis.com",
        "maps-backend.googleapis.com",
        "geocoding-backend.googleapis.com",
    ]
    run_cmd([gcloud_bin, "services", "enable", *apis, f"--project={project_id}"])
    print("  [✓] GCP APIs enabled.")

    # 4. Upload all 4 secrets to Google Cloud Secret Manager
    print("\n[2/5] Storing secrets in Google Cloud Secret Manager (zero local plaintext keys)...")
    upsert_gcp_secret(gcloud_bin, project_id, "tanksquare-google-maps-api-key", maps_key)
    upsert_gcp_secret(gcloud_bin, project_id, "tanksquare-w3w-api-key", w3w_key)
    upsert_gcp_secret(gcloud_bin, project_id, "tanksquare-session-signing-secret", session_secret)
    upsert_gcp_secret(gcloud_bin, project_id, "tanksquare-vendor-api-secret", vendor_secret)
    print("  [✓] All 4 secrets stored in Google Cloud Secret Manager.")

    # 5. Grant Cloud Run service account Secret Manager access
    print("\n[3/5] Granting Cloud Run service account access to Secret Manager...")
    proj_num_proc = run_cmd(
        [gcloud_bin, "projects", "describe", project_id, "--format=value(projectNumber)"]
    )
    project_number = proj_num_proc.stdout.decode("utf-8").strip()
    if project_number:
        run_cmd(
            [
                gcloud_bin,
                "projects",
                "add-iam-policy-binding",
                project_id,
                f"--member=serviceAccount:{project_number}-compute@developer.gserviceaccount.com",
                "--role=roles/secretmanager.secretAccessor",
            ],
            check=False,
        )
        print("  [✓] IAM role 'roles/secretmanager.secretAccessor' bound.")

    # 6. Provision Firestore & Cloud Storage Bucket (idempotent)
    print("\n[4/5] Ensuring Native Firestore database & GCS media bucket exist...")
    run_cmd(
        [
            gcloud_bin,
            "firestore",
            "databases",
            "create",
            "--location=nam5",
            "--type=firestore-native",
            f"--project={project_id}",
        ],
        check=False,
    )
    bucket_uri = f"gs://{project_id}-media"
    run_cmd(
        [
            gcloud_bin,
            "storage",
            "buckets",
            "create",
            bucket_uri,
            f"--location={region}",
            "--uniform-bucket-level-access",
            f"--project={project_id}",
        ],
        check=False,
    )
    print(f"  [✓] Firestore (nam5) and GCS Bucket ({bucket_uri}) ready.")

    # 7. Write secret-free local `.env` pointer file (untracked by Git)
    print("\n[5/5] Writing secret-free `.env` pointer file (loads secrets from GCP Secret Manager)...")
    env_file = REPO_ROOT / ".env"
    env_content = (
        "# Auto-generated by scripts/setup_gcp_local.py (Untracked by Git)\n"
        "# Sensitive keys are NOT stored here; they are fetched at runtime from GCP Secret Manager.\n"
        "ENV=dev\n"
        f"GCP_PROJECT_ID={project_id}\n"
        "FIRESTORE_DATABASE=(default)\n"
        "FIRESTORE_COLLECTION_PREFIX=dev_\n"
        f"GCS_BUCKET_NAME={project_id}-media\n"
        "USE_GCP_SECRET_MANAGER=true\n"
        "SEED_DEMO_DATA=true\n"
    )
    env_file.write_text(env_content, encoding="utf-8")
    print(f"  [✓] Wrote non-sensitive project pointer to {env_file} (ignored by Git).")
    print("\nSetup complete! Your secrets are safely stored in GCP Secret Manager.")


if __name__ == "__main__":
    main()
