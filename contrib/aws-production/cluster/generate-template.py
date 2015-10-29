#!/usr/bin/env python
import argparse
import json
import os
import urllib2
import yaml
import sys
import shutil
import random

# hack since this is not a package
if __name__ == '__main__':
    if __package__ is None:
        from os import path
        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
        from vpc import VPC
    else:
        from ..vpc import VPC

CURR_DIR = os.path.dirname(os.path.realpath(__file__))


def get_instance_sizes():
    # Seed in the base template
    template = json.load(open(os.path.join(CURR_DIR, 'cluster.template.json'), 'r'))
    return template['Parameters']['InstanceType']['AllowedValues']


class UniqueAppendAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        unique_values = [set(values)]
        setattr(namespace, self.dest, unique_values)


def check_odd_number(value):
    ivalue = int(value)
    if not ivalue % 2:
        raise argparse.ArgumentTypeError("%s is an even number. Only odd numbers are allowed." % value)
    return ivalue


parser = argparse.ArgumentParser()
parser.add_argument('--channel', help='the CoreOS channel to use', default='stable')
parser.add_argument('--version', help='the CoreOS version to use', default='current')
parser.add_argument('--stack', help='Name of the stack being setup', required=True)
parser.add_argument('--disable-termination-protection', help='Disable instance termination protection for the cluster that has etcd on it. Instances can be accidentally deleted', default=False, action='store_true')

parser.add_argument('--aws-profile', help='Sets which AWS Profile configured in the AWS CLI to use',
                    metavar="<profile>", default=os.getenv("AWS_CLI_PROFILE"))

group = parser.add_mutually_exclusive_group(required=True)
group.add_argument('--bastion-id', help='If a bastion host is being used then its EC2 instance ID is needed', metavar="<id>")
group.add_argument('--vpc-id', help='VPC ID', metavar="<id>")

group = parser.add_argument_group('VPC', 'VPC configuration for all the planes. Zones and subnets are auto discovered unless specified here')
group.add_argument('--vpc-zones', nargs='+', help='VPC Zones', metavar="<zones>")
group.add_argument('--vpc-subnets', nargs='+', help='VPC Subnets', metavar="<subnets>")
group.add_argument('--vpc-private-subnets', nargs='+', help='VPC Private Subnets', metavar="<subnets>")

group = parser.add_argument_group('control-plane', 'Setup configuration around the Control Plane')
group.add_argument('--isolate-control-plane',
                   help='Set if Control Plane should be isolated',
                   required=False, action='store_true')
group.add_argument('--control-plane-colocate',
                   help='Other planes that should be colocated with the Control Plane',
                   nargs='+', action=UniqueAppendAction, choices=['router', 'data'],
                   default=[])
group.add_argument('--control-plane-instances',
                   help='How many control plane instances to start',
                   type=check_odd_number, metavar='<count>', default=3)
group.add_argument('--control-plane-instances-max',
                   help='How many control plane instances to scale to max',
                   type=check_odd_number, metavar='<count>', default=9)
group.add_argument('--control-plane-instance-size',
                   help='AWS instance size, otherwise uses default in template',
                   metavar='<instance type>',
                   choices=get_instance_sizes())

group = parser.add_argument_group('data-plane', 'Setup configuration around the Data Plane')
group.add_argument('--isolate-data-plane',
                   help='Set if Data Plane should be isolated',
                   required=False, action='store_true')
group.add_argument('--data-plane-colocate',
                   help='Other planes that should be colocated with the Data Plane',
                   nargs='+', action=UniqueAppendAction, choices=['router', 'control'],
                   default=[])
group.add_argument('--data-plane-instances',
                   help='How many data plane instances to start',
                   type=int, metavar='<count>', default=3)
group.add_argument('--data-plane-instances-max',
                   help='How many data plane instances to scale to max',
                   type=int, metavar='<count>', default=25)
group.add_argument('--data-plane-instance-size',
                   help='AWS instance size, otherwise uses default in template',
                   metavar='<instance type>',
                   choices=get_instance_sizes())

group = parser.add_argument_group('router-mesh', 'Setup configuration around the Router Mesh')
group.add_argument('--isolate-router',
                   help='Set if Router Mesh should be isolated',
                   required=False, action='store_true')
