import json
import os
import re
import uuid
import boto3
import logging
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")

TABLE_NAME = os.environ["TABLE_NAME"]
TOPIC_ARN = os.environ["TOPIC_ARN"]

table = dynamodb.Table(TABLE_NAME)
EMAIL_REGEX = r"^[^@]+@[^@]+\.[^@]+$"


def is_valid_email(email: str) -> bool:
    return re.match(EMAIL_REGEX, email) is not None


def response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        logger.info("Received event: %s", event)
        logger.info("Parsed body: %s", body)

        name = body.get("name", "").strip()
        email = body.get("email", "").strip()
        subject = body.get("subject", "").strip()
        message = body.get("message", "").strip()

        if not name or not email or not subject or not message:
            logger.info("Rejected: missing required field(s)")
            return response(400, {"error": "All fields are required"})

        if not is_valid_email(email):
            logger.info("Rejected: invalid email address")
            return response(400, {"error": "Invalid email"})

        msg_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        table.put_item(
            Item={
                "contact-id": msg_id,
                "created-at": created_at,
                "name": name,
                "email": email,
                "subject": subject,
                "message": message,
            }
        )
        logger.info("Stored contact %s in DynamoDB", msg_id)

        sns.publish(
            TopicArn=TOPIC_ARN,
            Subject="New Contact Form Submission — amir-ghahari.dev",
            Message=(
                f"New Contact Form Submission\n\n"
                f"Name:    {name}\n"
                f"Email:   {email}\n"
                f"Subject: {subject}\n"
                f"Date:    {created_at}\n\n"
                f"Message:\n{message}"
            ),
        )
        logger.info("Published notification for contact %s to SNS", msg_id)

        return response(200, {"success": True, "id": msg_id})

    except Exception as e:
        logger.exception("Unhandled error: %s", str(e))
        return response(500, {"error": "Internal server error"})
