# Amir Ghahari Personal Website - Backend Architecture

## Project Overview

This repository contains the complete backend infrastructure and API server for **amir-ghahari.dev**. It's a fully serverless, cloud-native architecture built on AWS with infrastructure-as-code using CloudFormation.

### High-Level Architecture

```
Users → CloudFront CDN → API Gateway (api.amir-ghahari.dev)
                      ↓
                    Lambda Function
                      ↓
    ┌─────────────────┬─────────────────┐
    ↓                 ↓                  ↓
DynamoDB            SNS Topic        CloudWatch Logs
(Contacts DB)      (Email Alerts)     (Monitoring)
```

The system also serves static website content through CloudFront from S3, making it a complete web infrastructure solution.

---

## Directory Structure

```
amir_ghahari_personal_website_api_server/
├── cloudformation/
│   └── test.yaml                           # Production CloudFormation template (MAIN)
├── lambda/
│   └── post_contact/
│       ├── website_post_contact.py         # Python Lambda handler
│       ├── website_post_contact.zip        # Packaged Lambda function
│       └── requirements.txt                # Python dependencies
├── cloudformation-sample-code.yaml         # ECS example template (reference only)
└── README.md                               # Basic reference links
```

---

## Architecture Components

### 1. **AWS Services Stack**

#### API Gateway
- **Endpoint**: `api.amir-ghahari.dev` (via Route53 + custom domain)
- **Type**: REST API (Regional)
- **Resources**:
  - `/contact-page` - POST endpoint for contact form submissions
  - CORS/OPTIONS method for cross-origin requests
- **Stage**: `prod` (production environment)
- **Logging**: CloudWatch Logs for all requests

#### Lambda Function
- **Function**: `amirghahari-website-contact`
- **Runtime**: Python 3.14
- **Memory**: 128 MB
- **Timeout**: 20 seconds
- **Handler**: `website_post_contact.lambda_handler`
- **Code Source**: S3 bucket `amir-ghahari-website-lambdas` → `website_post_contact.zip`
- **Triggers**: API Gateway POST requests

#### DynamoDB
- **Table**: `amirghahari-website-contacts-table`
- **Partition Key**: `contact-id` (UUID string)
- **Sort Key**: `created-at` (ISO timestamp)
- **Attributes**:
  - `contact-id`: Unique message identifier
  - `created-at`: Submission timestamp
  - `name`: Sender's name
  - `email`: Sender's email address
  - `subject`: Message subject
  - `message`: Message body
- **Billing Mode**: PROVISIONED (1 RCU, 1 WCU)

#### SNS Topic
- **Topic**: `amirghahari-website-contacts-topic`
- **Subscriber**: Email notification to `ahesam.ghahari@gmail.com`
- **Purpose**: Real-time email alerts when contact forms are submitted

#### S3 Buckets
1. **Static Website Bucket** (`amirghahari-website`)
   - Stores frontend HTML, CSS, JavaScript files
   - Versioning enabled
   - AES-256 server-side encryption
   - Access only through CloudFront (via Origin Access Control)

2. **Lambda Code Bucket** (`amir-ghahari-website-lambdas`)
   - Stores packaged Lambda function ZIP files
   - Versioning enabled for deployment history
   - AES-256 server-side encryption

3. **Logging Bucket** (`amirghahari-website-access-logs`)
   - Centralized access logs from CloudFront and S3
   - Log prefixes: `cloudfront-access/`, `website-static/`, `website-lambdas/`
   - Separate from operational buckets for security and audit compliance

#### CloudFront Distribution
- **Domain**: `test.amir-ghahari.dev` (via Route53 CNAME)
- **SSL Certificate**: ACM certificate referenced via parameter
- **Origins**:
  - S3 bucket for static content (website files)
  - Future: API Gateway origin for API caching
- **Cache Behavior**:
  - Default cache policy for static assets
  - Compression enabled
  - HTTP/2 enabled
  - IPv6 supported
- **Root Object**: `index.html`

#### Route53 DNS
- **Hosted Zone**: `amir-ghahari.dev`
- **Records**:
  - `test.amir-ghahari.dev` → CloudFront distribution
  - `api.amir-ghahari.dev` → API Gateway custom domain
  - `www.amir-ghahari.dev` → Root domain alias

