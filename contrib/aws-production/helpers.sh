# Useful helpers that is shared across the various cluster scripts

# Change aws profiles is needed
# TODO change this perhaps so it is more deis specific?
if [ ! -z "$AWS_CLI_PROFILE" ]; then
  EXTRA_AWS_CLI_ARGS+="--profile $AWS_CLI_PROFILE"
fi

template_source() {
    TEMPLATE=$1
    STACK_NAME=$2
    TEMPLATE_SIZE=$(wc -c < $TEMPLATE)
    TEMPLATE_SOURCING="--template-body file://$TEMPLATE"
    if [ "$TEMPLATE_SIZE" -gt "51200" ]; then
        echo_yellow "Template file exceeds the 51,200 byte AWS CloudFormation limit. Uploading to S3"

        # Bucket name length is 63
        KEY=$(aws configure get aws_access_key_id $EXTRA_AWS_CLI_ARGS)
        UNIQUE=$(md5 -q -s $KEY$STACK_NAME)
        BUCKET=deis-cloudformation-templates-$UNIQUE
        if [[ "$(aws s3 ls $EXTRA_AWS_CLI_ARGS | grep -o $BUCKET)" != "$BUCKET" ]]; then
            aws s3 mb s3://$BUCKET $EXTRA_AWS_CLI_ARGS
            echo_green "Made s3 bucket $BUCKET to store the CF templates in"
        fi

        FILE=$(basename $TEMPLATE)
        aws s3 cp --acl private \
            --storage-class REDUCED_REDUNDANCY \
            --only-show-errors \
            $TEMPLATE s3://$BUCKET/$FILE \
            $EXTRA_AWS_CLI_ARGS

        TEMPLATE_SOURCING="--template-url https://$BUCKET.s3.amazonaws.com/$FILE"
        echo_green "S3 upload done to s3://$BUCKET/$FILE"
    fi

    #echo $TEMPLATE_SOURCING
}

get_sshkey() {
  # Check if SSH is available using a nasty little python hack
  PARAMETERS=$1
  sshkey=$(python -c "import sys, json; data = json.load(open('$PARAMETERS')); sshkey = [row for row in data if 'KeyPair' in row.values()]; print sshkey[0]['ParameterValue']")
  echo $sshkey
}

check_sshkey() {
    PARAMETERS=$1

    sshkey=$(get_sshkey $PARAMETERS)
    echo_green "Verifying SSH Key $sshkey"
    if [ -z $sshkey ]; then
        echo_red "Could not locate a SSH Key Pair in the parameters file"
        echo_red "Follow the SSH Key Pair instructions at http://docs.deis.io/en/latest/installing_deis/aws/"
        exit 1
    else
        fingerprint=$(
            aws ec2 describe-key-pairs \
                --query "KeyPairs[?KeyName=='$sshkey'].[KeyFingerprint]" \
                --output text \
                $EXTRA_AWS_CLI_ARGS
        )

        if [ -z $fingerprint ]; then
           echo_red "SSH Key Pair '$sshkey' does not exist in AWS yet. Did you forgot to import it?"
           echo_red "Follow the SSH Key Pair instructions at http://docs.deis.io/en/latest/installing_deis/aws/"
           exit 1
        else
            if [ -z "$2" ]; then
                keypath="$HOME/.ssh/$sshkey"
            else
                # expand home directory
                keypath=$2
                keypath="${keypath/#\~/$HOME}"
            fi

            echo_green "Using $keypath as the private key to compare against"

            local_fingerprint=$(python $PARENT_DIR/ec2-fingerprint-key.py -p $keypath)
            if [ "$local_fingerprint" != "$fingerprint" ]; then
                echo_red "Local fingerprint of $keypath does not match the keypair '$sshkey' in AWS"
                echo_red "Local Fingerprint: $local_fingerprint"
                echo_red "AWS Fingerprint: $fingerprint"
                exit 1
            fi

            if ! ssh-add -l | grep -q $keypath; then
                echo_red "Could not locate $keypath in ssh-add -l - This is required for Deis"
                echo_red "Load the key with: ssh-add $keypath"
                exit 1
            fi
        fi
    fi

    echo_green "All SSH Keys look good to go!"
}

get_stack_status() {
    STACK_NAME=$1
    STACK_STATUS=$(
      aws cloudformation describe-stacks \
          --stack-name $STACK_NAME \
          --query 'Stacks[].StackStatus' \
          --output text \
          $EXTRA_AWS_CLI_ARGS
    )

    printf $STACK_STATUS
}

