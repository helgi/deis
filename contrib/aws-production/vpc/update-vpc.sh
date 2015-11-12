#!/usr/bin/env bash
#
# Usage: ./update-vpc.sh [name]
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

update_stack

aws --output text cloudformation describe-stacks --stack-name $STACK_NAME
