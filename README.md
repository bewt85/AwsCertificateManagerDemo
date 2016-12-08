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

Hopefully you should leave with an impression of the power of CloudFormation when used with Lambda and some ideas of how you might want to use it.  It also gives you a bit of insight into some of the tools and techniques drie use to build our [platform as a service](https://www.drie.co).

Don't hesitate to get in touch if you have any questions or feedback on this demo or questions about how drie works behind the scenes.

## Step 1 - A load balanced app

We'll start slowly with our [first template](cf_simple.yml) which sets up a load balancer with an autoscaling group of servers behind it.  There is no connection encryption in this example.  Our aim here is to make you more comfortable with the CloudFormation interface and walk you through some of the key sections of a simple template.

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

You can also add a `Description` for the template and `Mappings` which can be used to lookup values using others (e.g. lookup the correct AMI for a region).  In this example I've not even used `Parameters` because we don't need any.

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

By now the stack should have been deployed and we can check on the web service.  Return to the CloudFormation console, click on the stack we just created, click on the "Outputs" tab and copy and paste the URL listed into the address bar.  If you've been patient enough, you should be greeted by the words "Hello, World!".

There's more that's dodgy about this template (like hardcoding the region, only supporting the AMI in that region, etc.) but I've made compromises to make the demo a bit easier.  Now that we're done with this demo, click on the stack, click Actions and delete the template.  This will delete all of the resources we've used so far automatically (and stop you being billed for them).

## Step 2 - SSL on the frontend

The next step is to add SSL to connections to the load balancer.  For this I will need a domain that I control (in this case "benmade.it") and a certificate.

First I need to create a "Hosted Zone" in [Route 53](https://console.aws.amazon.com/route53/home?region=eu-west-1#hosted-zones:).  Route 53 is Amazon's DNS service which we will use to direct traffic to the correct load balancer.  In my case I also used Route 53 to buy the "benmade.it" domain and the Hosted Zone was setup as part of this process.  If you want to use a domain that you already control then have a look at the documentation for [migrating a domain to Route 53](http://docs.aws.amazon.com/Route53/latest/DeveloperGuide/MigratingDNS.html) or the documentation for [migrating a subdomain](http://docs.aws.amazon.com/Route53/latest/DeveloperGuide/CreatingNewSubdomain.html).

When you have the Hosted Zone setup, make a note of its "Hosted Zone ID" which in my case was "Z2MFW6JEDJ91GG".

Next we need to create a new frontend certificate in [Amazon Certificate Manager](https://eu-west-1.console.aws.amazon.com/acm/home?region=eu-west-1#/) (ACM).  To do this, just click "Request a certificate" and provide the domain you want to get a certificate for.  In my case I picked a wildcard certificate for "\*.demo.benmade.it" which I use for all of the demos.

ACM checks that you're authorised to have this certificate by emailing the following:

* administrator@benmade.it
* webmaster@benmade.it
* hostmaster@benmade.it
* admin@benmade.it
* postmaster@benmade.it

When they get the email, they just need to click the link and follow the instructions on the screen.  If your administrator doesn't get this email (for example because these email addresses are not monitored) then you need to request the certificate using the API or the Amazon CLI.  There are more details in the [domain validation documentation](https://docs.aws.amazon.com/acm/latest/userguide/gs-acm-validate.html).

When your administrator has verified ownership of the domain, the status should change from "Pending validation" to "Issued".  Click on the certificate and make a note of its ARN.

It's now time to create a new stack from the [cf_frontend_cert.yml](cf_frontend_cert.yml] template.  In this case it will ask you for:

* the domain you app is served on (e.g. "frontend.demo.benmade.it");
* the ARN for the certificate you created in ACM which matches the domain (in my case "arn:aws:acm:eu-west-1:844611257690:certificate/6fdce02f-c3c9-4c0a-82fe-33dfa62d0acb"); and
* the Hosted Zone ID in Route 53 which you use to administer that domain (in my case "Z2MFW6JEDJ91GG").

Notice that `Route53HostedZoneId` gives you a lookup for your Hosted Zones.  That's because I set the type to `AWS::Route53::HostedZone::Id`.  Similarly you can limit parameters to things like SSH keys or security groups (see the [parameter documentation](http://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/parameters-section-structure.html) for more details).

```
Route53RecordSet:
    Type: AWS::Route53::RecordSet
    Properties:
        HostedZoneId: !Ref Route53HostedZoneId
        Comment: !Ref Domain
        Name: !Join [ ".", [ !Ref Domain, ""]]
        Type: CNAME
        TTL: 60
        ResourceRecords:
        - !GetAtt [ ElasticLoadBalancer, DNSName ]
```

This template creates DNS entries which send traffic to your load balancer using a more sensible URL.  The ELB has your SSL certificate installed on it by Amazon; this is used to terminate SSL and the traffic is then passed unencrypted to your backend instances.

```
+ +--  3 lines: ElasticLoadBalancer:------|+ +--  3 lines: ElasticLoadBalancer:---------------
          AvailabilityZones: !GetAZs      |          AvailabilityZones: !GetAZs
          CrossZone: true                 |          CrossZone: true
          Listeners:                      |          Listeners:
          - LoadBalancerPort: 80          |          - LoadBalancerPort: 80
            InstancePort: 8080            |            InstancePort: 8080
            Protocol: HTTP                |            Protocol: HTTP
  ----------------------------------------|          - LoadBalancerPort: 443
  ----------------------------------------|            InstancePort: 8080
  ----------------------------------------|            Protocol: HTTPS
  ----------------------------------------|            InstanceProtocol: HTTP
  ----------------------------------------|            SSLCertificateId: !Ref SSLCertificate
  ----------------------------------------|            PolicyNames: []
          HealthCheck:                    |          HealthCheck:
              Target: "TCP:8080"          |              Target: "TCP:8080"
              HealthyThreshold: "3"       |              HealthyThreshold: "3"
              UnhealthyThreshold: "5"     |              UnhealthyThreshold: "5"
              Interval: "6"               |              Interval: "6"
              Timeout: "5"                |              Timeout: "5"
+ +--  2 lines: SecurityGroups:-----------|+ +--  2 lines: SecurityGroups:--------------------
```

The other key difference is this addition to the ElasticLoadBalancer resource.  This tells it to take HTTPS traffic on port 443 (`Protocol`, `LoadBalancerPort`), use our certificate (`SSLCertificateId`) and pass that using HTTP to the instances on port 8080 (`InstanceProtocol`, `InstancePort`).

After a couple of minutes, the servers should be up and you should now be able to access you app on the domain you specified.  For example, my app was accessible on http://frontend.demo.benmade.it and https://frontend.demo.benmade.it

You can now tear down the stack to stop paying for the resources.  Note that you'll keep paying a small fee ($0.50 per month) for the Route 53 Hosted Zone until you delete that manually but we'll want that for the latter demos.

## Step 3 - Hard coded backend certificates

This is all pretty common stuff, it gets much more interesting when we start encrypting the connections to our backend instances.

This can be acheived using the [cf_backend_cert.yml](cf_backend_cert.yml) template.

```
AppSecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
        GroupDescription: Limit access to the app instances
        SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 8443
          ToPort: 8443
          SourceSecurityGroupId: !GetAtt [ElbSecurityGroup, GroupId]
```

The first big change is that we've changed the security group so that the firewalls don't permit access to the backend instances on port 8080; they can now only be accessed on port 8443 which we'll use for the encrypted traffic.

```
AppLaunchConfig:
    Type: AWS::AutoScaling::LaunchConfiguration
    Properties:
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
                - stunnel4
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
                - content: |
                    -----BEGIN PRIVATE KEY-----
                      >>> SNIPPED FOR BREVITY <<<
                    -----END PRIVATE KEY-----
                  path: /etc/stunnel/elb-backend-private.key
                  permissions: '0400'
                - content: |
                    -----BEGIN CERTIFICATE-----
                      >>> SNIPPED FOR BREVITY <<<
                    -----END CERTIFICATE-----
                  path: /etc/stunnel/elb-backend-cert.pem
                  permissions: '0444'
                - content: |
                    output=/var/log/stunnel-elb-backend.log
                    pid=/var/run/stunnel4/elb-backend.pid
                    setuid=stunnel4
                    setgid=stunnel4
                    client=no

                    [ELB]
                    cert=/etc/stunnel/elb-backend-cert.pem
                    key=/etc/stunnel/elb-backend-private.key
                    accept=0.0.0.0:8443
                    connect=127.0.0.1:8080
                  path: /etc/stunnel/elb-backend.conf
                  permissions: '0644'
                runcmd:
                - pip install flask gunicorn gevent
                - sed -i 's/^ENABLED=0/ENABLED=1/' /etc/default/stunnel4
                - touch /var/log/stunnel-elb-backend.log
                - chown stunnel4 /var/log/stunnel-elb-backend.log /etc/stunnel/elb-backend-private.key /etc/stunnel/elb-backend-cert.pem
                - systemctl restart stunnel4
                - cd /etc/ && gunicorn hello:app -b 127.0.0.1:8080 -k gevent
```

The biggest changes are in the launch configuration which is used to setup the backend instances.  Here I have used the launch configuration to put a self signed SSL certificate and it's private key onto the server and setup stunnel4 to terminate SSL. It goes without saying that **THIS IS REALLY BAD PRACTICE**.  Sensitive key data like this should not be committed to Git (especially a public repo but I'd strongly encourage not doing so in a private repo either).  You might also think that it is OK to generate the keys locally and insert it into the template just before using it to deploy the stack in CloudFormation.   That's marginally better but the private key will still be human readable to anyone with access to CloudFormation (via the Template tab).

It is possible to argue that this is a low risk because: only trusted admins will be able to access the CloudFormation console; the developer who produced the data probably used sensible settings and cleared up their local copy sensibly; and the certificate is self signed and therefore not useful for anything except this app.  That said, I've seen plenty of examples where we make these sort of compromisses now based on assumptions about how we're using things which then prove to be false in the future.  I'd therefore be keen to pick a solution which better fits with other developers (and my) future assumption that things like private keys have been kept secret.

If you created this stack, then don't forget to delete it.

## Step 4 - Automatically generated certificates

I'd prefer a solution which:

* doesn't rely on the developer remembering the correct settings to create good certificates;
* doesn't rely on the developer being good at clearing up secrets from their local environment (including making assumptions that they're good at encrypting their local disk; their swap files are encrypted etc.);
* doesn't make it easy for an administrator to read the secret keys (I prefer solutions which make it easy to hide secrets or at least audit that they've been read); and
* uses automation to reliably get round these issues.

