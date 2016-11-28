# AwsCertificateManagerDemo

AWS Cerificate Manager (ACM) is a great tool to create SSL certificates and deploy them in front of AWS based services using Amazon CloudFront or an Elastic Load Balancer (ELB).  The nicest properties of ACM are:

* it's really easy to create certificates (no faffing with signing requests etc);
* it's not possible to steal the private key (not even you get to see it) which makes it much easier to secure;
* it's renewed automatically by Amazon;
* Amazon terminates SSL on their boxes (and they fix problems like Heartbleed before they're even announced); and
* it's free!

The challenge is to securely connect the load balancer to the instances actually serving the request.  Fortunately ELBs support uploading a public key for a self-signed certificate, although this is somewhat non-trivial.

## Aims

This repo leads you through the steps to apply end-to-end encryption for a collection of instances using AWS Certificate Manager (ACM), Elastic Load Balancer (ELB), AWS Lambda, CloudFormation and Amazon Simple Storage Service (S3).  Eventually your architecture will look a bit like this:

![User traffic is terminated on ELB, traffic is re-encrypted between the ELB and instances using a self signed certificate which is created by AWS Lambda and loaded from S3 when the instances boot](https://github.com/bewt85/AwsCertificateManagerDemo/raw/master/images/acm_s3_ssl_cert_demo.png "Architecture overview")

As an aside, this repo also gives you a bit of background on how CloudFormation works and how to use Custom Resources (powered by Lambda) to do more powerful things.

## Step 1 - A load balanced app

[The first template](cf_simple.yml) sets up a load balancer with an autoscaling group of servers behind it.  There is no connection encryption in this example.

To give it a go just download [the template](cf_simple.yml) and log into the AWS console and select the CloudFormation service (or [click this link](https://console.aws.amazon.com/cloudformation/home?region=eu-west-1#/stacks/new?stackName=simple)).  These templates use a hard-coded AMI which only works in the Ireland region.  Select the option to upload the CloudFormation template to S3 and browse to where you downloaded `cf_simple.yml`.

On the next screen, give your new stack a name (e.g. `simple`).  The default values for the next screen are fine so click "Next" and then "Create" on the Review screen.

![Example of the AWS CloudFormation console after creating a stack called "simple".  It shows unread events at the bottom](https://github.com/bewt85/AwsCertificateManagerDemo/raw/master/images/create_simple_stack.png "After creating a simple stack")

You should see something like this.  If you click on the "simple" stack, you should see the events as they happen, otherwise you might need to click the refresh icon in the top right.  When the status changes to `CREATE_COMPLETE` you can click on the "Outputs" tab and copy the URL for the load balanced app.  Note that the app isn't actually up and running yet; the servers have been created but they won't actually be serving the app for around 2 minutes.

In the meantime, let's have a quick look at the template we used.

The template is written in [YAML](http://yaml.org/) and can have a few top level keys.  These are:

* `AWSTemplateFormatVersion` which always seems to be `2010-09-09`;
* `Parameters` which describes the inputs to the templates;
* `Resources` which defines and configures the AWS resources we want; and
* `Outputs` which are values we want to output from the template for refrence or so that they can be consumed by other templates.  

You can also add a `Description` for the template and `Mappings` which can be used to lookup values using others (e.g. lookup the correct AMI using a region).  In this example I've not even used `Parameters` because we don't need any.

The template creates a few resources:

* `AppSecurityGroup` - a security group (`Type: AWS::EC2::SecurityGroup`) to configure firewall rules for the app instances;
* `AppScalingGroup` - an autoscaling group (`Type: AWS::AutoScaling::AutoScalingGroup`) for the app instances;
* `AppLaunchConfig` - some configuration (`Type: AWS::AutoScaling::LaunchConfiguration`) for each of the app instances (including the hello world source code);
* `ElbSecurityGroup` - a security group (`Type: AWS::EC2::SecurityGroup`) to configure firewall rules for the load balancer; and
* `ElasticLoadBalancer` - the load balancer (`Type: AWS::ElasticLoadBalancing::LoadBalancer`) itself.

The documentation for each resource is pretty easy to find by searching for the `Type` (e.g. `AWS::ElasticLoadBalancing::LoadBalancer`).  The two interesting ones here are the `AppScalingGroup` and the `AppLaunchConfig`.

```
AppScalingGroup:
    Type: AWS::AutoScaling::AutoScalingGroup
    Properties:
        AvailabilityZones: !GetAZs
        LaunchConfigurationName: !Ref AppLaunchConfig
        DesiredCapacity: 1
        MinSize: 0
        MaxSize: 2
        LoadBalancerNames:
        - !Ref ElasticLoadBalancer
    UpdatePolicy:
        AutoScalingRollingUpdate:
            MinInstancesInService: 1
            MaxBatchSize: 1
```

The first question you might have is "Why are you using an autoscaling group to load just one instance, why not just make an EC2 instance"?  Well it's a pretty convenient way of configuring which instances the load balancer should send traffic to; I can easily add health checks to recreate the instances if they die; and it makes it easier to add instances in the future.  If I had started with an EC2 instance, these features would have been harder to add later.  Autoscale groups are free so why not use them?

You might also wonder why I set `DesiredCapacity` to 1 and the `MaxSize` to 2.  The reason is that the `UpdatePolicy` creates new servers before deleting old ones and CloudFormation gets upset if I don't set `MaxSize` to be N+1.  If I was doing this properly, I would also use health checks to make sure that new instances were up and running before deleting old ones, but I'm trying to keep the demo simple.

```
AppLaunchConfig:
    Type: AWS::AutoScaling::LaunchConfiguration
    Properties:
        ImageId: ami-a4d44ed7
        SecurityGroups:
        - !GetAtt [AppSecurityGroup, GroupId]
        InstanceType: t2.nano
        UserData:
            !Base64 |
                #cloud-config
                ---
                packages:
                - git
                - python-pip
                write_files:
                - content: |
                    from flask import Flask
                    app = Flask(__name__)


                    @app.route("/")
                    def hello():
                        return "Hello, World!"

                    if __name__ == "__main__":
                        app.run(port=8080)
                  path: /etc/hello.py
                  permissions: '0644'
                runcmd:
                - pip install flask gunicorn gevent
                - cd /etc/ && gunicorn hello:app -b 0.0.0.0:8080 -k gevent
```

The `AppLaunchConfig` shows you how to use functions to refer to attributes of other template resources, for example `!GetAtt [AppSecurityGroup, GroupId]` gets the details of the security group for these instances.  I've also used the `UserData` parameter to write a "Hello, World!" web service onto the instance, install the dependencies it needs and start it up at boot time.  This is not how you should deploy your real applications: it's not very maintainable if you want your service to say something different; and there is nothing to restart the service if it falls over.  Also it's running as the root user which is very bad practice.

There's more that's dodgy about this template (like hardcoding the region, only supporting the AMI in that region, etc.) but I've made compromises to make the demo a bit easier.

## Step 2 - SSL on the frontend

So the next step is to add SSL to connections to the load balancer.  For this I will need a domain that I control (in this case "benmade.it") and a certificate.

For the first one I went into -- More to follow.