group.add_argument('--router-mesh-colocate',
                   dest="router_plane_colocate",
                   help='Other planes that should be colocated with the Router Mesh',
                   nargs='+', action=UniqueAppendAction, choices=['data', 'control'],
                   default=[])
group.add_argument('--router-mesh-instances',
                   dest="router_plane_instances",
                   help='How many router mesh instances to start',
                   type=int, metavar='<count>', default=3)
group.add_argument('--router-mesh-instances-max',
                   dest="router_plane_instances_max",
                   help='How many router mesh instances to scale to max',
                   type=int, metavar='<count>', default=9)
group.add_argument('--router-mesh-instance-size',
                   dest="router_plane_instance_size",
                   help='AWS instance size, otherwise uses default in template',
                   metavar='<instance type>',
                   choices=get_instance_sizes())

group = parser.add_argument_group('etcd', 'Setup configuration around the etcd cluster')
group.add_argument('--isolate-etcd',
                   help='Set if etcd should be isolated',
                   required=False, action='store_true')
group.add_argument('--etcd-instances',
                   dest="etcd_plane_instances",
                   help='How many etcd mesh instances to start',
                   type=check_odd_number, metavar='<count>', default=3)
group.add_argument('--etcd-instances-max',
                   dest="etcd_plane_instances_max",
                   help='How many etcd mesh instances to scale to max',
                   type=check_odd_number, metavar='<count>', default=9)
group.add_argument('--etcd-instance-size',
                   dest="etcd_plane_instance_size",
                   help='AWS instance size, otherwise uses default in template',
                   metavar='<instance type>',
                   choices=get_instance_sizes())

group = parser.add_argument_group('other', 'Setup configuration around the planes that are not isolated out specifically')
group.add_argument('--other-plane-instances',
                   help='How many instances to start',
                   type=int, metavar='<count>', default=3)
group.add_argument('--other-plane-instances-max',
                   help='How many instances to scale to max',
                   type=int, metavar='<count>', default=9)
group.add_argument('--other-plane-instance-size',
                   help='AWS instance size, otherwise uses default in template',
                   metavar='<instance type>',
                   choices=get_instance_sizes())

args = vars(parser.parse_args())

# Add AWS-specific units to the shared user-data
FORMAT_DOCKER_VOLUME = '''
  [Unit]
  Description=Formats the added EBS volume for Docker
  ConditionPathExists=!/etc/docker-volume-formatted
  [Service]
  Type=oneshot
  RemainAfterExit=yes
  ExecStart=/usr/sbin/wipefs -f /dev/xvdf
  ExecStart=/usr/sbin/mkfs.ext4 -i 4096 -b 4096 /dev/xvdf
  ExecStart=/bin/touch /etc/docker-volume-formatted
'''
MOUNT_DOCKER_VOLUME = '''
  [Unit]
  Description=Mount Docker volume to /var/lib/docker
  Requires=format-docker-volume.service
  After=format-docker-volume.service
  Before=docker.service
  [Mount]
  What=/dev/xvdf
  Where=/var/lib/docker
  Type=ext4
'''
DOCKER_DROPIN = '''
  [Unit]
  Requires=var-lib-docker.mount
  After=var-lib-docker.mount
'''
FORMAT_ETCD_VOLUME = '''
  [Unit]
  Description=Formats the etcd device
  ConditionPathExists=!/etc/etcd-volume-formatted
  [Service]
  Type=oneshot
  RemainAfterExit=yes
  ExecStart=/usr/sbin/wipefs -f /dev/xvdg
  ExecStart=/usr/sbin/mkfs.ext4 -i 4096 -b 4096 /dev/xvdg
  ExecStart=/bin/touch /etc/etcd-volume-formatted
'''
MOUNT_ETCD_VOLUME = '''
  [Unit]
  Description=Mounts the etcd volume
  Requires=format-etcd-volume.service
  After=format-etcd-volume.service
  [Mount]
  What=/dev/xvdg
  Where=/media/etcd
  Type=ext4
'''
PREPARE_ETCD_DATA_DIRECTORY = '''
  [Unit]
  Description=Prepares the etcd data directory
  Requires=media-etcd.mount
  After=media-etcd.mount
  Before=etcd2.service
  [Service]
  Type=oneshot
  RemainAfterExit=yes
  ExecStart=/usr/bin/chown -R etcd:etcd /media/etcd
'''
ETCD_DROPIN = '''
  [Unit]
  Requires=prepare-etcd-data-directory.service
  After=prepare-etcd-data-directory.service
'''

