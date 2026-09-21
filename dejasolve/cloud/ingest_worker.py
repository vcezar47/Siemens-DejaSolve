"""SQS consumer for Layer 1 at scale -- the queue in data.yaml, an ECS Fargate
service in compute.yaml. Long-polls one artifact reference at a time,
downloads it from S3, runs it through the *same* ingest.ingest_text() the CLI
and app.py use, and writes the resulting Case Card back to S3 -- unchanged
parsing logic, just a different place for the artifact and the result to live.

Message body (JSON): {"key": "artifacts/foo.log"}, optionally with "bucket"
(defaults to DATA_BUCKET), "name" (defaults to the key's filename), and
"backend" (defaults to "auto").

    python -m dejasolve.cloud.ingest_worker
"""

from __future__ import annotations

import json
import os

import boto3

from .. import ingest

QUEUE_URL = os.environ["INGEST_QUEUE_URL"]
DEFAULT_BUCKET = os.environ.get("DATA_BUCKET")

sqs = boto3.client("sqs")
s3 = boto3.client("s3")


def _process(message: dict) -> None:
    body = json.loads(message["Body"])
    bucket = body.get("bucket", DEFAULT_BUCKET)
    key = body["key"]
    name = body.get("name", key.rsplit("/", 1)[-1])

    obj = s3.get_object(Bucket=bucket, Key=key)
    text = obj["Body"].read().decode("utf-8")

    card = ingest.ingest_text(text, name, backend=body.get("backend", "auto"))

    out_key = f"cards/{name}.json"
    s3.put_object(Bucket=bucket, Key=out_key,
                  Body=json.dumps(card.to_dict(), indent=2).encode("utf-8"),
                  ContentType="application/json")
    found = len(card.params)
    print(f"ingested s3://{bucket}/{key} -> s3://{bucket}/{out_key} "
          f"({found}/{found + len(card.missing)} fields)")


def main() -> None:
    print(f"ingest-worker polling {QUEUE_URL}")
    while True:
        resp = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=1,
                                   WaitTimeSeconds=20)
        for message in resp.get("Messages", []):
            try:
                _process(message)
            except Exception as exc:  # noqa: BLE001 -- one bad message must not wedge the loop
                print(f"failed: {exc}")
            else:
                sqs.delete_message(QueueUrl=QUEUE_URL,
                                   ReceiptHandle=message["ReceiptHandle"])


if __name__ == "__main__":
    main()