One pattern which meets these objectives is to use AWS Lambda as part of a Custom Resource in the CloudFormation template.  Custom Resources allow you to supply code which is run when a stack is created or updated.  In our case, that code is going to: create a new certificate, private and public key when a stack is created; save the private key and certificate into an S3 bucket which most people cannot access; load the public key into the load balancer so that only instances with the private key will be trusted; grant permission to the EC2 instances to load the private key and certificate (and only their own) from the S3 bucket at startup; and reuse an existing certificate and private key for a new instance if the stack is updated or if a new instance is added to the autoscaling group.

The Lambda is just a Python script which has a method which is configured to handle events created by CloudFormation.  The code is in [certificate_lambda](certificate_lambda).  The code needs to be packaged up into a zip file before it can be deployed, this can be done using the [package.sh](certificate_lambda/package.sh) script.  Take a look at the [README](certificate_lambda/README.md) for instructions on creating your own copy of the Lambda.

```
ElbBackendCertificate:
    Type: Custom::ElbBackendCertificate
    Properties:
        ServiceToken: !Ref CreateElbBackendCertificatesArn
        AppDomain: !Ref Domain
        AppName: !Ref Domain
        AppS3Bucket: !Ref CertificateBucket
```

*Custom resource in [cf_automated.yml](cf_automated.yml)*

