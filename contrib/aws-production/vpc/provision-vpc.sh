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
PARAMETERS_FILE=$THIS_DIR/parameters.json
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

create_stack
get_available_instances
aws cloudformation describe-stacks --stack-name $STACK_NAME --output text $EXTRA_AWS_CLI_ARGS

BASTION_ID=$(aws ec2 describe-instances \
              --max-items 1 \
              --filters Name=tag:aws:cloudformation:stack-name,Values=$STACK_NAME Name=instance-state-name,Values=running Name=tag:Name,Values=bastion \
              --query "Reservations[].Instances[].[InstanceId]" \
              --output text \
              $EXTRA_AWS_CLI_ARGS)

# script kick off SSH agent and save in the env file for ssh
# Allows for adding ssh keys to the ssh agent
# This can't go into cloud-init; SSH becomes unavailable if dropped too early
ssh_copy "$THIS_DIR/ssh_agent.sh" "~/.ssh/rc"

echo_green "\nBastion Instance ID is: $BASTION_ID"
echo_green "Run the following before moving on to the Deis Cluster setup"
echo_green "export BASTION_ID=$BASTION_ID"
