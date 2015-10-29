#!/usr/bin/env bash
#
# Usage: ./update-cluster.sh [name] [cf-template]
# The [name] is the CloudFormation stack name, and defaults to 'deis-cluster'
# the [cf-template] the path to a pre-generated CF template, defaults to making one

set -e

THIS_DIR=$(cd $(dirname $0); pwd) # absolute path
PARENT_DIR=$(dirname $THIS_DIR)
CONTRIB_DIR=$(dirname $PARENT_DIR)

source $CONTRIB_DIR/utils.sh
source $THIS_DIR/defaults.sh
source $PARENT_DIR/helpers.sh
source $THIS_DIR/helpers.sh

# check for AWS API tools in $PATH
check_aws

# Figure out if there is a cluster param file
PARAMETERS_FILE=$THIS_DIR/cluster.parameters.json
if [ ! -f $PARAMETERS_FILE ]; then
    echo_red "Can not locate $(basename $PARAMETERS_FILE)"
    exit 1
fi

# Check if SSH is available specificed in cluster.parameters.json
check_sshkey $PARAMETERS_FILE $DEIS_SSH_KEY

# Deal with inputs from the user
if [ -z "$1" ]; then
    STACK_NAME=deis-cluster
else
    STACK_NAME=$1
fi

if [ -z "$2" ]; then
    TMPFILE=$(mktemp /tmp/deis.$STACK_NAME.XXXXXXXXXX)
    $THIS_DIR/generate-template.sh $STACK_NAME > $TMPFILE
    # TODO: Cleanup tmpfile on success
    TEMPLATE=$TMPFILE
    echo_green "generated template can be found at ${TEMPLATE}"
else
    TEMPLATE=$2
fi

# update the AWS CloudFormation stack
echo_green "Starting CloudFormation Stack updating"
template_source $TEMPLATE $STACK_NAME
aws cloudformation update-stack \
  $TEMPLATE_SOURCING \
  --stack-name $STACK_NAME \
  --parameters "$(<$PARAMETERS_FILE)" \
  --stack-policy-body "$(<$THIS_DIR/stack_policy.json)" \
  $EXTRA_AWS_CLI_ARGS

# Loop until stack update is complete
stack_progress $STACK_NAME 'UPDATE'

echo_green "\nYour Deis cluster on AWS CloudFormation has been successfully updated.\n"