This new resource triggers the Lambda and passes the properties used when you created the stack. The Lambda returns a dictionary of data including `PublicKey` and `CertificateS3Key` which are used later in the template.

```
+ +-- 23 lines: ElasticLoadBalancer:---------------------------------------------------|+ +-- 23 lines: ElasticLoadBalancer:-----------------------------------
          - !GetAtt [ElbSecurityGroup, GroupId]                                        |          - !GetAtt [ElbSecurityGroup, GroupId]
          Policies:                                                                    |          Policies:
          - PolicyName: BackendPublicKeyPolicy                                         |          - PolicyName: BackendPublicKeyPolicy
            PolicyType: PublicKeyPolicyType                                            |            PolicyType: PublicKeyPolicyType
            Attributes:                                                                |            Attributes:
            - Name: PublicKey                                                          |            - Name: PublicKey
              Value: |                                                                 |              Value: !GetAtt [ ElbBackendCertificate, PublicKey ]      
                  MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1rCfBQn1Sg1Q97FbQus0     |  ---------------------------------------------------------------------
                  8khN3k1IqQn5+Vy8rvVLOEIFhzwgcKtNQ5zGEDETOYk0wqF651OCsvJOzklM5oLg     |  ---------------------------------------------------------------------
                  IG5B1ErnLC3yc1FYwm8RhC9ISYT5ToUy/gDAVUjKHqZFH2xyS/efopRAx5cDTy1Q     |  ---------------------------------------------------------------------
                  qgXZUrPVnT6XnibtsZiB4qiXnLly3IW3RXzr0kDdbFvWb8C6zT1GWU1qAyYtr4gH     |  ---------------------------------------------------------------------
                  XVulTlxQCaE/F/IftplHzCmdsXrnzJ7Gd7O8ZC3RzzueZbmmvppSSZbst6rl47zP     |  ---------------------------------------------------------------------
                  2eIqgKJX+xU/2cwAqPiYHjc7HSWGRM1UOGKebDmQ5qE+M0zMVbTISrqV6YjYTzCj     |  ---------------------------------------------------------------------
                  iQIDAQAB                                                             |  ---------------------------------------------------------------------
          - PolicyName: BackendServerAuthenticationPolicy                              |          - PolicyName: BackendServerAuthenticationPolicy
            PolicyType: BackendServerAuthenticationPolicyType                          |            PolicyType: BackendServerAuthenticationPolicyType
            Attributes:                                                                |            Attributes:
            - Name: PublicKeyPolicyName                                                |            - Name: PublicKeyPolicyName
              Value: BackendPublicKeyPolicy                                            |              Value: BackendPublicKeyPolicy
            InstancePorts: [ "8443" ]                                                  |            InstancePorts: [ "8443" ]
```

