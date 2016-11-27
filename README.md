# AwsCertificateManagerDemo

AWS Cerificate Manager (ACM) is a great tool to create SSL certificates and deploy them infront of AWS based services using Amazon CloudFront or an Elastic Load Balancer (ELB).  The nicest properties of ACM are:

* It's really east to create certificates (no faffing with signing requests etc)
* It's not possible to steal the private key (not even you get to see it) which makes it much easier to secure
* It's reniewed automatically by Amazon
* Amazon terminates SSL on their boxes (and they fix problems like Heartbleed before they're even announced)
* It's free

The challenge is to securely connect the load balancer to the instances actually serving the request.  Fortunatly ELBs support uploading a public key for a self signed certificates although this is somewhat non trivial.

## Aims

This repo leads you through the steaps to apply end to end encryption for a collection of instances using AWS Certificate Manager, ELB, AWS Lambda, CloudFormation and S3.  Eventually your architecture will look a bit like this:

![User traffic is terminated on ELB, traffic is re-encrypted between the ELB and instances using a self signed certificate which is created by AWS Lambda and loaded from S3 when the instances boot](https://github.com/bewt85/AwsCertificateManagerDemo/raw/master/acm_s3_ssl_cert_demo.png "Architecture overview")

As an aside, this repo also gives you a bit of background on how CloudFormation works and how to use Custom Resources (powered by Lambda) to do more powerful things.

## Step 1 - A load balanced app

[The first template](cf_simple.yml) sets up a load balancer with an autoscalling group of servers behind it.  There is no connection encryption in this example.

To give it a go just download [the template](cf_simple.yml), go into the AWS CloudFormation console, create a new stack, select the option to upload the CloudFormation template to S3 and give it `cf_simple.yml`.

You then need to give your new stack a name (e.g. `simple`).  I've also created a parameter for an SSH key which will be loaded 

--- More TODO
