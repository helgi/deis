#!/usr/bin/env bash
#
# Usage: ./provision-cluster.sh [name] [cf-template]
# The [name] is the CloudFormation stack name, and defaults to 'deis-cluster'
# the [cf-template] the path to a pre-generated CF template, defaults to making one

set -e

THIS_DIR=$(cd $(dirname $0); pwd) # absolute path
PARENT_DIR=$(dirname $THIS_DIR)
CONTRIB_DIR=$(dirname $PARENT_DIR)

source $CONTRIB_DIR/utils.sh
source $PARENT_DIR/helpers.sh

# Check for AWS API tools in $PATH
check_aws

# Figure out if there is a cluster param file
PARAMETERS_FILE=$THIS_DIR/parameters.json
if [ ! -f $PARAMETERS_FILE ]; then
  echo_red "Can not locate $(basename $PARAMETERS_FILE)"
  exit 1
fi

# Check if SSH is available specificed in cluster.parameters.json
if [ -z $DEIS_SSH_KEY ]; then
  DEIS_SSH_KEY="$HOME/.ssh/$(get_sshkey $PARAMETERS_FILE)"
fi

check_sshkey $PARAMETERS_FILE $DEIS_SSH_KEY

# Deal with inputs from the user
if [ -z "$1" ]; then
  STACK_NAME=deis-cluster
else
  STACK_NAME=$1
fi

if [ -z "$2" ]; then
  TMPFILE=$(mktemp /tmp/deis.$STACK_NAME.XXXXXXXXXX)
  # TODO: Cleanup tmpfile on success
  $THIS_DIR/generate-template.sh --stack $STACK_NAME > $TMPFILE
  TEMPLATE=$TMPFILE
  echo_green "generated template can be found at ${TEMPLATE}"
else
  TEMPLATE=$2
fi

create_stack
get_available_instances
get_elb_info

INSTANCE="$(get_first_instance)"
if [ -z "$INSTANCE" ]; then
  echo_red "The IP of any of your instances could not be found."
  echo_red "Ensure that the cloudformation stack was created successfully."
  exit 1
fi

# Running against a bastion host
if [ -n "$BASTION_ID" ]; then
  echo_yellow "Setting up a SSH tunnel to help with deisctl due to Bastion host"
  echo_yellow "Make sure to have both bastion and deis SSH keys loaded in your ssh agent"

  echo_green "Installing deisctl on the bastion host so the platform can be configured"
  run "curl -sSL http://deis.io/deisctl/install.sh | sh && sudo mv deisctl /usr/local/bin/"
  echo_green "\ndeisctl has been installed and moved to /usr/local/bin/"
  echo_green "transferring the private deis ssh key ($DEIS_SSH_KEY) to the bastion host"

  sshkey=$(basename $DEIS_SSH_KEY)
  ssh_copy $DEIS_SSH_KEY "~/.ssh/$sshkey"
  run "chmod 0600 ~/.ssh/$sshkey"
  run "ssh-add ~/.ssh/deis"

  echo_green "key transferred"
else
  export DEISCTL_TUNNEL=$INSTANCE
fi

# loop until etcd / fleet are up and running
COUNTER=1
until run deisctl list >/dev/null; do
  if [ $COUNTER -gt $ATTEMPTS ]; then
    echo_red "Timed out waiting for fleet, giving up"
    echo_red "Ensure that the private key in $PARAMETERS_FILE"
    echo_red "is added to your ssh-agent."
    break
  fi
  echo "Waiting until fleet is up and running ..."
  sleep 5
  let COUNTER=COUNTER+1
done

echo_green "Enabling platform placement"
if ! run deisctl config platform set enablePlacementOptions=true; then
  echo_red "Could not run the platform placement option!"
  echo_red "Try running deisctl config platform set enablePlacementOptions=true by hand"
fi

echo_green "Enabling proxy protocol"
if ! run deisctl config router set proxyProtocol=1; then
  echo_red "# WARNING: Enabling proxy protocol failed."
  echo_red "# Ensure that the private key in cloudformation.json is added to"
  echo_red "# your ssh-agent, then enable proxy protocol before continuing:"
  echo_red "#"
  echo_red "# deisctl config router set proxyProtocol=1\n"
fi

echo_green "\nYour Deis cluster was deployed to AWS CloudFormation as stack "$STACK_NAME"."
if [ -n "$BASTION_ID" ]; then
  echo_green "Make sure to SSH into your bastion host ($(get_bastion_host)) first"
fi

echo_green "Now run this command in your shell:"
echo_green "export DEISCTL_TUNNEL=$INSTANCE"
echo_green "\nContinue to follow the documentation for \"Installing the Deis Platform.\""
