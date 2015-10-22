import subprocess


class AWS(object):
    # So that the user can change profile without setting ENV vars
    aws_profile = None

    def __init__(self, aws_profile):
        self.aws_profile = aws_profile

    def run(self, cmd):
        if self.aws_profile:
            cmd = "%s --profile %s" % (cmd.strip(), self.aws_profile)
        data, err = subprocess.Popen(cmd.strip(), shell=True, stdout=subprocess.PIPE).communicate()
        if err:
            raise Exception("Command failed: " + err)
        return data.strip()