#### ACM Certificates
- **API Certificate**: `api.amir-ghahari.dev` (DNS validation)
- **CloudFront Certificate**: Passed via parameter (pre-created)

#### IAM Roles & Policies
1. **Lambda Execution Role** (`amirghahari-website-contact-lambda-role`)
   - Allows CloudWatch Logs writes (basic execution)
   - DynamoDB: `PutItem` permission on contacts table
   - SNS: `Publish` permission on notification topic

2. **API Gateway Role** (`api-gateway-role`)
   - CloudWatch Logs write access for debugging

---

## Lambda Function Details

### File: `lambda/post_contact/website_post_contact.py`

The Lambda function handles HTTP POST requests from the contact form on the website frontend.

#### Request Format
```json
{
  "name": "John Doe",
  "email": "john@example.com",
  "subject": "Inquiry about services",
  "message": "Hello, I'm interested in..."
}
```

#### Processing Steps

1. **Parse Request Body**
   - Extracts JSON from API Gateway event
   - Removes whitespace via `.strip()`

2. **Validation**
   - Checks all required fields present (name, email, subject, message)
   - Email format validation using regex: `^[^@]+@[^@]+\.[^@]+$`
   - Returns 400 error if validation fails

3. **Data Storage**
   - Generates UUID for unique message ID
   - Records current UTC timestamp in ISO format
   - Stores contact record in DynamoDB
   - **Note**: Subject field is stored correctly in DB, but bug exists in SNS email (stores email instead of subject on line 82)

4. **Email Notification**
   - Publishes message to SNS topic
   - Triggers automatic email to admin
   - Email includes: name, email, date, full message text

5. **Response**
   - Success (200): Returns message ID for tracking
   - Validation error (400): Returns error message
   - Server error (500): Generic error response for security

#### Response Format
```json
{
  "statusCode": 200,
  "headers": {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS"
  },
  "body": "{\"success\": true, \"id\": \"uuid-here\"}"
}
```

#### CORS Configuration
- Allows requests from any origin (`*`)
- Supports POST and OPTIONS methods
- Permits Content-Type and Authorization headers

#### Logging
- All major operations logged to CloudWatch:
  - Incoming request details
  - Parsed form data
  - Validation failures
  - Database operations
  - SNS publish status
  - Error details

---

## CloudFormation Template Structure

### File: `cloudformation/test.yaml`

The main infrastructure template with organized resource sections.

#### Parameters
- **CloudFrontCertArn**: ACM certificate ARN for CloudFront distribution (must be in us-east-1)

#### Resource Sections

**DynamoDB Resources**
- Contact submissions table with composite key

**SNS Resources**
- Topic for notifications
- Email subscription
- Topic policy for Lambda publish access

**Lambda Resources**
- IAM role with required permissions
- Lambda function definition
- API Gateway invocation permission

**CloudWatch Resources**
- Log group for API Gateway debug logging

**API Gateway Resources**
- REST API definition
- `/contact-page` resource
- POST and OPTIONS methods
- Integration with Lambda (AWS_PROXY)
- Custom domain mapping
- API certificate
- Deployment and prod stage
- Access logging configuration

**Route53 & DNS Resources**
- Domain alias records
- Custom domain names for API and CloudFront
- Health checks (future enhancement)

**S3 Resources**
- Static website bucket (versioned, encrypted)
- Lambda code bucket (versioned, encrypted)
- Access logs bucket
- Bucket policies and lifecycle rules

**CloudFront Resources**
- Origin Access Control (OAC) for S3 authentication
- Distribution with S3 origin
- SSL/TLS configuration
- Access logging
- Cache behaviors

---

## Deployment & Operations

### Prerequisites
- AWS Account with appropriate permissions
- CloudFormation access
- ACM certificate for CloudFront (pre-created in us-east-1)
- Domain registered and hosted zone created

### Deployment Steps

1. **Package Lambda Function**
   ```bash
   cd lambda/post_contact/
   zip -r website_post_contact.zip website_post_contact.py
   # Upload ZIP to S3: amir-ghahari-website-lambdas/website_post_contact.zip
   ```

