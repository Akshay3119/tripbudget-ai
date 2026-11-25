"""Authenticate Docker with an isolated config. Never puts an access token in command arguments."""

import os
import argparse
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--tag", default="v1")
parser.add_argument("--local-image", default="tripbudget-ai:verification")
args = parser.parse_args()
if not __import__("re").fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", args.tag):
    raise SystemExit("Invalid image tag")
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
image = "us-central1-docker.pkg.dev/csci599-a3-hermes-1029/a4-tripbudget/app:" + args.tag
subprocess.run(["docker", "tag", args.local_image, image], env=env, check=True)
subprocess.run(["docker", "push", image], env=env, check=True)