# etcd domain
domain = 'etcd-%s.internal' % args['stack']

# Diffs a list
def diff(a, b):
    b = set(b)
    return [aa for aa in a if aa not in b]


def coreos_amis(channel, version):
    url = "http://{channel}.release.core-os.net/amd64-usr/{version}/coreos_production_ami_all.json".format(channel=channel, version=version)
    try:
        amis = json.load(urllib2.urlopen(url))
    except (IOError, ValueError):
        print "The URL {} is invalid.".format(url)
        raise

    return dict(map(lambda n: (n['name'], dict(PV=n['pv'], HVM=n['hvm'])), amis['amis']))


def prepare_user_data(filename, etcd_cluster, planes=['control', 'data', 'router'], worker=False, name=''):
    # Define units that are going to be added to the default coreos user-data
    new_units = [
        dict({'name': 'format-docker-volume.service', 'command': 'start', 'content': FORMAT_DOCKER_VOLUME}),
        dict({'name': 'var-lib-docker.mount', 'command': 'start', 'content': MOUNT_DOCKER_VOLUME}),
        dict({'name': 'docker.service', 'drop-ins': [{'name': '90-after-docker-volume.conf', 'content': DOCKER_DROPIN}]}),
        dict({'name': 'format-etcd-volume.service', 'command': 'start', 'content': FORMAT_ETCD_VOLUME}),
        dict({'name': 'media-etcd.mount', 'command': 'start', 'content': MOUNT_ETCD_VOLUME}),
        dict({'name': 'prepare-etcd-data-directory.service', 'command': 'start', 'content': PREPARE_ETCD_DATA_DIRECTORY}),
        dict({'name': 'etcd2.service', 'drop-ins': [{'name': '90-after-etcd-volume.conf', 'content': ETCD_DROPIN}]})
    ]

    # coreos-cloudinit will start the units in order, so we want these to be processed
    # before etcd/fleet are started
    with open(filename, 'r') as handle:
        data = yaml.safe_load(handle)
        data['coreos']['units'] = new_units + data['coreos']['units']

    # sort out the planes that should be on this setup
    p = []
    for plane in planes:
        # if statements due to non-consistent naming
        if plane == 'control':
            p.append('controlPlane=true')
        elif plane == 'data':
            p.append('dataPlane=true')
        elif plane == 'router':
            p.append('routerMesh=true')

    if not p:
        # no planes, etcd isolation going on
        del data['coreos']['fleet']['metadata']
    else:
        data['coreos']['fleet']['metadata'] = ','.join(p)

    # Ditch the discovery url
    del data['coreos']['etcd2']['discovery']

    # if etcd should be in proxy mode
    if worker:
        data['coreos']['etcd2']['proxy'] = 'on'
    else:
        # Figure out if joining existing cluster or creating a new one
        tag = '%s-node-%s' % (etcd_cluster, name)
        first = '%s-node-%s' % (etcd_cluster, 1)  # Check if the first node exists
        if vpc.get_instance(first) and not vpc.get_instance(tag):
            etcd_state = 'existing'
        else:
            etcd_state = 'new'

        data['coreos']['etcd2']['name'] = "node-%s" % name
        data['coreos']['etcd2']['initial-cluster-state'] = etcd_state
        data['coreos']['etcd2']['initial-cluster-token'] = args['stack']
        data['coreos']['etcd2']['initial-advertise-peer-urls'] = 'http://node-%s.%s:2380' % (name, domain)
        data['coreos']['etcd2']['advertise-client-urls'] = 'http://node-%s.%s:2379' % (name, domain)

    # Advertise all the peers via SRV records
    data['coreos']['etcd2']['discovery-srv'] = domain

    return yaml.dump(data, default_flow_style=False)


