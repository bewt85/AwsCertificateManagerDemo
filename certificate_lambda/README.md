# CreateElbBackendCertificates

This is a Lambda function which can be used in a CloudFormation template to create self signed SSL certificates.
These are used by the hacky PaaS to secure the connection between an ELB and instances in an autoscaling group.
The certificates and their keys are stored in an S3 bucket.  Note that in this implementation, none of these
details are encrypted.  Normally I would use KMS for this but it would have made the code less clear than
it already is.

## Deployment

* Creating an IAM policy and IAM role with permissions at least as generous as the [lambda_policy](lambda_policy.json)
* Create a private S3 bucket for the certificates
* Run [package.sh](package.sh) on a Linux machine (it might work on OSX but it isn't tested)
* Create a new Python 2.7 Lambda function called `CreateElbBackendCertificates`
* Upload the ZIP file which is created to your new Lambda
* Set the "handler" to `lambda_function.handler`
* Set the lambda timeout to 30 seconds (128 MB of RAM is loads for this)
* Leave the VPC as default
* Use the new role you created

## Dependencies

* [Probably] Linux (tested on Ubuntu 15.04)
* Python 2.7
* virtualenv (`pip install virtualenv`)
