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

![User traffic is terminated on ELB, traffic is re-encrypted between the ELB and instances using a self signed certificate which is created by AWS Lambda and loaded from S3 when the instances boot](https://github.com/bewt85/AwsCertificateManagerDemo/raw/master/images/acm_s3_ssl_cert_demo.png "Architecture overview")

As an aside, this repo also gives you a bit of background on how CloudFormation works and how to use Custom Resources (powered by Lambda) to do more powerful things.

## Step 1 - A load balanced app

[The first template](cf_simple.yml) sets up a load balancer with an autoscalling group of servers behind it.  There is no connection encryption in this example.

To give it a go just click this button: [![Launch button for cf_simple.yml](https://github.com/bewt85/AwsCertificateManagerDemo/raw/master/images/cloudformation-launch-stack.png "Launch cf_simple.yml")](https://console.aws.amazon.com/cloudformation/home?region=eu-west-1#/stacks/new?stackName=simple&templateURL=https://github.com/bewt85/AwsCertificateManagerDemo/raw/master/cf_simple.yml)

On the next screen, give your new stack a name (e.g. `simple`).  The default values for the next screen are fine so click "Next" and then "Create" on the Review screen.

![Example of the AWS CloudFormation console after creating a stack called "simple".  It shows unread events at the bottom](https://github.com/bewt85/AwsCertificateManagerDemo/raw/master/images/create_simple_stack.png "After creating a simple stack")

You should see something like this.  If you click on the "simple" stack, you should see the events as they happen; otherwise you might need to click the refresh icon in the top right.  When the status changes to "CREATE_COMPLETE" you can click on the "Outputs" tab and copy the URL for the load balanced app.  Note that the app isn't actually up and running yet; the servers have been created but they won't actually be serving the app for around 2 minutes.

In the mean time, lets have a quick look at the template we used.

The template is written in [YAML](http://yaml.org/) and can have a few top level keys.  These are `AWSTemplateFormatVersion` which always seems to be `2010-09-09`; `Parameters` which describes the inputs to the templates; `Resources` which defines and configures the AWS resources we want and `Outputs` which are values we want to output from the template for refrence or so that they can be consumed by other templates.  You can also add a `Description` for the template and `Mappings` which can be used to lookup values using others (e.g. lookup the correct AMI using a region).  In this example I've not even used `Parameters` because we don't need any.