Here is where the resource is actually used.  In this case the Load Balancer resource has used the `GetAtt` function to lookup the `PublicKey` attribute created by the Lambda and used it in place of the hard coded value.

Later I've removed the hard coded private key information from the Launch configuration.  This has been replaced with a script which pulls the private key and certificate from an S3 bucket and loads them into the correct locations.

## Still TODO

This is a big improvement over the previous implementation because lots of sources of human error have been removed and it's a lot easier to limit access to the relevant keys using IAM policies on the S3 bucket.  There are a few extra improvements you should consider before using this in production.  This includes:

* Renewing certificates before they expire (e.g. using a Lambda to scan the S3 bucket and update the CloudFormation template as required);
* Load the certificates without burning down the server (e.g. using an agent on the server to pull the new certificate or maybe using AWS Code Deploy);
* Encrypt the private key (e.g. using KMS so that it can only be decrypted on the server); and
* Deploy an app more interesting than "Hello, World!".

## Takeaways

Hopefully this has given you a bit of a taste for how you can use CloudFormation and Lambda together to acheive more complicated automation tasks.  drie use similar techniques extensively as part of our service which takes care or routine maintenance like certificate management, firewalls and app scaling so that you have more time to tackle technical debt and new features.

If you've got questions about how this or drie work then please get in touch.