def user_data(namespace, etcd_cluster, planes=[], worker=False, name=''):
    # Copy coreos user-data over
    coreos_userdata_example = os.path.realpath(os.path.join(CURR_DIR, '..', '..', 'coreos', 'user-data.example'))
    coreos_userdata = os.path.realpath(os.path.join(CURR_DIR, '..', '..', 'coreos', 'user-data'))
    shutil.copy2(coreos_userdata_example, coreos_userdata)
    final_userdata = os.path.join(CURR_DIR, 'user-data', namespace.lower() + '-plane-user-data')
    shutil.copy2(coreos_userdata, final_userdata)

    # Prepare the user_data and decorate with new thing as needed
    data = prepare_user_data(final_userdata, etcd_cluster, planes, worker, name)
    return ["\n", ["#cloud-config", "---"] + data.split("\n")]


def add_static_plane(tp, template, etcd_cluster, planes, azs):
    global elb_allocated  # This is nasty
    for i in range(1, (args[tp.lower() + '_plane_instances']+1)):
        instance = json.loads(open(os.path.join(CURR_DIR, 'instance.template.json'), 'r').read())
        if args[tp.lower() + '_plane_instance_size']:
            instance['Properties']['InstanceType'] = args[tp.lower() + '_plane_instance_size']

        # Pick the AZ - needed due to CF not exposing this properly for none ASG creation
        tag = '%s-node-%s' % (etcd_cluster, i)
        data = vpc.get_instance(tag)
        if data:
            az = data['Placement']['AvailabilityZone']
        else:
            az = random.choice(azs)

        instance["Properties"]["AvailabilityZone"] = az
        instance["Properties"]["NetworkInterfaces"][0]["SubnetId"] = {"Fn::FindInMap": ["VPCSubnets", az, "private"]}

        node = "node-%s" % i
        instance['Properties']['UserData']['Fn::Base64']['Fn::Join'] = user_data(tp, etcd_cluster, planes, False, i)
        instance['Properties']['Tags'] = [{'Key': 'Name', 'Value': tag}, {'Key': 'etcd', 'Value': 'true'}]
        if args['disable_termination_protection']:
            instance['Properties']['DisableApiTermination'] = False

        name = 'Etcd%sInstance' % i
        template['Resources'][name] = instance

        dns = open(os.path.join(CURR_DIR, 'dns_record.template.json'), 'r').read()
        dns = dns.replace('EtcdInstance', name)
        dns_record = json.loads(dns)
        dns_record['Name'] = "%s.%s" % (node, domain)
        template['Resources']['etcdInternalDNS']['Properties']['RecordSets'].append(dns_record)
        template['Resources']['etcdInternalDNS']['DependsOn'].append(name)

        # Setup the SRV record properly
        # see https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/ResourceRecordTypes.html#SRVFormat
        template['Resources']['etcdInternalDNS']['Properties']['RecordSets'][0]['ResourceRecords'].append("0 0 2380 node-%s.%s" % (i, domain))

    if not elb_allocated and 'router' in planes:
        # Whatever plane serves the traffic needs this. Works differently than ASGs
        elb_allocated = True
        for i in range(1, (args[tp.lower() + '_plane_instances']+1)):
            template['Resources']['DeisWebELB']['Properties']['Instances'].append({"Ref": 'Etcd%sInstance' % i})

    return template


# Adds an auto scaling group with all the right user data and sizes
def add_plane(tp, template, etcd_cluster, worker=False, planes=[]):
    global elb_allocated  # This is nasty
    tp = tp.capitalize()

    plane = open(os.path.join(CURR_DIR, 'plane.template.json'), 'r').read()
    plane = plane.replace('Plane', tp + 'Plane').replace('deis-plane-node', 'deis-%s-plane-node' % tp.lower())
    plane = json.loads(plane)
    plane[tp + 'PlaneLaunchConfig']['Properties']['UserData']['Fn::Base64']['Fn::Join'] = user_data(tp, etcd_cluster, planes, worker)
    template['Resources'].update(plane)

    min_instances = args[tp.lower() + '_plane_instances']
    max_instances = args[tp.lower() + '_plane_instances_max']
    template['Parameters'][tp + 'PlaneSize'] = {
        'Default': min_instances,
        'MinValue': min_instances,
        'Description': "Number of nodes in the cluster (%s-%s)" % (min_instances, max_instances),
        'Type': 'Number',
    }

    # Can't do this via Parameters
    template['Resources'][tp + 'PlaneAutoScale']['Properties']['MaxSize'] = max_instances

    # Instance size
    if args[tp.lower() + '_plane_instance_size']:
        template['Resources'][tp + 'PlaneLaunchConfig']['Properties']['InstanceType'] = args[tp.lower() + '_plane_instance_size']

    if not elb_allocated and 'router' in planes:
        # Whatever plane serves the traffic needs this
        elb_allocated = True
        template['Resources'][tp + 'PlaneAutoScale']['Properties']['LoadBalancerNames'] = [
            {'Ref': "DeisWebELB"}
        ]

    return template

