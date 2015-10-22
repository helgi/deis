#!/usr/bin/env python
import json
import os
import argparse

# hack since this is not a package
if __name__ == '__main__':
    if __package__ is None:
        from os import path
        import sys
        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
        from base import AWS
    else:
        from ..base import AWS


parser = argparse.ArgumentParser()
parser.add_argument('--include-private-subnets', dest='include_private_subnets', required=False, default=os.getenv('INCLUDE_PRIVATE_SUBNETS', True), action='store_true')
parser.add_argument('--disable-termination-protection', help='Disable instance termination protection. Instances can be accidentally deleted', default=True, action='store_false')
args = vars(parser.parse_args())

CURR_DIR = os.path.dirname(os.path.realpath(__file__))

template = json.load(open(os.path.join(CURR_DIR, 'vpc.template.json'), 'r'))

if args['include_private_subnets']:
    conn = AWS(os.getenv('AWS_CLI_PROFILE', 'default'))
    region = conn.run('aws configure get region')

    regions = ['us-west-2', 'us-east-1', 'eu-west-1']
    if region not in regions:
        raise Exception("%s is not a supported region. Pick one of the following: %s" % (region, ', '.join(regions)))

    # Get mappings from separate files
    nat = {}
    bastion = {}
    for region in regions:
        # NAT
        cmd = """\
            aws ec2 describe-images \
                --region %s \
                --owners amazon \
                --filters 'Name=architecture,Values=x86_64' \
                          'Name=block-device-mapping.volume-type,Values=gp2' \
                          'Name=virtualization-type,Values=hvm' \
                          'Name=name,Values=amzn-ami-vpc-nat-hvm-*' \
                --query 'reverse(sort_by(Images, &CreationDate))[0].ImageId' \
        """ % region
        image = conn.run(cmd)
        nat[region] = {"HVM": image.strip("\"\n")}

        # Bastion
        cmd = """\
            aws ec2 describe-images \
                --region %s \
                --owners 099720109477 \
                --filters 'Name=architecture,Values=x86_64' \
                          'Name=block-device-mapping.volume-type,Values=gp2' \
                          'Name=virtualization-type,Values=hvm' \
                          'Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-trusty-14.04-amd64-server-*' \
                --query 'reverse(sort_by(Images, &CreationDate))[0].ImageId' \
        """ % region

        image = conn.run(cmd)
        bastion[region] = {"HVM": image.strip("\"\n")}

    template['Mappings']['NatAMIs'] = nat
    template['Mappings']['BastionAMIs'] = bastion

    # Instance termination protection
    template['Resources']['BastionHost']['Properties']['DisableApiTermination'] = args['disable_termination_protection']
    template['Resources']['NatHost']['Properties']['DisableApiTermination'] = args['disable_termination_protection']
else:
    # Skip anything related to the more robust network setup
    del template['Parameters']['KeyPair']
    del template['Parameters']['IamInstanceProfile']
    del template['Parameters']['SSHFrom']
    del template['Parameters']['NatInstanceType']
    del template['Parameters']['BastionInstanceType']
    del template['Parameters']['EC2VirtualizationType']
    del template['Parameters']['EC2EBSVolumeType']
    del template['Parameters']['AssociatePublicIP']
    del template['Parameters']['RootVolumeSize']
    del template['Mappings']['NatAMIs']
    del template['Mappings']['BastionAMIs']
    del template['Mappings']['SubnetConfig']['PrivateSubnet1']
    del template['Mappings']['SubnetConfig']['PrivateSubnet2']
    del template['Mappings']['SubnetConfig']['PrivateSubnet3']
    del template['Conditions']['UseIamInstanceProfile']
    del template['Resources']['PrivateSubnet1']
    del template['Resources']['PrivateSubnet2']
    del template['Resources']['PrivateSubnet3']
    del template['Resources']['PrivateRouteTable']
    del template['Resources']['PrivateRoute']
    del template['Resources']['PrivateSubnet1RouteTableAssociation']
    del template['Resources']['PrivateSubnet2RouteTableAssociation']
    del template['Resources']['PrivateSubnet3RouteTableAssociation']
    del template['Resources']['NatSecurityGroup']
    del template['Resources']['NatHost']
    del template['Resources']['NatIpAddress']
    del template['Resources']['BastionSecurityGroup']
    del template['Resources']['BastionHost']
    del template['Resources']['BastionIpAddress']
    del template['Outputs']['PrivateSubnet1Id']
    del template['Outputs']['PrivateSubnet2Id']
    del template['Outputs']['PrivateSubnet3Id']
    del template['Outputs']['BastionSecurityGroupId']
    del template['Outputs']['BastionElasticIp']

print json.dumps(template)
