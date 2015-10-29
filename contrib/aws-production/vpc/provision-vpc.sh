#!/usr/bin/env bash
#
# Usage: ./provision-vpc.sh [name]
# The [name] is the CloudFormation stack name, and defaults to 'deis-vpc'
# the [cf-template] the path to a pre-generated CF template, defaults to making one

set -e

THIS_DIR=$(cd $(dirname $0); pwd) # absolute path
PARENT_DIR=$(dirname $THIS_DIR)
CONTRIB_DIR=$(dirname $PARENT_DIR)

source $CONTRIB_DIR/utils.sh
source $PARENT_DIR/helpers.sh

# check for AWS API tools in $PATH
check_aws

# Check if region being used is supported
region=$(aws configure get region $EXTRA_AWS_CLI_ARGS)
regions=(us-west-2 us-east-1 eu-west-1)

if [[ " ${regions[*]} " != *" $region "* ]]; then
    echo_red "$region is not supported as it has too few Availability Zones to safely operate Deis"
    echo_red "The following are the supported regions: ${regions[*]}"
    exit 1
fi

# Figure out if there is a cluster param file
PARAMETERS_FILE=$THIS_DIR/vpc.parameters.json
if [ ! -f $PARAMETERS_FILE ]; then
    echo_red "Can not locate $(basename $PARAMETERS_FILE)"
    exit 1
fi

# Check if SSH is available using a nasty little python hack
check_sshkey $PARAMETERS_FILE $DEIS_BASTION_SSH_KEY

if [ -z "$1" ]; then
    STACK_NAME=deis-vpc
else
    STACK_NAME=$1
fi

if [ -z "$2" ]; then
    TMPFILE=$(mktemp /tmp/deis.$STACK_NAME.XXXXXXXXXX)
    # TODO: Cleanup tmpfile on success
    $THIS_DIR/generate-template.py > $TMPFILE
    TEMPLATE=$TMPFILE
    echo_green "generated template can be found at ${TEMPLATE}"
else
    TEMPLATE=$2
fi

# Template has 2 instances
DEIS_NUM_TOTAL_INSTANCES=2

# Create an AWS cloudformation stack based on the a generated template
echo_green "Starting CloudFormation Stack creation"
template_source $TEMPLATE $STACK_NAME
aws cloudformation create-stack \
  $TEMPLATE_SOURCING \
  --stack-name $STACK_NAME \
  --parameters "$(<$PARAMETERS_FILE)" \
  --stack-policy-body "$(<$THIS_DIR/stack_policy.json)" \
  $EXTRA_AWS_CLI_ARGS

# Loop until stack creation is complete
if ! stack_progress $STACK_NAME 'CREATE' ; then
  echo "Destroying stack $STACK_NAME"
  bailout $STACK_NAME
  exit 1
fi

# Loop until the instances pass health checks
if ! stack_health $STACK_NAME ; then
  echo "Health checks not passed after 10m, giving up"
  echo "Destroying stack $STACK_NAME"
  bailout $STACK_NAME
  exit 1
fi

echo_green "\nYour Deis VPC was deployed to AWS CloudFormation as stack "$STACK_NAME".\n"

aws cloudformation describe-stacks --stack-name $STACK_NAME --output text $EXTRA_AWS_CLI_ARGS

printf "\nInstances are available:\n"
aws ec2 describe-instances \
  --filters Name=tag:aws:cloudformation:stack-name,Values=$STACK_NAME Name=instance-state-name,Values=running \
  --query "Reservations[].Instances[].[InstanceId,PublicIpAddress,InstanceType,Placement.AvailabilityZone,State.Name]" \
  --output text \
  $EXTRA_AWS_CLI_ARGS

# script kick off SSH agent and save in the env file for ssh
# Allows for adding ssh keys to the ssh agent
# This can't go into cloud-init; SSH becomes unavailable if dropped too early
ssh_copy "$THIS_DIR/ssh_agent.sh" "~/.ssh/rc"

BASTION_ID=$(aws ec2 describe-instances \
                --max-items 1 \
                --filters Name=tag:aws:cloudformation:stack-name,Values=$STACK_NAME Name=instance-state-name,Values=running Name=tag:Name,Values=bastion \
                --query "Reservations[].Instances[].[InstanceId]" \
                --output text \
                $EXTRA_AWS_CLI_ARGS)

echo_green "\nBastion Instance ID is: $BASTION_ID"
echo_green "Run the following before moving on to the Deis Cluster setup"
echo_green "export BASTION_ID=$BASTION_ID"