2. **Deploy CloudFormation**
   ```bash
   aws cloudformation create-stack \
     --stack-name amir-ghahari-website-api \
     --template-body file://cloudformation/test.yaml \
     --parameters ParameterKey=CloudFrontCertArn,ParameterValue=arn:aws:acm:... \
     --capabilities CAPABILITY_NAMED_IAM
   ```

3. **Monitor Deployment**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name amir-ghahari-website-api \
     --query 'Stacks[0].StackStatus'
   ```

### Testing the API
```bash
# Test contact form submission
curl -X POST https://api.amir-ghahari.dev/contact-page \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "subject": "Test Subject",
    "message": "This is a test message"
  }'
```

### Monitoring & Logs
- **API Gateway Logs**: CloudWatch Logs group `/aws/apigateway/amirghahari-api-gateway`
- **Lambda Logs**: CloudWatch Logs group `/aws/lambda/amirghahari-website-contact`
- **Access Logs**: S3 bucket `amirghahari-website-access-logs`
  - CloudFront access logs in `cloudfront-access/` prefix
  - S3 bucket access logs in `website-static/` and `website-lambdas/` prefixes

### Cost Optimization
- DynamoDB: On-demand billing mode recommended for unpredictable traffic (switch to `PAY_PER_REQUEST`)
- Lambda: 128 MB memory is minimal; monitor execution time and increase if needed
- CloudFront: `PriceClass_All` used for global distribution; consider `PriceClass_100` for cost reduction
- S3: Lifecycle rules clean up old versions after 15 days

---

## Known Issues & TODOs

### Bug
- **Line 82 in `website_post_contact.py`**: Subject field stores `email` instead of `subject`
  ```python
  "subject": email,  # ❌ Should be: "subject": subject
  ```

### Future Enhancements
1. Add CloudFront origin for API Gateway (reduce origin latency)
2. Add WAF rules to API Gateway (protect against attacks)
3. Implement CORS pre-flight caching in CloudFront
4. Add DynamoDB point-in-time recovery
5. Implement automated certificate renewal
6. Add Lambda function versioning and aliases for blue-green deployments
7. Consider API rate limiting based on IP address
8. Add SNS subscription for SMS/Slack notifications
9. Implement API authentication for sensitive operations
10. Add CloudWatch alarms for errors and high latency

---

## Security Considerations

### Current Implementation
- ✅ S3 buckets encrypted with AES-256
- ✅ HTTPS/TLS for all endpoints
- ✅ CloudFront Origin Access Control for S3
- ✅ IAM roles with least-privilege permissions
- ✅ API Gateway logging enabled
- ✅ CORS properly configured

### Recommendations
- Add AWS WAF rules to API Gateway
- Enable S3 bucket versioning lock (Object Lock)
- Use AWS Secrets Manager for sensitive configuration
- Implement request validation in API Gateway
- Add API throttling per user/IP
- Enable VPC Flow Logs if using Lambda in VPC
- Regular security audits and penetration testing

---

## AWS References

### CloudFormation Documentation
- [AWS CloudFormation Template Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-template-resource-type-ref.html)
- [API Gateway with Lambda Proxy](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-apigateway-method.html)

### AWS Solutions & Architectures
- [AWS Architecture Center](https://aws.amazon.com/architecture/)
- [AWS Solutions Library](https://aws.amazon.com/solutions/)

### Service Documentation
- [API Gateway Developer Guide](https://docs.aws.amazon.com/apigateway/)
- [Lambda Developer Guide](https://docs.aws.amazon.com/lambda/)
- [DynamoDB Documentation](https://docs.aws.amazon.com/dynamodb/)
- [CloudFront Developer Guide](https://docs.aws.amazon.com/cloudfront/)
- [S3 User Guide](https://docs.aws.amazon.com/s3/)

---

## Author & Contact

**Project Owner**: Amir Ghahari  
**Domain**: amir-ghahari.dev  
**Email**: ahesam.ghahari@gmail.com  
**Repository**: Amir_Ghahari_Personal_Website_API_Server