# Prepare bailout function to prevent us polluting the namespace
bailout() {
  aws cloudformation delete-stack --stack-name $EXTRA_AWS_CLI_ARGS $1
}

# Check for AWS API tools in $PATH
check_aws() {
  if ! which aws > /dev/null; then
    echo_red 'Please install the AWS command-line tool and ensure it is in your $PATH.'
    echo_red 'Running pip install -r requirements.txt should do the trick'
    exit 1
  fi
}

# Get Bastion Host based on the instance ID
get_bastion_host() {
    if [ -n $BASTION_HOST ]; then
        printf "$BASTION_HOST"
    fi

    BASTION_HOST=$(
      aws ec2 describe-instances \
        --instance-ids $BASTION_ID \
        --query 'Reservations[].Instances[0].PublicIpAddress' \
        --output text \
        $EXTRA_AWS_CLI_ARGS
    )

    printf "$BASTION_HOST"
}

# Copy a file to the bastion host
ssh_copy() {
  if [ -z $BASTION_ID ]; then
    echo_red "Bastion Host instance ID is not defined"
    exit 1
  fi

  scp -o UserKnownHostsFile=/dev/null \
      -o StrictHostKeyChecking=no \
      -o LogLevel=quiet \
      $1 ubuntu@$(get_bastion_host):$2 >/dev/null
}

stack_progress() {
  STACK_NAME=$1
  TYPE=$2
  ATTEMPTS=60
  SLEEPTIME=10
  COUNTER=1
  INSTANCE_IDS=""

  until [ $(wc -w <<< $INSTANCE_IDS) -eq $DEIS_NUM_TOTAL_INSTANCES ] && ([ "$STACK_STATUS" = "${TYPE}_COMPLETE" ] || [ "$STACK_STATUS" = "${TYPE}_COMPLETE_CLEANUP_IN_PROGRESS" ]) ; do
    if [ $COUNTER -gt $ATTEMPTS ]; then
      echo "Instance action failed (timeout, $(wc -w <<< $INSTANCE_IDS) of $DEIS_NUM_TOTAL_INSTANCES ready after 10m)"
      echo "Operation failed"
      exit 1
    fi

    STACK_STATUS=$(get_stack_status $STACK_NAME)
    if [ $STACK_STATUS != "${TYPE}_IN_PROGRESS" -a $STACK_STATUS != "${TYPE}_COMPLETE" ] ; then
      echo "operation failed: "
      aws --output text cloudformation describe-stack-events \
          --stack-name $STACK_NAME \
          --query "StackEvents[?ResourceStatus=='${TYPE}_FAILED'].[LogicalResourceId,ResourceStatusReason]" \
          $EXTRA_AWS_CLI_ARGS
      exit 1
    fi

    INSTANCE_IDS=$(
      aws ec2 describe-instances \
          --filters Name=tag:aws:cloudformation:stack-name,Values=$STACK_NAME Name=instance-state-name,Values=running \
          --query 'Reservations[].Instances[].[ InstanceId ]' \
          --output text \
          $EXTRA_AWS_CLI_ARGS
    )

    echo "Waiting for operation to complete ($STACK_STATUS, $(expr 61 - $COUNTER)0s) ..."
    sleep $SLEEPTIME

    let COUNTER=COUNTER+1
  done
}

stack_health() {
  STACK_NAME=$1
  ATTEMPTS=60
  SLEEPTIME=10
  COUNTER=1
  INSTANCE_STATUSES=""
  until [ `wc -w <<< $INSTANCE_STATUSES` -eq $DEIS_NUM_TOTAL_INSTANCES ]; do
    if [ $COUNTER -gt $ATTEMPTS ]; then
      exit 1
    fi

    if [ $COUNTER -ne 1 ]; then sleep $SLEEPTIME; fi
    echo "Waiting for instances to pass initial health checks ($(expr 61 - $COUNTER)0s) ..."
    INSTANCE_IDS=$(
      aws ec2 describe-instances \
          --filters Name=tag:aws:cloudformation:stack-name,Values=$STACK_NAME Name=instance-state-name,Values=running \
          --query 'Reservations[].Instances[].[ InstanceId ]' \
          --output text \
          $EXTRA_AWS_CLI_ARGS
    )

    INSTANCE_STATUSES=$(
      aws ec2 describe-instance-status \
          --filters Name=instance-status.reachability,Values=passed \
          --instance-ids $INSTANCE_IDS \
          --query 'InstanceStatuses[].[ InstanceId ]' \
          --output text \
          $EXTRA_AWS_CLI_ARGS
    )
    let COUNTER=COUNTER+1
  done
}