# Figure out what goes where
elb_allocated = False  # downside is this will go to the first router seen
available_planes = ['control', 'router', 'data']
isolated_planes = {}

if args['isolate_router']:
    args['router_plane_colocate'].append('router')
    isolated_planes.update({
        'router': {
            'worker': True,
            'planes': args['router_plane_colocate']
        }
    })
    available_planes = diff(available_planes, args['router_plane_colocate'])

if args['isolate_data_plane']:
    args['data_plane_colocate'].append('data')
    isolated_planes.update({
        'data': {
            'worker': True,
            'planes': args['data_plane_colocate']
        }
    })
    available_planes = diff(available_planes, args['data_plane_colocate'])

if args['isolate_control_plane']:
    args['control_plane_colocate'].append('control')
    # Make control plane the etcd "owner" if etcd isn't being isolated
    isolated_planes.update({
        'control': {
            'worker': not args['isolate_etcd'],
            'planes': args['control_plane_colocate']
        }
    })
    available_planes = diff(available_planes, args['control_plane_colocate'])

if args['isolate_etcd']:
    isolated_planes.update({'etcd': {'worker': False, 'planes': []}})

# Deal with rest of the planes that weren't isolated
if available_planes:
    worker = True
    if not args['isolate_etcd'] and 'control' in available_planes:
        worker = False

    isolated_planes.update({
        'other': {
            'worker': worker,
            'planes': available_planes
        }
    })

# Deal with the fact plane isolation + colocation = proxy on still due to lack of further smarts
if len(isolated_planes) == 1:
    key = isolated_planes.keys()[0]
    if 'control' in isolated_planes[key]['planes']:
        isolated_planes[key]['worker'] = False

# Seed in the base template
template = json.load(open(os.path.join(CURR_DIR, 'cluster.template.json'), 'r'))

# Get all the VPC information
vpc = VPC(args['vpc_id'], args['bastion_id'], args['aws_profile'])
vpc.discover()
# Overwrite in case the user had specific opinions vs what's discovered
if args['vpc_zones']:
    vpc.zones = args['vpc_zones']
if args['vpc_private_subnets']:
    vpc.private_subnets = args['vpc_private_subnets']
if args['vpc_subnets']:
    vpc.subnets = args['vpc_subnets']

# Set VPC information by abusing Parametersa little bit
template['Parameters']['VPC']['Default'] = vpc.id
template['Parameters']['VPCAvailabilityZones']['Default'] = ','.join(vpc.zones)
template['Parameters']['VPCPublicSubnets']['Default'] = ','.join(vpc.subnets)
template['Parameters']['VPCPrivateSubnets']['Default'] = ','.join(vpc.private_subnets)
template['Mappings']['VPCSubnets'] = vpc.mapping

# Figure out where etcd is
etcd = ''
for plane, info in isolated_planes.items():
    if not info['worker']:
        etcd = plane

# Setup each plane
for plane, info in isolated_planes.items():
    if info['worker']:
        template = add_plane(plane, template, etcd, info['worker'], info['planes'])
    else:
        # setting up a etcd cluster, can't be ASG
        template = add_static_plane(plane, template, etcd, info['planes'], vpc.zones)

# Add in the AMIs
template['Mappings']['CoreOSAMIs'] = coreos_amis(args['channel'], args['version'])

# Update ingress to the cluster based on whether a bastion server is being used
if args['bastion_id']:
    del template['Parameters']['SSHFrom']
    template['Parameters']['BastionSecurityGroupID']['Default'] = vpc.bastion['sg']
    del template['Resources']['CoreOSSecurityGroup']['Properties']['SecurityGroupIngress'][0]
else:
    del template['Parameters']['BastionSecurityGroupID']
    del template['Resources']['CoreOSSecurityGroup']['Properties']['SecurityGroupIngress'][1]

print json.dumps(template, separators=(',', ': '))
