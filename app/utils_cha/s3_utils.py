import boto3
from botocore.config import Config
from flask import current_app
import os
from botocore.exceptions import ClientError
from flask import Response, stream_with_context

def get_s3_client():
    """Get S3 client with configured credentials"""
    try:
        client = boto3.client(
            "s3",
            aws_access_key_id=current_app.config["AWS_ACCESS_KEY_ID"],
            aws_secret_access_key=current_app.config["AWS_SECRET_ACCESS_KEY"],
            region_name=current_app.config["AWS_REGION"],
            endpoint_url=current_app.config["S3_ENDPOINT_URL"],
            config=Config(signature_version="s3v4"),
        )
        print("S3 client created successfully")
        return client
    except Exception as e:
        print(f"Error creating S3 client: {str(e)}")
        raise


def upload_file_to_s3(file, bucket, key):
    """Upload a file to S3 bucket"""
    try:
        print(f"Starting S3 upload - Bucket: {bucket}, Key: {key}")
        s3_client = get_s3_client()

        # Reset file pointer to beginning
        file.seek(0)

        # Get content type from file if available
        content_type = getattr(file, "content_type", "application/octet-stream")

        # Upload file with content type
        s3_client.upload_fileobj(
            file, bucket, key, ExtraArgs={"ContentType": content_type}
        )
        print("File uploaded successfully to S3")
        return True
    except ClientError as e:
        return False
    except Exception as e:
        return False


def get_s3_url(bucket, key, expires_in=3600):
    """Generate S3 URL for a file"""
    try:
        print(f"Generating presigned URL - Bucket: {bucket}, Key: {key}")
        s3_client = get_s3_client()

        # Ensure the key doesn't start with a slash
        if key.startswith("/"):
            key = key[1:]
            print(f"Removed leading slash from key. New key: {key}")

        # Generate the presigned URL
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,  # URL expires in specified seconds (default 1 hour)
        )
        print(
            f"Generated presigned URL successfully: {url[:100]}..."
        )  # Print first 100 chars of URL
        return url
    except ClientError as e:
        print(f"AWS Error generating S3 URL: {str(e)}")
        print(f"Error code: {e.response['Error']['Code']}")
        print(f"Error message: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        print(f"Unexpected error generating S3 URL: {str(e)}")
        import traceback

        traceback.print_exc()
        return None


def delete_file_from_s3(bucket, key):
    """Delete a file from S3 bucket"""
    try:
        print(f"Attempting to delete file - Bucket: {bucket}, Key: {key}")
        s3_client = get_s3_client()
        s3_client.delete_object(Bucket=bucket, Key=key)
        print("File deleted successfully from S3")
        return True
    except ClientError as e:
        print(f"AWS Error deleting file from S3: {str(e)}")
        return False
    except Exception as e:
        print(f"Unexpected error deleting file from S3: {str(e)}")
        return False


def get_secure_document_url(s3_key):
    """
    Generate a secure URL that goes through your application proxy instead of direct S3 access.
    This replaces the old get_s3_url function for document viewing.
    """
    try:
        # Remove leading slash if present
        if s3_key.startswith("/"):
            s3_key = s3_key[1:]
        
        # Get base URL from config
        base_url = current_app.config.get('BASE_URL')
        
        # Generate secure proxy URL
        secure_url = f"{base_url}/secure-document/{s3_key}"
        print(f"Generated secure URL: {secure_url}")
        return secure_url
        
    except Exception as e:
        print(f"Error generating secure URL: {str(e)}")
        return None
    

def serve_s3_file(s3_key, bucket=None):
    """
    Serve S3 file through your application (proxy method).
    This function is used by the secure document route.
    """
    try:
        if not bucket:
            bucket = current_app.config["S3_BUCKET_NAME"]
            
        print(f"Serving S3 file - Bucket: {bucket}, Key: {s3_key}")
        s3_client = get_s3_client()
        
        # Get object from S3
        response = s3_client.get_object(Bucket=bucket, Key=s3_key)
        
        # Get content type
        content_type = response.get('ContentType', 'application/octet-stream')
        
        # Get filename from S3 key
        filename = os.path.basename(s3_key)
        
        def generate():
            try:
                # Stream the file in chunks
                for chunk in response['Body'].iter_chunks(chunk_size=8192):
                    yield chunk
            except Exception as e:
                print(f"Error streaming file: {str(e)}")
                
        return Response(
            stream_with_context(generate()),
            mimetype=content_type,
            headers={
                'Content-Disposition': f'inline; filename="{filename}"',
                'Cache-Control': 'private, max-age=3600'  # Cache for 1 hour
            }
        )
        
    except ClientError as e:
        print(f"AWS Error serving file: {str(e)}")
        if e.response['Error']['Code'] == 'NoSuchKey':
            return Response("File not found", status=404)
        else:
            return Response("Error accessing file", status=500)
    except Exception as e:
        print(f"Unexpected error serving file: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response("Internal server error", status=500)
    
