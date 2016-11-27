from __future__ import print_function

import cfn_resource

import boto3
import json
import logging
import os
import re
import subprocess
import tempfile

from contextlib import contextmanager

logger = logging.getLogger('AppBackendCertificates')
logger.setLevel(logging.DEBUG)

handler = cfn_resource.Resource()

@contextmanager
def temp_filenames(number):
    filenames = []
    try:
        for i in range(number):
            file = tempfile.NamedTemporaryFile(mode='w', delete=False)
            filenames.append(file.name)
            logger.debug("Creating temporary file '{}'".format(file.name))
            file.close()
        yield filenames[:]
    finally:
        for filename in filenames:
            try:
                logger.debug("Deleting temporary file '{}'".format(filename))
                os.remove(filename)
            except OSError:
                pass


def create_keys(apps_domain, length=2048):
    logger.info("Creating {} bit keys and certificates".format(length))
    with temp_filenames(2) as (cert_filename, key_filename):
        logger.debug("Writing keys: private key to '{}'; cert to '{}'".format(key_filename, cert_filename))
        command = ['openssl', 'req', '-x509',
                   '-sha256', '-nodes',
                   '-newkey', 'rsa:{}'.format(length),
                   '-keyout', key_filename,
                   '-out', cert_filename,
                   '-days', '3650',
                   '-subj', '/C=GB/ST=London/L=London/O=drie/CN=*.{0}'.format(apps_domain)]
        subprocess.check_output(command)
        with open(key_filename, 'r') as key_file:
            private_key = key_file.read()
        with open(cert_filename, 'r') as cert_file:
            cert = cert_file.read()
        command = ['openssl', 'x509',
                   '-in', cert_filename,
                   '-pubkey', '-noout']
        public_key = subprocess.check_output(command)
    return cert, private_key, public_key


def unarmour_key(armoured_key):
    one_line = armoured_key.replace("\n", "")
    key_type, key = re.match("-----BEGIN (\S+) KEY-----(.+)-----END \\1 KEY-----", one_line).groups()
    return key


def upload_keys(s3_bucket, s3_key, certificate_data):
    s3_client = boto3.client("s3")
    logger.info("Uploading certificates to {}/{}".format(s3_bucket, s3_key))
    s3_client.put_object(
        ACL='private',
        Body=json.dumps(certificate_data, indent=4).encode("utf-8"),
        Bucket=s3_bucket,
        ContentType='application/json',
        Key=s3_key,
        StorageClass='STANDARD',
    )


def certificate_name(app_name):
    return "backend-certificate-{}.json".format(app_name)


@handler.delete
def delete_certificate_details(event, context):
    resource_properties = event.get("ResourceProperties", {})
    app_name = resource_properties['AppName']
    s3_bucket = resource_properties['AppS3Bucket']
    s3_key = certificate_name(app_name)
    s3_client = boto3.client("s3")
    logger.info("Deleting {}/{}".format(s3_bucket, s3_key))
    try:
        s3_client.delete_objects(
            Bucket=s3_bucket,
            Delete={
                "Objects": [{"Key": s3_key}]
            }
        )
    except:
        pass
    return {"message": "Deleted certificates for {}".format(app_name),
            "PhysicalResourceId": event.get("PhysicalResourceId", context.log_stream_name)}


def get_certificate_details(event, context):
    resource_properties = event.get("ResourceProperties", {})
    app_domain = resource_properties['AppDomain']
    app_name = resource_properties['AppName']
    s3_bucket = resource_properties['AppS3Bucket']
    s3_key = certificate_name(app_name)
    s3_client = boto3.client("s3")
    logger.info("Getting certificates from {}/{}".format(s3_bucket, s3_key))
    try:
        response = s3_client.get_object(
            Bucket=s3_bucket,
            Key=s3_key
        )
        certificate_data = json.load(response['Body'])
    except Exception:
        KEY_LENGTH=2048
        cert, private_key, public_key = create_keys(app_domain, KEY_LENGTH)

        certificate_data = {
            "private_key": private_key,
            "app_name": app_name,
            "certificate": cert,
            "public_key": public_key,
            "apps_domain": app_domain
        }
        upload_keys(s3_bucket, s3_key, certificate_data)
    unarmoured_public_key = unarmour_key(certificate_data['public_key'])
    return {
        "Data": {
            "PublicKey": unarmoured_public_key,
            "CertificateS3Key": s3_key,
        },
        "message": "Certificate is in s3://{}/{}".format(s3_bucket, s3_key),
        "PhysicalResourceId": event.get("PhysicalResourceId", context.log_stream_name)
    }


@handler.create
def create(event, context):
    return get_certificate_details(event, context)


@handler.update
def update(event, context):
    return get_certificate_details(event, context)
