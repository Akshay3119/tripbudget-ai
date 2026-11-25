"""Authenticate Docker with an isolated config. Never puts an access token in command arguments."""

import os
import subprocess
from pathlib import Path

env = dict(
    os.environ,
    CLOUDSDK_CONFIG=str(Path(".runtime/gcloud").resolve()),
    DOCKER_CONFIG=str(Path(".runtime/docker").resolve()),
)
Path(env["DOCKER_CONFIG"]).mkdir(exist_ok=True)
token = subprocess.run(
    ["gcloud", "auth", "print-access-token"], env=env, capture_output=True, text=True, check=True
).stdout
subprocess.run(
    ["docker", "login", "-u", "oauth2accesstoken", "--password-stdin", "https://us-central1-docker.pkg.dev"],
    input=token,
    env=env,
    text=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    check=True,
)
image = "us-central1-docker.pkg.dev/csci599-a3-hermes-1029/a4-tripbudget/app:v1"
subprocess.run(["docker", "tag", "tripbudget-ai:verification", image], env=env, check=True)
subprocess.run(["docker", "push", image], env=env, check=True)
